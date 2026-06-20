"""WebSocket /ws — log stream + lightweight event push for the diagnostics tab.

Wire shape (every frame is a single JSON line):

    {"kind": "log",   "record": "<rendered structlog json string>"}
    {"kind": "event", "type": "<EventClassName>", "payload": {...}}

The ``log`` channel hands the connecting client every record currently in
the ringbuffer (catch-up), then streams new ones as they arrive. The
``event`` channel pushes select bus events (deck-attached/detached,
broker-connected/disconnected) so the diagnostics page can show real-time
state without polling /api/status.

Auth: same session cookie as the rest of the API. Unauthenticated handshake
is closed immediately with policy code 1008.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from deckbridge.events.types import (
    BrokerConnected,
    BrokerDisconnected,
    DeckConnected,
    DeckDisconnected,
    Event,
)
from deckbridge.http.auth import is_authenticated
from deckbridge.logging_ import get_logger as _get_logger
from deckbridge.logging_ import get_ringbuffer

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from deckbridge.events import EventBus

router = APIRouter()
log = _get_logger(__name__)

_PUSHED_EVENT_TYPES: tuple[type[Event], ...] = (
    DeckConnected,
    DeckDisconnected,
    BrokerConnected,
    BrokerDisconnected,
)


@router.websocket("/ws")
async def diagnostics_ws(websocket: WebSocket) -> None:
    if not is_authenticated(websocket):
        # Starlette: code 1008 = policy violation. Refuse before accept.
        await websocket.close(code=1008)
        return
    await websocket.accept()

    bus: EventBus = websocket.app.state.bus
    ringbuffer = get_ringbuffer()

    log_queue = ringbuffer.subscribe()
    event_queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=200)

    async def on_event(event: Event) -> None:
        # Diagnostics is best-effort: drop the event if a slow consumer fell
        # behind rather than back-pressuring the bus.
        with contextlib.suppress(asyncio.QueueFull):
            event_queue.put_nowait(event)

    handlers: list[tuple[type[Event], Callable[[Event], Awaitable[None]]]] = [
        (et, on_event) for et in _PUSHED_EVENT_TYPES
    ]
    for event_type, handler in handlers:
        bus.subscribe(event_type, handler)

    # Catch-up: push the current ringbuffer snapshot before streaming.
    try:
        for record in ringbuffer.snapshot():
            await websocket.send_text(json.dumps({"kind": "log", "record": record}))

        # Two pumps: log queue and event queue. Whichever fires first sends.
        log_pump = asyncio.create_task(_pump_logs(log_queue, websocket))
        event_pump = asyncio.create_task(_pump_events(event_queue, websocket))
        try:
            done, _ = await asyncio.wait(
                {log_pump, event_pump}, return_when=asyncio.FIRST_COMPLETED
            )
            for t in done:
                if t.exception() and not isinstance(t.exception(), WebSocketDisconnect):
                    raise t.exception()  # type: ignore[misc]
        finally:
            for t in (log_pump, event_pump):
                if not t.done():
                    t.cancel()
            for t in (log_pump, event_pump):
                with contextlib.suppress(asyncio.CancelledError, BaseException):
                    await t
    except WebSocketDisconnect:
        pass
    finally:
        for event_type, handler in handlers:
            bus.unsubscribe(event_type, handler)
        ringbuffer.unsubscribe(log_queue)


async def _pump_logs(queue: asyncio.Queue[str], ws: WebSocket) -> None:
    while True:
        record = await queue.get()
        await ws.send_text(json.dumps({"kind": "log", "record": record}))


async def _pump_events(queue: asyncio.Queue[Event], ws: WebSocket) -> None:
    while True:
        event = await queue.get()
        payload = _event_payload(event)
        await ws.send_text(
            json.dumps({"kind": "event", "type": type(event).__name__, "payload": payload})
        )


def _event_payload(event: Event) -> dict[str, Any]:
    if is_dataclass(event):
        return asdict(event)
    return {}
