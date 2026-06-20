"""DeckManager rescan diffs decks; lifecycle events fire correctly."""

from __future__ import annotations

from typing import Any

from deckbridge.device import DeckManager
from deckbridge.events import DeckConnected, DeckDisconnected, EventBus
from deckbridge.events.types import Event
from tests.fixtures.fake_deck import FakeStreamDeck


class _MutableDiscoverer:
    """A discoverer whose return list can be swapped between rescan() calls."""

    def __init__(self, initial: list[FakeStreamDeck] | None = None) -> None:
        self.handles: list[FakeStreamDeck] = list(initial or [])

    def __call__(self) -> list[Any]:
        return list(self.handles)


def _collect_events(bus: EventBus) -> list[Event]:
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(Event, handler)
    return received


async def test_start_attaches_initial_decks_and_publishes_connected() -> None:
    bus = EventBus()
    received = _collect_events(bus)
    fake = FakeStreamDeck(serial="ABC")
    manager = DeckManager(bus, _MutableDiscoverer([fake]))

    await manager.start()

    assert "ABC" in manager.decks
    assert manager.decks["ABC"].attached is True
    connected = [e for e in received if isinstance(e, DeckConnected)]
    assert len(connected) == 1
    assert connected[0].serial == "ABC"
    assert connected[0].model == "FakeStreamDeck"

    await manager.stop()


async def test_stop_detaches_all_and_publishes_disconnected() -> None:
    bus = EventBus()
    received = _collect_events(bus)
    fake = FakeStreamDeck(serial="ABC")
    manager = DeckManager(bus, _MutableDiscoverer([fake]))

    await manager.start()
    received.clear()

    await manager.stop()

    assert manager.decks == {}
    assert not fake.is_open()
    disconnected = [e for e in received if isinstance(e, DeckDisconnected)]
    assert len(disconnected) == 1
    assert disconnected[0].serial == "ABC"


async def test_rescan_does_not_double_attach_existing_deck() -> None:
    """Re-running rescan() with the same discoverer state must not re-emit DeckConnected."""
    bus = EventBus()
    received = _collect_events(bus)
    fake = FakeStreamDeck(serial="ABC")
    manager = DeckManager(bus, _MutableDiscoverer([fake]))

    await manager.start()
    received.clear()

    await manager.rescan()

    connected = [e for e in received if isinstance(e, DeckConnected)]
    assert connected == []  # no re-emission

    await manager.stop()


async def test_rescan_attaches_newly_appearing_deck() -> None:
    bus = EventBus()
    received = _collect_events(bus)
    discoverer = _MutableDiscoverer([])
    manager = DeckManager(bus, discoverer)

    await manager.start()
    received.clear()

    new_deck = FakeStreamDeck(serial="NEW")
    discoverer.handles = [new_deck]
    await manager.rescan()

    assert "NEW" in manager.decks
    connected = [e for e in received if isinstance(e, DeckConnected)]
    assert len(connected) == 1
    assert connected[0].serial == "NEW"

    await manager.stop()


async def test_rescan_detaches_disappearing_deck() -> None:
    bus = EventBus()
    received = _collect_events(bus)
    fake = FakeStreamDeck(serial="GONE")
    discoverer = _MutableDiscoverer([fake])
    manager = DeckManager(bus, discoverer)

    await manager.start()
    received.clear()

    discoverer.handles = []  # device unplugged
    await manager.rescan()

    assert manager.decks == {}
    assert not fake.is_open()
    disconnected = [e for e in received if isinstance(e, DeckDisconnected)]
    assert len(disconnected) == 1
    assert disconnected[0].serial == "GONE"

    await manager.stop()


async def test_rescan_handles_multiple_decks() -> None:
    bus = EventBus()
    received = _collect_events(bus)
    decks = [FakeStreamDeck(serial=f"DECK-{i}") for i in range(3)]
    manager = DeckManager(bus, _MutableDiscoverer(decks))

    await manager.start()

    assert set(manager.decks) == {"DECK-0", "DECK-1", "DECK-2"}
    connected = [e for e in received if isinstance(e, DeckConnected)]
    assert len(connected) == 3
    assert {e.serial for e in connected} == {"DECK-0", "DECK-1", "DECK-2"}

    await manager.stop()


async def test_failing_discoverer_does_not_crash_rescan() -> None:
    """A discoverer that raises must be logged and treated as 'no decks'."""
    bus = EventBus()

    def boom() -> list[Any]:
        raise RuntimeError("simulated USB transport failure")

    manager = DeckManager(bus, boom)
    await manager.start()  # must not raise
    assert manager.decks == {}
    await manager.stop()


async def test_failing_attach_does_not_crash_rescan() -> None:
    """If a single deck fails to open, others still attach."""

    class BrokenDeck(FakeStreamDeck):
        def open(self) -> None:
            raise RuntimeError("hidapi: device locked")

    bus = EventBus()
    received = _collect_events(bus)
    good = FakeStreamDeck(serial="GOOD")
    bad = BrokenDeck(serial="BAD")
    manager = DeckManager(bus, _MutableDiscoverer([bad, good]))

    await manager.start()

    assert "GOOD" in manager.decks
    assert "BAD" not in manager.decks
    connected = [e for e in received if isinstance(e, DeckConnected)]
    assert {e.serial for e in connected} == {"GOOD"}

    await manager.stop()


async def test_swapping_serial_unplug_replug_cycle() -> None:
    """Unplug one deck and plug a different one between rescans."""
    bus = EventBus()
    received = _collect_events(bus)
    a = FakeStreamDeck(serial="A")
    b = FakeStreamDeck(serial="B")
    discoverer = _MutableDiscoverer([a])
    manager = DeckManager(bus, discoverer)

    await manager.start()
    received.clear()

    discoverer.handles = [b]
    await manager.rescan()

    assert set(manager.decks) == {"B"}
    types = [(type(e).__name__, getattr(e, "serial", None)) for e in received]
    assert ("DeckDisconnected", "A") in types
    assert ("DeckConnected", "B") in types

    await manager.stop()
