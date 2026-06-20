"""DeckManager — owns the lifecycle of every attached Stream Deck.

Started during FastAPI lifespan startup and stopped during shutdown. It is
the only module that calls into the discoverer; all other subsystems consume
deck state via :class:`~deckbridge.events.DeckConnected` /
:class:`~deckbridge.events.DeckDisconnected` events on the bus.

Hot-plug detection on Linux runs in a background daemon thread that watches
udev for USB events with vendor ID ``0fd9`` (Elgato). On non-Linux platforms
hot-plug is unavailable; the manager still works for whatever devices were
connected at startup, and ``rescan()`` can be called manually if needed.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from typing import TYPE_CHECKING, Any

from deckbridge.device.deck import Deck
from deckbridge.events import DeckConnected, DeckDisconnected
from deckbridge.logging_ import get_logger

if TYPE_CHECKING:
    from deckbridge.device.discoverer import Discoverer
    from deckbridge.events import EventBus

ELGATO_VENDOR_ID = "0fd9"


class DeckManager:
    """Orchestrates discovery, attach/detach, and hot-plug rescans."""

    def __init__(self, bus: EventBus, discoverer: Discoverer) -> None:
        self._bus = bus
        self._discover = discoverer
        self._decks: dict[str, Deck] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._hotplug_thread: threading.Thread | None = None
        self._hotplug_stop = threading.Event()
        self._log = get_logger(__name__)

    # ---- lifecycle ----

    async def start(self) -> None:
        """Enumerate currently-connected decks, attach each, start hot-plug watcher (Linux)."""
        self._loop = asyncio.get_running_loop()
        await self.rescan()
        if sys.platform == "linux":
            self._start_hotplug()

    async def stop(self) -> None:
        """Stop hot-plug watcher and detach every deck."""
        self._hotplug_stop.set()
        if self._hotplug_thread is not None:
            self._hotplug_thread.join(timeout=2)
            self._hotplug_thread = None
        for handle_id in list(self._decks):
            await self._detach_by_id(handle_id)

    @property
    def decks(self) -> dict[str, Deck]:
        """Snapshot of attached decks keyed by serial number."""
        return {d.serial: d for d in self._decks.values()}

    # ---- discovery ----

    async def rescan(self) -> None:
        """Diff currently-attached decks against the discoverer; attach new, detach gone.

        Called on startup, on every udev hot-plug event, and from tests that
        want to simulate a plug/unplug without going through udev.

        We key by ``handle.id()`` (the HID path) rather than by serial because
        the third-party library returns fresh handle instances on every
        enumerate() call, and we cannot read a handle's serial without opening
        it. Opening a handle for a device that's already attached can disturb
        the existing connection — so we dedupe before opening.
        """
        try:
            handles = list(self._discover())
        except Exception as exc:
            self._log.warning("rescan_discovery_failed", error=repr(exc))
            return

        seen: set[str] = set()
        for handle in handles:
            handle_id = self._handle_id(handle)
            seen.add(handle_id)
            if handle_id in self._decks:
                continue  # already attached — leave alone

            deck = self._wrap(handle)
            try:
                deck.attach()
            except Exception as exc:
                self._log.warning("attach_failed", handle_id=handle_id, error=repr(exc))
                continue

            self._decks[handle_id] = deck
            self._log.info("deck_attached", serial=deck.serial, model=deck.model)
            await self._bus.publish(DeckConnected(serial=deck.serial, model=deck.model))

        # Detach decks that were present last time but are gone now.
        for handle_id in list(self._decks):
            if handle_id not in seen:
                await self._detach_by_id(handle_id)

    async def _detach_by_id(self, handle_id: str) -> None:
        deck = self._decks.pop(handle_id, None)
        if deck is None:
            return
        serial = deck.serial
        deck.detach()
        self._log.info("deck_detached", serial=serial)
        await self._bus.publish(DeckDisconnected(serial=serial))

    def _wrap(self, handle: Any) -> Deck:
        assert self._loop is not None, "DeckManager.start() must run before _wrap"
        return Deck(handle, self._bus, loop=self._loop)

    @staticmethod
    def _handle_id(handle: Any) -> str:
        """Stable identifier for a handle so duplicate enumerations don't double-attach.

        The real ``StreamDeck`` handle exposes ``.id()`` returning its HID path.
        FakeStreamDeck (tests) implements the same method.
        """
        if hasattr(handle, "id") and callable(handle.id):
            return str(handle.id())
        # Fallback for handles that don't implement id() — unlikely, but at
        # least use serial as a degraded key.
        return f"serial:{handle.get_serial_number()}"

    # ---- hot-plug (Linux) ----

    def _start_hotplug(self) -> None:
        """Begin watching udev for Elgato USB events on a daemon thread.

        No-op on platforms where ``pyudev`` is not installed.
        """
        try:
            import pyudev
        except ImportError:
            self._log.info("hotplug_disabled", reason="pyudev_not_installed")
            return

        ctx = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(ctx)
        monitor.filter_by(subsystem="usb")
        monitor.start()

        loop = self._loop
        assert loop is not None

        def watch() -> None:
            self._log.info("hotplug_watching", vendor=ELGATO_VENDOR_ID)
            while not self._hotplug_stop.is_set():
                device = monitor.poll(timeout=1.0)
                if device is None:
                    continue
                if device.get("ID_VENDOR_ID") != ELGATO_VENDOR_ID:
                    continue
                action = device.action
                if action not in {"add", "remove"}:
                    continue
                self._log.info("hotplug_event", action=action)
                # Run the rescan on the asyncio loop. We deliberately don't
                # await the future — the daemon thread keeps watching for
                # the next event.
                asyncio.run_coroutine_threadsafe(self.rescan(), loop)

        self._hotplug_thread = threading.Thread(
            target=watch,
            name="deckbridge-hotplug",
            daemon=True,
        )
        self._hotplug_thread.start()
