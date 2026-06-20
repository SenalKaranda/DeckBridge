"""WebSocket /ws — auth gating, log catch-up, real-time push."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from deckbridge.storage import Storage


def test_ws_rejects_unauthenticated(unauth_client: tuple[TestClient, Storage]) -> None:
    import pytest
    from starlette.websockets import WebSocketDisconnect

    client, _ = unauth_client
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws"):
            pass
    assert exc_info.value.code == 1008


def test_ws_authenticated_session_streams_logs(
    authed_client: tuple[TestClient, Storage],
) -> None:
    """A logged-in client receives the catch-up snapshot on connect."""
    client, _ = authed_client
    # Generate at least one log line via a hit on /api/healthz.
    client.get("/api/healthz")

    from deckbridge.logging_ import get_ringbuffer

    # Make sure the buffer has at least one entry to send.
    get_ringbuffer().append('{"event":"ws_test_marker"}')

    with client.websocket_connect("/ws") as ws:
        # The first received message must be a JSON envelope with kind=log.
        message = ws.receive_text()
        envelope = json.loads(message)
        assert envelope["kind"] == "log"
        assert isinstance(envelope["record"], str)


def test_ws_pushes_subsequent_log_records(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    from deckbridge.logging_ import get_ringbuffer

    buf = get_ringbuffer()
    # Pre-clear-ish: snapshot is large; we just append a fresh sentinel and
    # consume until we see it.
    sentinel = '{"event":"ws_post_connect_sentinel"}'

    with client.websocket_connect("/ws") as ws:
        # Drain catch-up by reading non-blocking until we'd block.
        # TestClient WebSockets are sync; we just do a few reads then push.
        # Use a small drain loop with a budget.
        for _ in range(min(len(buf), 50)):
            try:
                ws.receive_text()
            except Exception:
                break
        buf.append(sentinel)
        # Now read until we find the sentinel envelope.
        for _ in range(20):
            envelope = json.loads(ws.receive_text())
            if envelope.get("kind") == "log" and "ws_post_connect_sentinel" in envelope["record"]:
                return
        raise AssertionError("did not see sentinel record on the WS")
