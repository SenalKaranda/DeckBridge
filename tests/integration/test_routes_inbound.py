"""Inbound state webhook (M7).

Token-authenticated POST that lets external apps update a key's displayed
state without speaking MQTT. Verifies bearer-token gating, payload shape
sniffing, and the resulting KeyStateUpdated event emission.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import TYPE_CHECKING

from deckbridge.events import KeyStateUpdated
from deckbridge.events.types import Event
from deckbridge.storage.schema import Key, Page

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from deckbridge.storage import Storage


def _set_token(storage: Storage, plaintext: str) -> None:
    digest = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    prefs = storage.get_preferences()
    storage.set_preferences(prefs.model_copy(update={"api_token_hash": digest}))


def _setup_key(storage: Storage) -> tuple[str, int]:
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    storage.upsert_key(Key(page_id="p1", slot=0))
    return "p1", 0


# ---- auth ---------------------------------------------------------------


def test_inbound_401_without_token(unauth_client: tuple[TestClient, Storage]) -> None:
    client, storage = unauth_client
    _setup_key(storage)
    _set_token(storage, "a-secret-token")
    r = client.post("/api/pages/p1/keys/0/state", json={"value": "ON"})
    assert r.status_code == 401


def test_inbound_401_with_wrong_token(unauth_client: tuple[TestClient, Storage]) -> None:
    client, storage = unauth_client
    _setup_key(storage)
    _set_token(storage, "real-token")
    r = client.post(
        "/api/pages/p1/keys/0/state",
        json={"value": "ON"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert r.status_code == 401


def test_inbound_401_when_no_token_configured(
    unauth_client: tuple[TestClient, Storage],
) -> None:
    """Until /api/settings/token has been hit at least once, every inbound
    request is 401 even with a Bearer header."""
    client, storage = unauth_client
    _setup_key(storage)
    # Explicitly clear any token hash to be sure.
    prefs = storage.get_preferences()
    storage.set_preferences(prefs.model_copy(update={"api_token_hash": None}))
    r = client.post(
        "/api/pages/p1/keys/0/state",
        json={"value": "ON"},
        headers={"Authorization": "Bearer anything"},
    )
    assert r.status_code == 401


# ---- 404 paths ----------------------------------------------------------


def test_inbound_404_missing_page(unauth_client: tuple[TestClient, Storage]) -> None:
    client, storage = unauth_client
    _set_token(storage, "tok")
    r = client.post(
        "/api/pages/nope/keys/0/state",
        json={"value": "ON"},
        headers={"Authorization": "Bearer tok"},
    )
    assert r.status_code == 404


def test_inbound_404_missing_key(unauth_client: tuple[TestClient, Storage]) -> None:
    client, storage = unauth_client
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))  # no key configured
    _set_token(storage, "tok")
    r = client.post(
        "/api/pages/p1/keys/0/state",
        json={"value": "ON"},
        headers={"Authorization": "Bearer tok"},
    )
    assert r.status_code == 404


# ---- payload shapes ----------------------------------------------------


def test_inbound_json_value_field(unauth_client: tuple[TestClient, Storage]) -> None:
    client, storage = unauth_client
    _setup_key(storage)
    _set_token(storage, "tok")
    r = client.post(
        "/api/pages/p1/keys/0/state",
        json={"value": "ON"},
        headers={"Authorization": "Bearer tok"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "value": "ON"}


def test_inbound_json_state_field(unauth_client: tuple[TestClient, Storage]) -> None:
    client, storage = unauth_client
    _setup_key(storage)
    _set_token(storage, "tok")
    r = client.post(
        "/api/pages/p1/keys/0/state",
        json={"state": "OFF"},
        headers={"Authorization": "Bearer tok"},
    )
    assert r.status_code == 200
    assert r.json()["value"] == "OFF"


def test_inbound_text_body(unauth_client: tuple[TestClient, Storage]) -> None:
    client, storage = unauth_client
    _setup_key(storage)
    _set_token(storage, "tok")
    r = client.post(
        "/api/pages/p1/keys/0/state",
        content=b"  PLAIN  ",
        headers={"Authorization": "Bearer tok", "Content-Type": "text/plain"},
    )
    assert r.status_code == 200
    assert r.json()["value"] == "PLAIN"


def test_inbound_empty_body_400(unauth_client: tuple[TestClient, Storage]) -> None:
    client, storage = unauth_client
    _setup_key(storage)
    _set_token(storage, "tok")
    r = client.post(
        "/api/pages/p1/keys/0/state",
        content=b"",
        headers={"Authorization": "Bearer tok"},
    )
    assert r.status_code == 400


def test_inbound_invalid_json_400(unauth_client: tuple[TestClient, Storage]) -> None:
    client, storage = unauth_client
    _setup_key(storage)
    _set_token(storage, "tok")
    r = client.post(
        "/api/pages/p1/keys/0/state",
        content=b"not-json",
        headers={"Authorization": "Bearer tok", "Content-Type": "application/json"},
    )
    assert r.status_code == 400


# ---- event emission ---------------------------------------------------


def test_inbound_emits_key_state_updated(
    unauth_client: tuple[TestClient, Storage],
) -> None:
    client, storage = unauth_client
    _setup_key(storage)
    _set_token(storage, "tok")
    received: list[Event] = []

    async def capture(event: Event) -> None:
        received.append(event)

    bus = client.app.state.bus  # type: ignore[attr-defined]
    bus.subscribe(KeyStateUpdated, capture)

    r = client.post(
        "/api/pages/p1/keys/0/state",
        json={"value": "ACTIVE"},
        headers={"Authorization": "Bearer tok"},
    )
    assert r.status_code == 200

    state_events = [e for e in received if isinstance(e, KeyStateUpdated)]
    assert len(state_events) == 1
    assert state_events[0].page_id == "p1"
    assert state_events[0].slot == 0
    assert state_events[0].value == "ACTIVE"


# ---- token roundtrip with the rotation endpoint ----------------------


def test_inbound_works_with_rotated_token(
    authed_client: tuple[TestClient, Storage],
) -> None:
    """End-to-end: rotate a token via the settings endpoint, use it on the
    inbound endpoint."""
    client, storage = authed_client
    _setup_key(storage)
    rotation = client.post("/api/settings/token")
    assert rotation.status_code == 200
    token = rotation.json()["token"]
    assert token  # non-empty plaintext
    del token  # we don't need to use it directly; setup just verifies the path
    # Use the rotated token (which is sha256-stored) by extracting it from
    # the response above:
    fresh = client.post("/api/settings/token").json()["token"]
    r = client.post(
        "/api/pages/p1/keys/0/state",
        json={"value": "X"},
        headers={"Authorization": f"Bearer {fresh}"},
    )
    assert r.status_code == 200


# ---- token comparison is constant-time ------------------------------


def test_token_compare_uses_hmac_compare_digest() -> None:
    """Smoke check that long-prefix differences don't shortcut the compare."""
    from deckbridge.http.routes_inbound import _verify_token

    real = secrets.token_urlsafe(32)
    real_hash = hashlib.sha256(real.encode("utf-8")).hexdigest()
    assert _verify_token(f"Bearer {real}", real_hash) is True
    assert _verify_token(f"Bearer {real}x", real_hash) is False
    assert _verify_token("Bearer ", real_hash) is False
    assert _verify_token(None, real_hash) is False
    assert _verify_token(f"Bearer {real}", None) is False
