"""Per-deck adapter.

Wraps a single Stream Deck handle (real or fake) and translates physical key
events delivered on the library's HID thread into typed
:class:`~deckbridge.events.KeyPressed` messages on the asyncio event loop.

Also exposes :meth:`set_key_image` for the M6c painter to push composited
images. For real Stream Decks the bytes go through ``StreamDeck.ImageHelpers
.PILHelper.to_native_format`` (typically JPEG); for FakeStreamDeck and other
test fakes that don't implement the full handle protocol, raw PNG bytes
pass through unchanged (the fake records what it was given).
"""

from __future__ import annotations

import asyncio
import io
from typing import TYPE_CHECKING, Any

from PIL import Image

from deckbridge.events import KeyPressed
from deckbridge.logging_ import get_logger

if TYPE_CHECKING:
    from deckbridge.events import EventBus


class Deck:
    """A single attached Stream Deck.

    Lifecycle:
        construct → ``attach()`` (opens, reads metadata, registers callback)
                  → ``detach()`` (unregisters callback, closes)
    """

    def __init__(
        self,
        handle: Any,
        bus: EventBus,
        *,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._handle = handle
        self._bus = bus
        self._loop = loop
        self._log = get_logger(__name__)

        # Populated by attach() so we don't read metadata from an unopened
        # device. Real StreamDeck handles refuse some queries before open().
        self._serial: str | None = None
        self._key_count: int | None = None
        self._model: str = type(handle).__name__
        self._attached = False

    # ---- introspection ----

    @property
    def serial(self) -> str:
        if self._serial is None:
            raise RuntimeError("Deck.serial accessed before attach()")
        return self._serial

    @property
    def key_count(self) -> int:
        if self._key_count is None:
            raise RuntimeError("Deck.key_count accessed before attach()")
        return self._key_count

    @property
    def model(self) -> str:
        """The handle's class name (e.g. ``StreamDeckMK2``, ``FakeStreamDeck``)."""
        return self._model

    @property
    def attached(self) -> bool:
        return self._attached

    # ---- lifecycle ----

    def attach(self) -> None:
        """Open the device, read metadata, register the key callback."""
        if self._attached:
            return
        self._handle.open()
        self._serial = self._handle.get_serial_number()
        self._key_count = self._handle.key_count()
        self._handle.set_key_callback(self._on_key_callback)
        # Clear the Elgato boot logo so the user sees a known blank state
        # even before the painter has any keys to render. Without this,
        # an attached deck with no pages configured shows the boot logo
        # forever (the device only stops showing it once software pushes
        # a frame). Real StreamDeck handles support .reset(); fakes may
        # not, so guard with hasattr.
        if hasattr(self._handle, "reset"):
            try:
                self._handle.reset()
            except Exception as exc:
                self._log.warning("deck_reset_failed", serial=self._serial, error=repr(exc))
        self._attached = True
        self._log.info(
            "deck_opened",
            serial=self._serial,
            model=self._model,
            key_count=self._key_count,
        )

    def detach(self) -> None:
        """Close the device. Safe to call when not attached or after a prior detach."""
        if not self._attached:
            return
        try:
            self._handle.close()
        except Exception as exc:
            self._log.warning(
                "deck_close_failed",
                serial=self._serial,
                error=repr(exc),
            )
        finally:
            self._attached = False
            self._log.info("deck_closed", serial=self._serial)

    # ---- output ----

    def set_key_image(self, slot: int, image: bytes | Image.Image) -> None:
        """Push a key image to the device.

        Accepts either raw PNG bytes (the painter's normal path) or a PIL
        Image. For real Stream Decks the image is converted through
        ``PILHelper.to_native_format`` (which produces JPEG for MK.2). If
        that conversion fails — e.g. the underlying handle is a test fake
        that doesn't satisfy PILHelper's expectations — we fall back to
        passing raw PNG bytes straight through, which fakes record happily
        and tests can assert on.
        """
        if not self._attached:
            return

        pil: Image.Image
        if isinstance(image, bytes):
            try:
                opened = Image.open(io.BytesIO(image))
                opened.load()
                pil = opened
            except Exception as exc:
                self._log.warning("image_decode_failed", slot=slot, error=repr(exc))
                return
        else:
            pil = image

        native: bytes
        try:
            from StreamDeck.ImageHelpers import PILHelper

            native = PILHelper.to_native_format(self._handle, pil)
        except Exception as exc:
            self._log.debug("pilhelper_unavailable_using_raw_png", error=repr(exc))
            buf = io.BytesIO()
            pil.save(buf, format="PNG")
            native = buf.getvalue()

        try:
            self._handle.set_key_image(slot, native)
        except Exception as exc:
            self._log.warning("set_key_image_failed", slot=slot, error=repr(exc))

    # ---- input ----

    def _on_key_callback(self, _deck: Any, key: int, pressed: bool) -> None:
        """HID-thread callback. Marshals onto the asyncio loop.

        We emit on press only (not release) — release semantics are added in a
        future milestone if/when long-press support lands. Releases are dropped
        silently here.
        """
        if not pressed:
            return
        event = KeyPressed(serial=self.serial, key=key)
        # run_coroutine_threadsafe is the canonical bridge from a non-loop
        # thread into an asyncio loop. The returned Future is intentionally
        # discarded; EventBus.publish swallows subscriber failures internally.
        asyncio.run_coroutine_threadsafe(self._bus.publish(event), self._loop)
