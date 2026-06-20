"""In-memory ringbuffer of recent structured log records.

Wraps a thread-safe ``deque(maxlen=N)`` so the diagnostics WebSocket can
catch up on what just happened, then stream new lines as they come in.

Cross-thread safety matters: structlog records can originate from any
thread (the Stream Deck HID callback thread, pyudev hot-plug, the MQTT
client's task on the asyncio loop, etc.). This module exposes a
``BufferingProcessor`` that's safe to call from any thread; subscribers
are notified via ``loop.call_soon_threadsafe`` so their async queues
fill up correctly even when the producing thread isn't on the asyncio
loop.
"""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator, MutableMapping


_DEFAULT_MAX = 500


class LogRingBuffer:
    """Thread-safe ring of recent rendered log records (one JSON string each).

    Subscribers register an asyncio Queue and the loop they live on; when a
    new record is appended, the buffer schedules a put on each subscriber
    queue via ``loop.call_soon_threadsafe``.
    """

    def __init__(self, maxlen: int = _DEFAULT_MAX) -> None:
        self._records: deque[str] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        # Each entry is (loop, asyncio.Queue[str]).
        self._subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue[str]]] = []

    # ---- producer side --------------------------------------------------

    def append(self, rendered: str) -> None:
        """Add a rendered log line and fan out to subscribers."""
        with self._lock:
            self._records.append(rendered)
            subs = list(self._subscribers)
        for loop, queue in subs:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, rendered)
            except RuntimeError:
                # Loop is closed — skip; the subscriber will be cleaned up
                # on its next register/unregister cycle.
                continue

    # ---- consumer side --------------------------------------------------

    def snapshot(self) -> list[str]:
        """Copy of the current buffer contents (oldest first)."""
        with self._lock:
            return list(self._records)

    def subscribe(
        self, loop: asyncio.AbstractEventLoop | None = None, *, maxsize: int = 200
    ) -> asyncio.Queue[str]:
        """Register a new subscriber queue. Caller must call :meth:`unsubscribe`."""
        loop = loop or asyncio.get_running_loop()
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=maxsize)
        with self._lock:
            self._subscribers.append((loop, queue))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        with self._lock:
            self._subscribers = [(loop, q) for (loop, q) in self._subscribers if q is not queue]

    # ---- diagnostics ----------------------------------------------------

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    def __iter__(self) -> Iterator[str]:
        return iter(self.snapshot())


# Module-level singleton. The structlog processor and the lifespan
# both reach for this; nothing forces multiple instances.
_BUFFER: LogRingBuffer | None = None


def get_ringbuffer() -> LogRingBuffer:
    """Return the process-wide LogRingBuffer (lazy-initialized)."""
    global _BUFFER
    if _BUFFER is None:
        _BUFFER = LogRingBuffer()
    return _BUFFER


def buffering_processor(
    _logger: Any, _name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: capture each record into the ringbuffer.

    Runs BEFORE the actual renderer in the structlog processor chain. We
    render our own compact JSON copy here so the buffer holds a structured
    record regardless of the human-facing renderer choice.
    """
    # Importing inside the function keeps module import cheap and avoids a
    # circular dep between logging_.setup and logging_.ringbuffer.
    import json

    try:
        rendered = json.dumps(dict(event_dict), default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        rendered = str(event_dict)
    get_ringbuffer().append(rendered)
    return event_dict
