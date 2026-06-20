"""Inbound state webhook (M7).

    POST /api/pages/{page_id}/keys/{slot}/state
        Authorization: Bearer <token-from-/api/settings/token>

Lets external apps update a key's displayed state without speaking MQTT.
Accepts three payload shapes (Content-Type sniffed):

    application/json  with body ``{"value": "ON"}`` or ``{"state": "ON"}``
    text/*            with body ``ON``  (whole body trimmed and used as value)
    anything else     with body ``ON``  (treated as text/plain)

The resolved value emits a :class:`~deckbridge.events.KeyStateUpdated` event
identical in shape to what the MQTT state subscriber emits — the painter
re-renders the affected key automatically.

Token is checked via constant-time sha256 compare against
``Preferences.api_token_hash``. Missing or mismatched token is a 401, no
information leak about whether the key/page exists.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from deckbridge.events.types import KeyStateUpdated
from deckbridge.logging_ import get_logger

router = APIRouter(prefix="/api/pages", tags=["inbound"])

log = get_logger(__name__)


class InboundStateResponse(BaseModel):
    ok: bool
    value: str


def _verify_token(authorization: str | None, expected_hash: str | None) -> bool:
    if not expected_hash or not authorization:
        return False
    if not authorization.startswith("Bearer "):
        return False
    token = authorization[len("Bearer ") :]
    if not token:
        return False
    actual_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return hmac.compare_digest(actual_hash, expected_hash)


def _extract_value(content_type: str, body: bytes) -> str | None:
    """Return the resolved state value or None if the payload was unusable."""
    if not body:
        return None
    if "json" in content_type.lower():
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict):
            for field in ("value", "state"):
                if field in data and data[field] is not None:
                    return str(data[field]).strip() or None
            return None
        return str(data).strip() or None
    return body.decode("utf-8", errors="replace").strip() or None


@router.post(
    "/{page_id}/keys/{slot}/state",
    response_model=InboundStateResponse,
)
async def update_key_state(
    page_id: str,
    slot: int,
    request: Request,
    authorization: str | None = Header(default=None),
) -> InboundStateResponse:
    storage = request.app.state.storage
    expected_hash = storage.get_preferences().api_token_hash
    if not _verify_token(authorization, expected_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing token")

    if storage.get_page(page_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "page not found")
    if storage.get_key(page_id, slot) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "key not found")

    body = await request.body()
    content_type = request.headers.get("content-type", "")
    value = _extract_value(content_type, body)
    if value is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "could not extract a value from the body")

    bus = request.app.state.bus
    await bus.publish(KeyStateUpdated(page_id=page_id, slot=slot, value=value))
    log.info("inbound_state", page_id=page_id, slot=slot, value=value)
    return InboundStateResponse(ok=True, value=value)
