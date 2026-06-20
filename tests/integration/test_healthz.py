"""End-to-end health endpoint check via FastAPI's TestClient.

Exercises the M1 vertical slice: ``create_app`` builds an app, the lifespan
fires :class:`DaemonStarted`, the healthz route returns a well-formed JSON
body. If this passes, the architecture is wired correctly.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from deckbridge import __version__
from deckbridge.events import Event, EventBus
from deckbridge.http import create_app
from deckbridge.settings import Settings
from deckbridge.storage import SqliteStorage


def test_healthz_returns_ok_with_version() -> None:
    app = create_app(
        settings=Settings(),
        bus=EventBus(),
        discoverer=lambda: [],
        storage=SqliteStorage(":memory:"),
    )
    with TestClient(app) as client:
        response = client.get("/api/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_lifespan_publishes_started_and_stopping_events() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def collect(event: Event) -> None:
        received.append(event)

    bus.subscribe(Event, collect)

    app = create_app(settings=Settings(), bus=bus)
    with TestClient(app) as client:
        # Hitting any route forces lifespan startup to complete.
        client.get("/api/healthz")

    types = [type(e).__name__ for e in received]
    assert "DaemonStarted" in types
    assert "DaemonStopping" in types


def test_openapi_schema_served() -> None:
    """The OpenAPI schema is served at /api/openapi.json (the SPA owns /)."""
    app = create_app(
        settings=Settings(),
        bus=EventBus(),
        discoverer=lambda: [],
        storage=SqliteStorage(":memory:"),
    )
    with TestClient(app) as client:
        response = client.get("/api/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "DeckBridge"
    assert "/api/healthz" in schema["paths"]


def test_swagger_relocated_under_api_docs() -> None:
    """Swagger lives under /api/docs so / stays reserved for the SPA mount.

    The exact behavior of /docs depends on whether the SPA has been built:
      - SPA built (production): /docs returns the SPA index.html (HTML), and
        the SvelteKit router decides what to render.
      - SPA not built: /docs returns 404 (no SPA mount).
    Either way, /docs MUST NOT return Swagger UI's distinctive markup.
    """
    app = create_app(
        settings=Settings(),
        bus=EventBus(),
        discoverer=lambda: [],
        storage=SqliteStorage(":memory:"),
    )
    with TestClient(app) as client:
        docs = client.get("/docs")
        api_docs = client.get("/api/docs")

    # /docs is not Swagger — either 404 (no SPA) or SPA HTML (built).
    if docs.status_code == 200:
        assert "swagger-ui" not in docs.text.lower()
    else:
        assert docs.status_code == 404

    # /api/docs IS Swagger when the schema is reachable.
    assert api_docs.status_code == 200
    assert "swagger-ui" in api_docs.text.lower()
