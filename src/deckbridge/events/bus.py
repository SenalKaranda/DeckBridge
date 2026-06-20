"""In-process async event bus.

Every long-running subsystem publishes typed :class:`~deckbridge.events.types.Event`
instances through one shared bus. Any subsystem can subscribe to a specific
event type (or the base :class:`Event` for everything) and receive each event
on the asyncio loop where it subscribed.

Design notes:
    * Subscribers are async callables receiving the event by reference. They
      should not block the publisher; if a subscriber needs to do significant
      work it should hand the event to its own ``asyncio.Queue``.
    * Publishing is fire-and-forget: errors raised by a subscriber are logged
      and swallowed so one buggy subscriber cannot poison the bus.
    * The bus is intentionally simple — no priority, no retention, no replay.
      Subsystems that need history (e.g. the in-UI log viewer in M8) keep
      their own ringbuffers.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from deckbridge.events.types import Event
from deckbridge.logging_ import get_logger

Subscriber = Callable[[Event], Awaitable[None]]


class EventBus:
    """Asyncio-native publish/subscribe bus for typed Event objects."""

    def __init__(self) -> None:
        self._subscribers: dict[type[Event], list[Subscriber]] = {}
        self._log = get_logger(__name__)

    def subscribe(self, event_type: type[Event], handler: Subscriber) -> None:
        """Register *handler* to receive every event of *event_type* (or its subclasses)."""
        self._subscribers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: type[Event], handler: Subscriber) -> None:
        """Best-effort removal. Silently no-ops if the handler was not registered."""
        handlers = self._subscribers.get(event_type)
        if handlers is None:
            return
        with contextlib.suppress(ValueError):
            handlers.remove(handler)

    async def publish(self, event: Event) -> None:
        """Deliver *event* to every matching subscriber concurrently.

        A subscriber matches if its registered type is exactly the event's type
        or any base class of it (so ``subscribe(Event, h)`` receives all events).
        """
        handlers: list[Subscriber] = []
        for event_type, subs in self._subscribers.items():
            if isinstance(event, event_type):
                handlers.extend(subs)

        if not handlers:
            return

        results = await asyncio.gather(
            *(self._invoke(h, event) for h in handlers),
            return_exceptions=True,
        )
        for result, handler in zip(results, handlers, strict=True):
            if isinstance(result, BaseException):
                self._log.warning(
                    "event_subscriber_failed",
                    event_type=type(event).__name__,
                    handler=getattr(handler, "__qualname__", repr(handler)),
                    error=repr(result),
                )

    async def _invoke(self, handler: Subscriber, event: Event) -> None:
        await handler(event)
