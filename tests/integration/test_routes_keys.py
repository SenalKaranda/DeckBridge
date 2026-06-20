"""HTTP API for /api/pages/{page_id}/keys/{slot} — key CRUD."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from deckbridge.storage import Storage


def _make_page(client: TestClient) -> str:
    return client.post("/api/pages", json={"deck_serial": "DECK"}).json()["id"]


def test_put_key_with_minimal_body(authed_client: tuple[TestClient, Storage]) -> None:
    client, _ = authed_client
    pid = _make_page(client)
    r = client.put(f"/api/pages/{pid}/keys/0", json={})
    assert r.status_code == 200, r.text
    key = r.json()
    assert key["page_id"] == pid
    assert key["slot"] == 0
    assert key["label"] == ""
    assert key["press"]["type"] == "no_op"


def test_put_key_with_full_body(authed_client: tuple[TestClient, Storage]) -> None:
    client, _ = authed_client
    pid = _make_page(client)
    body = {
        "label": "Kitchen",
        "icon_id": "lucide:lightbulb",
        "press": {
            "type": "mqtt_publish",
            "topic": "home/kitchen/light/set",
            "payload": "TOGGLE",
        },
        "state": {
            "topic": "home/kitchen/light/state",
            "jmespath": "state",
            "icon_map": {"on": "lucide:lightbulb", "off": "lucide:lightbulb-off"},
        },
    }
    r = client.put(f"/api/pages/{pid}/keys/3", json=body)
    assert r.status_code == 200, r.text
    key = r.json()
    assert key["label"] == "Kitchen"
    assert key["press"]["type"] == "mqtt_publish"
    assert key["press"]["topic"] == "home/kitchen/light/set"
    assert key["state"]["jmespath"] == "state"


def test_put_key_with_v1_1_presentation_fields(
    authed_client: tuple[TestClient, Storage],
) -> None:
    """Regression: KeyBody (the request body) and Key (the storage model)
    must stay in sync. v1.1.0 shipped with the new fields on Key but not on
    KeyBody, so saves with padding/show_*/colors/bg_image were rejected
    with 422 extra_forbidden. The PUT handler also forwards via
    `**payload.model_dump()` instead of hand-listing fields, so this test
    guards the full chain."""
    client, _ = authed_client
    pid = _make_page(client)
    body = {
        "label": "Lamp",
        "icon_id": "lucide:lightbulb",
        "padding": 6,
        "show_icon": True,
        "show_label": False,
        "bg_color": "#1a2b3c",
        "bg_image_id": None,
        "label_color": "#ff00ff",
        "icon_color": "#00ff00",
        "font_size": 18,
    }
    r = client.put(f"/api/pages/{pid}/keys/0", json=body)
    assert r.status_code == 200, r.text
    key = r.json()
    assert key["padding"] == 6
    assert key["show_icon"] is True
    assert key["show_label"] is False
    assert key["bg_color"] == "#1a2b3c"
    assert key["bg_image_id"] is None
    assert key["label_color"] == "#ff00ff"
    assert key["icon_color"] == "#00ff00"
    assert key["font_size"] == 18
    # Round-trip via GET to confirm it actually persisted.
    fetched = client.get(f"/api/pages/{pid}/keys/0").json()
    assert fetched == key


def test_put_key_overwrites_existing_slot(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    pid = _make_page(client)
    client.put(f"/api/pages/{pid}/keys/0", json={"label": "first"})
    client.put(f"/api/pages/{pid}/keys/0", json={"label": "second"})
    keys = client.get(f"/api/pages/{pid}/keys").json()
    assert len(keys) == 1
    assert keys[0]["label"] == "second"


def test_put_key_for_missing_page_404(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    r = client.put("/api/pages/nope/keys/0", json={})
    assert r.status_code == 404


def test_put_key_rejects_out_of_range_slot(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    pid = _make_page(client)
    r = client.put(f"/api/pages/{pid}/keys/99", json={})
    assert r.status_code == 422


def test_get_key(authed_client: tuple[TestClient, Storage]) -> None:
    client, _ = authed_client
    pid = _make_page(client)
    client.put(f"/api/pages/{pid}/keys/2", json={"label": "X"})
    r = client.get(f"/api/pages/{pid}/keys/2")
    assert r.status_code == 200
    assert r.json()["label"] == "X"


def test_get_missing_key_404(authed_client: tuple[TestClient, Storage]) -> None:
    client, _ = authed_client
    pid = _make_page(client)
    r = client.get(f"/api/pages/{pid}/keys/0")
    assert r.status_code == 404


def test_get_key_on_missing_page_404(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    r = client.get("/api/pages/nope/keys/0")
    assert r.status_code == 404


def test_delete_key(authed_client: tuple[TestClient, Storage]) -> None:
    client, _ = authed_client
    pid = _make_page(client)
    client.put(f"/api/pages/{pid}/keys/0", json={})
    r = client.delete(f"/api/pages/{pid}/keys/0")
    assert r.status_code == 204
    assert client.get(f"/api/pages/{pid}/keys/0").status_code == 404


def test_delete_missing_key_404(authed_client: tuple[TestClient, Storage]) -> None:
    client, _ = authed_client
    pid = _make_page(client)
    r = client.delete(f"/api/pages/{pid}/keys/0")
    assert r.status_code == 404


def test_keys_routes_require_auth(unauth_client: tuple[TestClient, Storage]) -> None:
    client, _ = unauth_client
    assert client.get("/api/pages/x/keys/0").status_code == 401
    assert client.put("/api/pages/x/keys/0", json={}).status_code == 401
    assert client.delete("/api/pages/x/keys/0").status_code == 401


def test_put_key_rejects_unknown_press_type(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    pid = _make_page(client)
    r = client.put(
        f"/api/pages/{pid}/keys/0",
        json={"press": {"type": "explode", "topic": "x"}},
    )
    assert r.status_code == 422
