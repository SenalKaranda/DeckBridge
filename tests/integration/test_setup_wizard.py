"""First-run setup wizard endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from deckbridge.events import EventBus
from deckbridge.http import create_app
from deckbridge.http.auth import hash_password
from deckbridge.settings import Settings
from deckbridge.storage import SqliteStorage, run_migrations


def _build_app(tmp_path: Path) -> tuple[object, SqliteStorage]:
    settings = Settings(
        data_dir=tmp_path,
        session_secret_key="test-secret-key-32bytes-or-more!",
    )
    storage = SqliteStorage(":memory:")
    run_migrations(storage)
    app = create_app(
        settings=settings,
        bus=EventBus(),
        discoverer=lambda: [],
        storage=storage,
    )
    return app, storage


def test_setup_needed_initially_true(tmp_path: Path) -> None:
    app, _ = _build_app(tmp_path)
    with TestClient(app) as client:  # type: ignore[arg-type]
        r = client.get("/api/setup/needed")
        assert r.status_code == 200
        assert r.json() == {"needed": True}


def test_setup_complete_sets_password_and_logs_in(tmp_path: Path) -> None:
    app, storage = _build_app(tmp_path)
    with TestClient(app) as client:  # type: ignore[arg-type]
        r = client.post("/api/setup/complete", json={"password": "hunter2-strong"})
        assert r.status_code == 201, r.text
        # Password is hashed in storage.
        prefs = storage.get_preferences()
        assert prefs.password_hash is not None
        assert prefs.password_hash.startswith("$argon2")
        # Setup is no longer needed after completion.
        assert client.get("/api/setup/needed").json() == {"needed": False}
        # And the user is auto-logged-in.
        assert client.get("/api/me").status_code == 200


def test_setup_complete_rejects_when_already_set(tmp_path: Path) -> None:
    app, storage = _build_app(tmp_path)
    storage.set_preferences(
        storage.get_preferences().model_copy(update={"password_hash": hash_password("existing")})
    )
    with TestClient(app) as client:  # type: ignore[arg-type]
        r = client.post("/api/setup/complete", json={"password": "second-attempt"})
        assert r.status_code == 409


def test_setup_complete_rejects_short_password(tmp_path: Path) -> None:
    app, _ = _build_app(tmp_path)
    with TestClient(app) as client:  # type: ignore[arg-type]
        r = client.post("/api/setup/complete", json={"password": "abc"})  # < min_length
        assert r.status_code == 422


def test_setup_needed_endpoint_is_unauthenticated(tmp_path: Path) -> None:
    """The frontend hits this on first load, before any session exists."""
    app, _ = _build_app(tmp_path)
    with TestClient(app) as client:  # type: ignore[arg-type]
        r = client.get("/api/setup/needed")
        assert r.status_code == 200
