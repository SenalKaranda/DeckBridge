"""Config export/import round-trips."""

from __future__ import annotations

from typing import TYPE_CHECKING

from deckbridge.storage.schema import Key, Page

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from deckbridge.storage import Storage


def test_export_returns_full_snapshot(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, storage = authed_client
    storage.upsert_page(Page(id="p1", deck_serial="ABC", name="Home"))
    storage.upsert_key(Key(page_id="p1", slot=0, label="Light"))

    r = client.post("/api/config/export")
    assert r.status_code == 200
    snap = r.json()
    assert snap["schema_version"] >= 1
    assert any(p["id"] == "p1" for p in snap["pages"])
    assert any(k["page_id"] == "p1" and k["slot"] == 0 for k in snap["keys"])


def test_export_requires_auth(unauth_client: tuple[TestClient, Storage]) -> None:
    client, _ = unauth_client
    assert client.post("/api/config/export").status_code == 401


def test_import_replaces_existing_data(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, storage = authed_client
    storage.upsert_page(Page(id="OLD", deck_serial="ABC"))
    payload = {
        "schema_version": 1,
        "preferences": {},
        "decks": [],
        "pages": [{"id": "NEW", "deck_serial": "XYZ", "name": "Imported", "order": 0}],
        "keys": [],
        "icons": [],
    }
    r = client.post("/api/config/import", json=payload)
    assert r.status_code == 200
    assert storage.get_page("OLD") is None
    assert storage.get_page("NEW") is not None


def test_import_invalid_shape_returns_422(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    r = client.post("/api/config/import", json={"unknown_top_level_field": True})
    assert r.status_code == 422


def test_export_then_import_round_trips(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, storage = authed_client
    storage.upsert_page(Page(id="p1", deck_serial="ABC", name="Home"))
    storage.upsert_key(Key(page_id="p1", slot=0, label="Light"))

    snap = client.post("/api/config/export").json()
    # Wipe and re-import.
    client.post(
        "/api/config/import",
        json={
            "schema_version": 1,
            "preferences": {},
            "decks": [],
            "pages": [],
            "keys": [],
            "icons": [],
        },
    )
    assert storage.get_page("p1") is None

    r = client.post("/api/config/import", json=snap)
    assert r.status_code == 200
    assert storage.get_page("p1") is not None
    assert storage.get_key("p1", 0) is not None


def test_import_requires_auth(unauth_client: tuple[TestClient, Storage]) -> None:
    client, _ = unauth_client
    r = client.post("/api/config/import", json={"schema_version": 1})
    assert r.status_code == 401
