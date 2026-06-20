"""HTTP API for /api/pages — pages CRUD + nested keys listing."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from deckbridge.storage import Storage


def test_list_pages_initially_empty(authed_client: tuple[TestClient, Storage]) -> None:
    client, _ = authed_client
    r = client.get("/api/pages")
    assert r.status_code == 200
    assert r.json() == []


def test_create_page_assigns_uuid(authed_client: tuple[TestClient, Storage]) -> None:
    client, storage = authed_client
    r = client.post("/api/pages", json={"deck_serial": "ABC", "name": "Home"})
    assert r.status_code == 201, r.text
    page = r.json()
    assert page["deck_serial"] == "ABC"
    assert page["name"] == "Home"
    assert page["order"] == 0
    assert len(page["id"]) >= 32  # UUID-ish
    assert storage.get_page(page["id"]) is not None


def test_get_page_returns_existing(authed_client: tuple[TestClient, Storage]) -> None:
    client, _ = authed_client
    created = client.post("/api/pages", json={"deck_serial": "X"}).json()
    r = client.get(f"/api/pages/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_get_missing_page_404(authed_client: tuple[TestClient, Storage]) -> None:
    client, _ = authed_client
    r = client.get("/api/pages/nonexistent")
    assert r.status_code == 404


def test_patch_page_partial_update(authed_client: tuple[TestClient, Storage]) -> None:
    client, _ = authed_client
    created = client.post("/api/pages", json={"deck_serial": "X", "name": "Old", "order": 0}).json()
    r = client.patch(f"/api/pages/{created['id']}", json={"name": "New", "order": 5})
    assert r.status_code == 200
    page = r.json()
    assert page["name"] == "New"
    assert page["order"] == 5
    assert page["deck_serial"] == "X"  # untouched


def test_patch_missing_page_404(authed_client: tuple[TestClient, Storage]) -> None:
    client, _ = authed_client
    r = client.patch("/api/pages/nope", json={"name": "x"})
    assert r.status_code == 404


def test_patch_page_with_empty_body_is_noop(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    created = client.post("/api/pages", json={"deck_serial": "X", "name": "n"}).json()
    r = client.patch(f"/api/pages/{created['id']}", json={})
    assert r.status_code == 200
    assert r.json() == created


def test_delete_page_cascades_to_keys(authed_client: tuple[TestClient, Storage]) -> None:
    client, storage = authed_client
    page = client.post("/api/pages", json={"deck_serial": "X"}).json()
    pid = page["id"]
    # Add a key to verify cascade.
    client.put(f"/api/pages/{pid}/keys/0", json={"label": "K"})
    r = client.delete(f"/api/pages/{pid}")
    assert r.status_code == 204
    assert storage.get_page(pid) is None
    assert storage.list_keys(pid) == []


def test_delete_missing_page_404(authed_client: tuple[TestClient, Storage]) -> None:
    client, _ = authed_client
    r = client.delete("/api/pages/nope")
    assert r.status_code == 404


def test_list_pages_filtered_by_deck(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    client.post("/api/pages", json={"deck_serial": "A", "name": "p1"})
    client.post("/api/pages", json={"deck_serial": "A", "name": "p2"})
    client.post("/api/pages", json={"deck_serial": "B", "name": "p3"})

    a_pages = client.get("/api/pages", params={"deck_serial": "A"}).json()
    assert len(a_pages) == 2
    assert all(p["deck_serial"] == "A" for p in a_pages)

    all_pages = client.get("/api/pages").json()
    assert len(all_pages) == 3


def test_list_keys_for_existing_page(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    page = client.post("/api/pages", json={"deck_serial": "A"}).json()
    pid = page["id"]
    client.put(f"/api/pages/{pid}/keys/0", json={"label": "first"})
    client.put(f"/api/pages/{pid}/keys/3", json={"label": "third"})

    r = client.get(f"/api/pages/{pid}/keys")
    assert r.status_code == 200
    keys = r.json()
    assert [k["slot"] for k in keys] == [0, 3]


def test_list_keys_for_missing_page_404(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    assert client.get("/api/pages/nope/keys").status_code == 404


def test_pages_routes_require_auth(unauth_client: tuple[TestClient, Storage]) -> None:
    client, _ = unauth_client
    assert client.get("/api/pages").status_code == 401
    assert client.post("/api/pages", json={"deck_serial": "X"}).status_code == 401
    assert client.get("/api/pages/x").status_code == 401
    assert client.patch("/api/pages/x", json={}).status_code == 401
    assert client.delete("/api/pages/x").status_code == 401
    assert client.get("/api/pages/x/keys").status_code == 401
