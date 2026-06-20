"""HTTP API for /api/icons — upload, list, raw bytes, delete."""

from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from deckbridge.events import EventBus
from deckbridge.http import create_app
from deckbridge.http.auth import hash_password
from deckbridge.settings import Settings
from deckbridge.storage import SqliteStorage, run_migrations
from deckbridge.storage.schema import Icon, IconSource

_TEST_PASSWORD = "icons-test-password"


def _png_bytes(color: tuple[int, int, int] = (50, 100, 150)) -> bytes:
    img = Image.new("RGB", (20, 20), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_app(tmp_path: Path) -> tuple[object, SqliteStorage]:
    """Build a fully-wired app with auth pre-configured (password = _TEST_PASSWORD)."""
    settings = Settings(
        data_dir=tmp_path,
        session_secret_key="test-secret-key-32bytes-or-more!",
    )
    storage = SqliteStorage(":memory:")
    run_migrations(storage)
    prefs = storage.get_preferences()
    storage.set_preferences(
        prefs.model_copy(update={"password_hash": hash_password(_TEST_PASSWORD)})
    )
    app = create_app(
        settings=settings,
        bus=EventBus(),
        discoverer=lambda: [],
        storage=storage,
    )
    return app, storage


def _login(client: TestClient) -> None:
    r = client.post("/api/login", json={"password": _TEST_PASSWORD})
    assert r.status_code == 200, r.text


def test_upload_then_list_then_get_raw(tmp_path: Path) -> None:
    app, _ = _build_app(tmp_path)
    raw = _png_bytes()

    with TestClient(app) as client:  # type: ignore[arg-type]
        _login(client)
        post = client.post(
            "/api/icons",
            files={"file": ("kitchen.png", raw, "image/png")},
            data={"name": "Kitchen"},
        )
        assert post.status_code == 201, post.text
        body = post.json()
        assert body["name"] == "Kitchen"
        assert body["source"] == "uploaded"
        icon_id = body["id"]

        listing = client.get("/api/icons")
        assert listing.status_code == 200
        assert any(i["id"] == icon_id for i in listing.json())

        single = client.get(f"/api/icons/{icon_id}")
        assert single.status_code == 200
        assert single.json()["id"] == icon_id

        raw_response = client.get(f"/api/icons/{icon_id}/raw")
        assert raw_response.status_code == 200
        assert raw_response.headers["content-type"] == "image/png"
        assert raw_response.content == raw


def test_upload_dedupes_by_sha256(tmp_path: Path) -> None:
    app, _ = _build_app(tmp_path)
    raw = _png_bytes((1, 2, 3))
    with TestClient(app) as client:  # type: ignore[arg-type]
        _login(client)
        first = client.post("/api/icons", files={"file": ("a.png", raw, "image/png")})
        second = client.post("/api/icons", files={"file": ("b.png", raw, "image/png")})
        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["id"] == second.json()["id"]


def test_upload_rejects_invalid_content_type(tmp_path: Path) -> None:
    app, _ = _build_app(tmp_path)
    with TestClient(app) as client:  # type: ignore[arg-type]
        _login(client)
        r = client.post(
            "/api/icons",
            files={"file": ("x.gif", b"GIF89a fake", "image/gif")},
        )
        assert r.status_code == 400
        assert "Unsupported" in r.json()["detail"]


def test_get_missing_icon_returns_404(tmp_path: Path) -> None:
    app, _ = _build_app(tmp_path)
    with TestClient(app) as client:  # type: ignore[arg-type]
        _login(client)
        r = client.get("/api/icons/upl:nonexistent")
        assert r.status_code == 404


def test_get_missing_icon_raw_returns_404(tmp_path: Path) -> None:
    app, _ = _build_app(tmp_path)
    with TestClient(app) as client:  # type: ignore[arg-type]
        _login(client)
        r = client.get("/api/icons/upl:nope/raw")
        assert r.status_code == 404


def test_delete_uploaded_icon(tmp_path: Path) -> None:
    app, _ = _build_app(tmp_path)
    with TestClient(app) as client:  # type: ignore[arg-type]
        _login(client)
        post = client.post(
            "/api/icons",
            files={"file": ("x.png", _png_bytes(), "image/png")},
        )
        icon_id = post.json()["id"]
        delete = client.delete(f"/api/icons/{icon_id}")
        assert delete.status_code == 204
        assert client.get(f"/api/icons/{icon_id}").status_code == 404


def test_cannot_delete_bundled_icon(tmp_path: Path) -> None:
    app, storage = _build_app(tmp_path)
    storage.upsert_icon(Icon(id="lucide:home", source=IconSource.BUNDLED, reference="home"))
    with TestClient(app) as client:  # type: ignore[arg-type]
        _login(client)
        r = client.delete("/api/icons/lucide:home")
        assert r.status_code == 400
        assert "Bundled" in r.json()["detail"]


def test_delete_missing_icon_returns_404(tmp_path: Path) -> None:
    app, _ = _build_app(tmp_path)
    with TestClient(app) as client:  # type: ignore[arg-type]
        _login(client)
        r = client.delete("/api/icons/upl:nope")
        assert r.status_code == 404


def test_unauthenticated_requests_to_icons_return_401(tmp_path: Path) -> None:
    """No login -> all /api/icons requests get 401, even GETs."""
    app, _ = _build_app(tmp_path)
    with TestClient(app) as client:  # type: ignore[arg-type]
        assert client.get("/api/icons").status_code == 401
        assert client.get("/api/icons/anything").status_code == 401
        assert client.get("/api/icons/anything/raw").status_code == 401
        assert (
            client.post(
                "/api/icons", files={"file": ("x.png", _png_bytes(), "image/png")}
            ).status_code
            == 401
        )
        assert client.delete("/api/icons/x").status_code == 401
