"""Login, logout, and whoami round-trips."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from deckbridge.events import EventBus
from deckbridge.http import create_app
from deckbridge.http.auth import hash_password
from deckbridge.settings import Settings
from deckbridge.storage import SqliteStorage, run_migrations


def _build_app_with_password(tmp_path: Path, password: str) -> object:
    settings = Settings(
        data_dir=tmp_path,
        session_secret_key="test-secret-key-32bytes-or-more!",
    )
    storage = SqliteStorage(":memory:")
    run_migrations(storage)
    storage.set_preferences(
        storage.get_preferences().model_copy(update={"password_hash": hash_password(password)})
    )
    return create_app(
        settings=settings,
        bus=EventBus(),
        discoverer=lambda: [],
        storage=storage,
    )


def test_login_409_when_setup_not_complete(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, session_secret_key="test-secret-key-32bytes-or-more!")
    storage = SqliteStorage(":memory:")
    run_migrations(storage)
    app = create_app(settings=settings, bus=EventBus(), discoverer=lambda: [], storage=storage)
    with TestClient(app) as client:
        r = client.post("/api/login", json={"password": "anything"})
        assert r.status_code == 409


def test_login_with_correct_password_sets_session(tmp_path: Path) -> None:
    app = _build_app_with_password(tmp_path, "correct-pw")
    with TestClient(app) as client:  # type: ignore[arg-type]
        login = client.post("/api/login", json={"password": "correct-pw"})
        assert login.status_code == 200
        assert login.json() == {"ok": True}
        assert client.get("/api/me").status_code == 200


def test_login_with_wrong_password_returns_401(tmp_path: Path) -> None:
    app = _build_app_with_password(tmp_path, "real-pw")
    with TestClient(app) as client:  # type: ignore[arg-type]
        r = client.post("/api/login", json={"password": "wrong-pw"})
        assert r.status_code == 401


def test_logout_clears_session(tmp_path: Path) -> None:
    app = _build_app_with_password(tmp_path, "pw")
    with TestClient(app) as client:  # type: ignore[arg-type]
        client.post("/api/login", json={"password": "pw"})
        assert client.get("/api/me").status_code == 200
        out = client.post("/api/logout")
        assert out.status_code == 200
        assert client.get("/api/me").status_code == 401


def test_me_requires_auth(tmp_path: Path) -> None:
    app = _build_app_with_password(tmp_path, "pw")
    with TestClient(app) as client:  # type: ignore[arg-type]
        assert client.get("/api/me").status_code == 401


def test_logout_requires_auth(tmp_path: Path) -> None:
    """Logging out unauthenticated is a 401, not a silent success."""
    app = _build_app_with_password(tmp_path, "pw")
    with TestClient(app) as client:  # type: ignore[arg-type]
        assert client.post("/api/logout").status_code == 401
