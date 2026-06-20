"""Settings endpoints — preferences GET/PATCH, password change, token rotation."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from deckbridge.storage import Storage


# ---- preferences GET / PATCH --------------------------------------------


def test_get_settings_returns_defaults(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["mqtt_host"] is None
    assert body["mqtt_port"] == 1883
    assert body["ha_discovery_enabled"] is True
    assert body["has_api_token"] is False
    # Hashes never leak through this endpoint.
    assert "password_hash" not in body
    assert "api_token_hash" not in body


def test_patch_settings_updates_broker(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, storage = authed_client
    r = client.patch(
        "/api/settings",
        json={"mqtt_host": "broker.lan", "mqtt_port": 8883, "mqtt_tls": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mqtt_host"] == "broker.lan"
    assert body["mqtt_port"] == 8883
    assert body["mqtt_tls"] is True
    # Persisted in storage.
    prefs = storage.get_preferences()
    assert prefs.mqtt_host == "broker.lan"
    assert prefs.mqtt_port == 8883


def test_patch_settings_partial_leaves_other_fields(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    client.patch("/api/settings", json={"mqtt_host": "first"})
    r = client.patch("/api/settings", json={"ha_discovery_enabled": False})
    assert r.status_code == 200
    body = r.json()
    assert body["mqtt_host"] == "first"
    assert body["ha_discovery_enabled"] is False


def test_patch_settings_rejects_unknown_field(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    r = client.patch("/api/settings", json={"some_random_field": True})
    assert r.status_code == 422


# ---- password change ----------------------------------------------------


def test_password_change_requires_auth(
    unauth_client: tuple[TestClient, Storage],
) -> None:
    client, _ = unauth_client
    r = client.post(
        "/api/settings/password",
        json={"current_password": "x", "new_password": "y" * 9},
    )
    assert r.status_code == 401


def test_password_change_succeeds(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    r = client.post(
        "/api/settings/password",
        json={"current_password": "test-password-strong", "new_password": "new-strong-pw"},
    )
    assert r.status_code == 200, r.text
    # Old password no longer works.
    client.post("/api/logout")
    bad = client.post("/api/login", json={"password": "test-password-strong"})
    assert bad.status_code == 401
    good = client.post("/api/login", json={"password": "new-strong-pw"})
    assert good.status_code == 200


def test_password_change_rejects_wrong_current(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    r = client.post(
        "/api/settings/password",
        json={"current_password": "wrong", "new_password": "new-strong-pw"},
    )
    assert r.status_code == 401


def test_password_change_rejects_short_new(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    r = client.post(
        "/api/settings/password",
        json={"current_password": "test-password-strong", "new_password": "tiny"},
    )
    assert r.status_code == 422


# ---- token rotation -----------------------------------------------------


def test_token_rotation_returns_plaintext_and_persists_hash(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, storage = authed_client
    r = client.post("/api/settings/token")
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    assert len(token) >= 32
    expected_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    prefs = storage.get_preferences()
    assert prefs.api_token_hash == expected_hash


def test_token_rotation_replaces_previous(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, storage = authed_client
    first = client.post("/api/settings/token").json()["token"]
    second = client.post("/api/settings/token").json()["token"]
    assert first != second
    expected = hashlib.sha256(second.encode("utf-8")).hexdigest()
    assert storage.get_preferences().api_token_hash == expected


def test_settings_get_reflects_token_presence(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    assert client.get("/api/settings").json()["has_api_token"] is False
    client.post("/api/settings/token")
    assert client.get("/api/settings").json()["has_api_token"] is True


def test_token_rotation_requires_auth(
    unauth_client: tuple[TestClient, Storage],
) -> None:
    client, _ = unauth_client
    assert client.post("/api/settings/token").status_code == 401
