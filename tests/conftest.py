"""Shared pytest fixtures for DeckBridge."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Allow `from tests.fixtures.fake_deck import ...` from any test module.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---- shared app + auth fixtures ------------------------------------------

TEST_PASSWORD = "test-password-strong"
TEST_SESSION_SECRET = "test-secret-key-32bytes-or-more!"


@pytest.fixture
def authed_app(tmp_path: Path) -> tuple[FastAPI, object]:
    """Build an app with a hermetic in-memory storage and a known password.

    Returns ``(app, storage)``. The password is :data:`TEST_PASSWORD`.
    """
    from deckbridge.events import EventBus
    from deckbridge.http import create_app
    from deckbridge.http.auth import hash_password
    from deckbridge.settings import Settings
    from deckbridge.storage import SqliteStorage, run_migrations

    settings = Settings(
        data_dir=tmp_path,
        session_secret_key=TEST_SESSION_SECRET,
    )
    storage = SqliteStorage(":memory:")
    run_migrations(storage)
    storage.set_preferences(
        storage.get_preferences().model_copy(update={"password_hash": hash_password(TEST_PASSWORD)})
    )
    app = create_app(
        settings=settings,
        bus=EventBus(),
        discoverer=lambda: [],
        storage=storage,
    )
    return app, storage


@pytest.fixture
def authed_client(authed_app: tuple[FastAPI, object]) -> Iterator[tuple[TestClient, object]]:
    """A TestClient that's already logged in. Yields ``(client, storage)``."""
    app, storage = authed_app
    with TestClient(app) as client:
        r = client.post("/api/login", json={"password": TEST_PASSWORD})
        assert r.status_code == 200, r.text
        yield client, storage


@pytest.fixture
def unauth_client(authed_app: tuple[FastAPI, object]) -> Iterator[tuple[TestClient, object]]:
    """A TestClient on the same app, but NOT logged in. For 401 assertions."""
    app, storage = authed_app
    with TestClient(app) as client:
        yield client, storage
