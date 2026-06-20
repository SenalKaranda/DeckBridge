"""GET /api/status — version + attached decks + broker connectivity."""

from __future__ import annotations

from typing import TYPE_CHECKING

from deckbridge import __version__

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from deckbridge.storage import Storage


def test_status_requires_auth(unauth_client: tuple[TestClient, Storage]) -> None:
    client, _ = unauth_client
    assert client.get("/api/status").status_code == 401


def test_status_returns_version_and_empty_decks(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == __version__
    assert body["decks"] == []  # discoverer in fixture returns []
    assert body["broker_connected"] is False
