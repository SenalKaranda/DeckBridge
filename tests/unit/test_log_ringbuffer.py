"""LogRingBuffer — append/snapshot/subscribe semantics + cross-thread safety."""

from __future__ import annotations

import asyncio
import threading

import pytest

from deckbridge.logging_.ringbuffer import LogRingBuffer


def test_append_and_snapshot() -> None:
    buf = LogRingBuffer(maxlen=10)
    buf.append("a")
    buf.append("b")
    assert buf.snapshot() == ["a", "b"]


def test_maxlen_evicts_oldest() -> None:
    buf = LogRingBuffer(maxlen=3)
    for letter in "abcde":
        buf.append(letter)
    assert buf.snapshot() == ["c", "d", "e"]


def test_iteration_returns_snapshot_copy() -> None:
    buf = LogRingBuffer()
    buf.append("x")
    buf.append("y")
    out = list(buf)
    buf.append("z")
    # Iteration captured a snapshot at the time it was iterated.
    assert out == ["x", "y"]


def test_len_reflects_current_size() -> None:
    buf = LogRingBuffer(maxlen=5)
    for letter in "abc":
        buf.append(letter)
    assert len(buf) == 3


async def test_subscriber_receives_subsequent_appends() -> None:
    buf = LogRingBuffer()
    queue = buf.subscribe()
    buf.append("first")
    buf.append("second")
    received = [await asyncio.wait_for(queue.get(), 1.0) for _ in range(2)]
    assert received == ["first", "second"]
    buf.unsubscribe(queue)


async def test_unsubscribed_queue_stops_filling() -> None:
    buf = LogRingBuffer()
    queue = buf.subscribe()
    buf.append("kept")
    await asyncio.wait_for(queue.get(), 1.0)
    buf.unsubscribe(queue)
    buf.append("dropped")
    # Nothing pending after unsubscribe.
    assert queue.empty()


async def test_multiple_subscribers_each_get_records() -> None:
    buf = LogRingBuffer()
    q1 = buf.subscribe()
    q2 = buf.subscribe()
    buf.append("hello")
    a = await asyncio.wait_for(q1.get(), 1.0)
    b = await asyncio.wait_for(q2.get(), 1.0)
    assert a == "hello"
    assert b == "hello"
    buf.unsubscribe(q1)
    buf.unsubscribe(q2)


async def test_append_from_other_thread_reaches_subscriber() -> None:
    """Producer thread isn't on the asyncio loop — the buffer should still
    deliver via call_soon_threadsafe."""
    buf = LogRingBuffer()
    queue = buf.subscribe()

    def produce() -> None:
        buf.append("from-thread")

    t = threading.Thread(target=produce)
    t.start()
    t.join()

    received = await asyncio.wait_for(queue.get(), 1.0)
    assert received == "from-thread"
    buf.unsubscribe(queue)


def test_get_ringbuffer_is_singleton() -> None:
    from deckbridge.logging_.ringbuffer import get_ringbuffer

    a = get_ringbuffer()
    b = get_ringbuffer()
    assert a is b


def test_buffering_processor_appends_to_singleton() -> None:
    from deckbridge.logging_.ringbuffer import buffering_processor, get_ringbuffer

    before = len(get_ringbuffer())
    out = buffering_processor(None, "info", {"event": "test_event", "x": 1})
    assert out == {"event": "test_event", "x": 1}  # passes the dict through
    assert len(get_ringbuffer()) == before + 1
    last = get_ringbuffer().snapshot()[-1]
    assert "test_event" in last


def test_buffering_processor_handles_unjsonable_values() -> None:
    """A bytes/non-JSON value shouldn't crash the processor."""
    from deckbridge.logging_.ringbuffer import buffering_processor

    weird: object = object()
    # default=str in our serializer should turn it into a string.
    buffering_processor(None, "info", {"event": "weird", "obj": weird})


@pytest.mark.parametrize("maxlen", [1, 5, 100])
def test_maxlen_parametrized(maxlen: int) -> None:
    buf = LogRingBuffer(maxlen=maxlen)
    for i in range(maxlen + 5):
        buf.append(str(i))
    snap = buf.snapshot()
    assert len(snap) == maxlen
    assert snap[-1] == str(maxlen + 4)
