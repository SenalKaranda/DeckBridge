"""Deck wrapper translates HID-thread key callbacks into KeyPressed events."""

from __future__ import annotations

import asyncio

import pytest

from deckbridge.device import Deck
from deckbridge.events import EventBus, KeyPressed
from deckbridge.events.types import Event
from tests.fixtures.fake_deck import FakeStreamDeck


async def test_attach_opens_handle_and_reads_metadata() -> None:
    bus = EventBus()
    fake = FakeStreamDeck(serial="ABC-123")
    deck = Deck(fake, bus, loop=asyncio.get_running_loop())

    deck.attach()

    assert fake.is_open()
    assert deck.attached is True
    assert deck.serial == "ABC-123"
    assert deck.key_count == 15
    assert deck.model == "FakeStreamDeck"


async def test_attach_resets_handle_to_clear_boot_logo() -> None:
    """Real Stream Decks display the Elgato boot logo until software pushes
    a frame OR calls reset(). A deck attached with no pages configured
    would otherwise show the logo forever — clear it on attach so the user
    sees a known blank state immediately."""
    fake = FakeStreamDeck()
    deck = Deck(fake, EventBus(), loop=asyncio.get_running_loop())

    deck.attach()

    assert ("reset", ()) in fake.calls


async def test_metadata_unavailable_before_attach() -> None:
    fake = FakeStreamDeck()
    deck = Deck(fake, EventBus(), loop=asyncio.get_running_loop())

    with pytest.raises(RuntimeError, match="before attach"):
        _ = deck.serial
    with pytest.raises(RuntimeError, match="before attach"):
        _ = deck.key_count


async def test_detach_closes_handle_and_is_idempotent() -> None:
    fake = FakeStreamDeck()
    deck = Deck(fake, EventBus(), loop=asyncio.get_running_loop())
    deck.attach()
    assert fake.is_open()

    deck.detach()
    assert not fake.is_open()
    assert deck.attached is False

    # Calling detach again is a no-op, no exception.
    deck.detach()
    assert not fake.is_open()


async def test_attach_is_idempotent() -> None:
    """Calling attach() twice should not re-open the handle."""
    fake = FakeStreamDeck()
    deck = Deck(fake, EventBus(), loop=asyncio.get_running_loop())
    deck.attach()
    deck.attach()  # would raise RuntimeError("already opened") if we re-opened
    assert fake.is_open()


async def test_press_publishes_key_pressed_event() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def collector(event: Event) -> None:
        received.append(event)

    bus.subscribe(KeyPressed, collector)

    fake = FakeStreamDeck(serial="DECK-1")
    deck = Deck(fake, bus, loop=asyncio.get_running_loop())
    deck.attach()

    fake.simulate_press(7)
    # Yield so the run_coroutine_threadsafe-scheduled publish coroutine can run.
    await asyncio.sleep(0.05)

    assert len(received) == 1
    event = received[0]
    assert isinstance(event, KeyPressed)
    assert event.serial == "DECK-1"
    assert event.key == 7


async def test_release_does_not_publish_event() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def collector(event: Event) -> None:
        received.append(event)

    bus.subscribe(KeyPressed, collector)

    fake = FakeStreamDeck()
    deck = Deck(fake, bus, loop=asyncio.get_running_loop())
    deck.attach()

    fake.simulate_press(3, pressed=True)
    fake.simulate_press(3, pressed=False)
    await asyncio.sleep(0.05)

    # Only the press fires an event; release is dropped.
    assert len(received) == 1
    assert received[0].key == 3  # type: ignore[attr-defined]


async def test_multiple_presses_each_publish() -> None:
    bus = EventBus()
    received: list[KeyPressed] = []

    async def collector(event: Event) -> None:
        assert isinstance(event, KeyPressed)
        received.append(event)

    bus.subscribe(KeyPressed, collector)

    fake = FakeStreamDeck()
    deck = Deck(fake, bus, loop=asyncio.get_running_loop())
    deck.attach()

    for k in range(5):
        fake.simulate_press(k)
    await asyncio.sleep(0.1)

    assert len(received) == 5
    assert [e.key for e in received] == [0, 1, 2, 3, 4]
