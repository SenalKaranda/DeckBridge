"""EventBus delivers typed events to matching subscribers; failures are isolated."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from deckbridge.events import DaemonStarted, EventBus, KeyPressed
from deckbridge.events.types import Event


@dataclass(frozen=True, slots=True)
class _CustomEvent(Event):
    payload: str


async def test_subscriber_receives_published_event() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(DaemonStarted, handler)
    await bus.publish(DaemonStarted())

    assert len(received) == 1
    assert isinstance(received[0], DaemonStarted)


async def test_subscribers_only_receive_their_event_type() -> None:
    bus = EventBus()
    received_keys: list[KeyPressed] = []
    received_started: list[DaemonStarted] = []

    async def on_key(event: Event) -> None:
        assert isinstance(event, KeyPressed)
        received_keys.append(event)

    async def on_started(event: Event) -> None:
        assert isinstance(event, DaemonStarted)
        received_started.append(event)

    bus.subscribe(KeyPressed, on_key)
    bus.subscribe(DaemonStarted, on_started)

    await bus.publish(KeyPressed(serial="abc", key=3))
    await bus.publish(DaemonStarted())

    assert len(received_keys) == 1
    assert received_keys[0].key == 3
    assert len(received_started) == 1


async def test_base_event_subscription_receives_all() -> None:
    bus = EventBus()
    everything: list[Event] = []

    async def catch_all(event: Event) -> None:
        everything.append(event)

    bus.subscribe(Event, catch_all)
    await bus.publish(DaemonStarted())
    await bus.publish(KeyPressed(serial="abc", key=1))
    await bus.publish(_CustomEvent(payload="hi"))

    assert len(everything) == 3


async def test_failing_subscriber_does_not_block_others() -> None:
    bus = EventBus()
    survived: list[Event] = []

    async def boom(event: Event) -> None:
        raise RuntimeError("bad subscriber")

    async def well_behaved(event: Event) -> None:
        survived.append(event)

    bus.subscribe(DaemonStarted, boom)
    bus.subscribe(DaemonStarted, well_behaved)

    # Publish must not raise even though one subscriber blew up.
    await bus.publish(DaemonStarted())
    assert len(survived) == 1


async def test_unsubscribe_removes_handler() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(DaemonStarted, handler)
    bus.unsubscribe(DaemonStarted, handler)
    await bus.publish(DaemonStarted())

    assert received == []


async def test_publish_with_no_subscribers_is_noop() -> None:
    bus = EventBus()
    await bus.publish(DaemonStarted())  # must not raise


async def test_handlers_run_concurrently() -> None:
    """Two handlers each sleeping 50ms should complete in ~50ms total, not 100ms."""
    bus = EventBus()
    order: list[str] = []

    async def slow_a(_event: Event) -> None:
        await asyncio.sleep(0.05)
        order.append("a")

    async def slow_b(_event: Event) -> None:
        await asyncio.sleep(0.05)
        order.append("b")

    bus.subscribe(DaemonStarted, slow_a)
    bus.subscribe(DaemonStarted, slow_b)

    loop = asyncio.get_running_loop()
    start = loop.time()
    await bus.publish(DaemonStarted())
    elapsed = loop.time() - start

    assert sorted(order) == ["a", "b"]
    assert elapsed < 0.09, f"handlers ran sequentially, elapsed={elapsed:.3f}s"


@pytest.mark.parametrize("event", [DaemonStarted(), KeyPressed(serial="x", key=0)])
async def test_immutable_events(event: Event) -> None:
    """Frozen dataclasses prevent in-flight mutation by subscribers."""
    with pytest.raises((AttributeError, Exception)):
        event.payload = "tampered"  # type: ignore[attr-defined]
