"""FastAPI application factory for DeckBridge.

The ``create_app`` function is the single entrypoint for both production
(``deckbridge run``) and tests (``TestClient(create_app(...))``). It wires:

    * the application :class:`~deckbridge.settings.Settings`
    * the in-process :class:`~deckbridge.events.EventBus`
    * route modules
    * lifespan hooks publishing :class:`DaemonStarted`/:class:`DaemonStopping`

All subsystems share a single bus per app instance, accessible at
``request.app.state.bus``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import httpx
from fastapi import Depends, FastAPI
from starlette.middleware.sessions import SessionMiddleware

from deckbridge import __version__
from deckbridge.actions import ActivePages, PressDispatcher
from deckbridge.device import DeckManager, real_discoverer
from deckbridge.device.cache import KeyImageCache
from deckbridge.device.painter import DeckPainter
from deckbridge.device.renderer import ImageRenderer
from deckbridge.events import DaemonStarted, DaemonStopping, EventBus
from deckbridge.http.auth import get_or_create_session_secret, require_auth
from deckbridge.http.routes_auth import router as auth_router
from deckbridge.http.routes_config import router as config_router
from deckbridge.http.routes_diagnostics import router as diagnostics_router
from deckbridge.http.routes_icons import router as icons_router
from deckbridge.http.routes_inbound import router as inbound_router
from deckbridge.http.routes_keys import router as keys_router
from deckbridge.http.routes_pages import router as pages_router
from deckbridge.http.routes_settings import router as settings_router
from deckbridge.http.routes_setup import router as setup_router
from deckbridge.http.routes_ws import router as ws_router
from deckbridge.http.spa import mount_spa
from deckbridge.icons.library import IconLibrary
from deckbridge.logging_ import get_logger
from deckbridge.mqtt import MqttClient
from deckbridge.mqtt.ha_discovery import HADiscovery
from deckbridge.mqtt.state_subscriber import StateSubscriber
from deckbridge.settings import Settings, load_settings
from deckbridge.storage import Storage, open_storage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from deckbridge.device import Discoverer

log = get_logger(__name__)


def create_app(
    settings: Settings | None = None,
    bus: EventBus | None = None,
    discoverer: Discoverer | None = None,
    storage: Storage | None = None,
) -> FastAPI:
    """Construct a fully-wired FastAPI app.

    Parameters
    ----------
    settings:
        Override settings. If omitted, loaded from environment.
    bus:
        Override event bus. If omitted, a fresh bus is created. Tests can pass
        in a recording bus to assert published events.
    discoverer:
        Override deck discoverer. If omitted, the production
        :func:`~deckbridge.device.real_discoverer` is used.
    storage:
        Override storage backend. If omitted, the configured backend
        (``settings.storage_backend``) is opened against ``settings.data_dir``
        with migrations applied. Tests inject an in-memory backend.
    """
    resolved_settings = settings or load_settings()
    resolved_bus = bus or EventBus()
    resolved_discoverer = discoverer or real_discoverer
    resolved_storage = storage or open_storage(
        resolved_settings.storage_backend,
        resolved_settings.data_dir,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        log.info(
            "deckbridge_starting",
            version=__version__,
            host=resolved_settings.host,
            port=resolved_settings.port,
            storage_backend=resolved_settings.storage_backend,
        )
        deck_manager = DeckManager(resolved_bus, resolved_discoverer)
        icon_library = IconLibrary(resolved_storage, resolved_settings.data_dir)
        icon_library.discover_bundled()
        # MQTT client reads broker config from preferences on every connect
        # cycle so a settings PATCH can call mqtt_client.reload() to pick up
        # changes without restart.
        mqtt_client = MqttClient(
            resolved_bus,
            prefs_provider=resolved_storage.get_preferences,
        )
        active_pages = ActivePages()
        # Single httpx pool for the lifetime of the daemon, shared by every
        # webhook action. follow_redirects keeps user-supplied URLs usable
        # when their target redirects.
        http_client = httpx.AsyncClient(follow_redirects=True)
        press_dispatcher = PressDispatcher(
            resolved_bus,
            resolved_storage,
            mqtt_client,
            active_pages,
            http_client,
            deck_manager=deck_manager,
        )
        # Render pipeline (M6c): renderer composes 72x72 PNGs, cache stores
        # them on disk, painter pushes to attached decks on relevant events,
        # state subscriber bridges MQTT messages -> KeyStateUpdated.
        renderer = ImageRenderer()
        image_cache = KeyImageCache(resolved_settings.data_dir)
        deck_painter = DeckPainter(
            resolved_bus,
            resolved_storage,
            deck_manager,
            icon_library,
            renderer,
            image_cache,
            active_pages,
        )
        state_subscriber = StateSubscriber(resolved_bus, resolved_storage, mqtt_client)
        ha_discovery = HADiscovery(resolved_bus, resolved_storage, mqtt_client, deck_manager)
        app.state.deck_manager = deck_manager
        app.state.storage = resolved_storage
        app.state.icon_library = icon_library
        app.state.mqtt_client = mqtt_client
        app.state.active_pages = active_pages
        app.state.press_dispatcher = press_dispatcher
        app.state.http_client = http_client
        app.state.renderer = renderer
        app.state.image_cache = image_cache
        app.state.deck_painter = deck_painter
        app.state.state_subscriber = state_subscriber
        app.state.ha_discovery = ha_discovery
        await deck_manager.start()
        mqtt_client.start()
        await resolved_bus.publish(DaemonStarted())
        try:
            yield
        finally:
            log.info("deckbridge_stopping")
            await resolved_bus.publish(DaemonStopping())
            await mqtt_client.stop()
            await deck_manager.stop()
            await http_client.aclose()
            resolved_storage.close()

    app = FastAPI(
        title="DeckBridge",
        version=__version__,
        description=(
            "Network-accessible smart-button bridge for the Elgato Stream Deck. "
            "See the project README for installation and configuration."
        ),
        lifespan=lifespan,
        # Hide the default Swagger UI behind /docs to keep the root reserved
        # for the SvelteKit SPA mount in M5.
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    # Stash shared state for route handlers / future middleware.
    app.state.settings = resolved_settings
    app.state.bus = resolved_bus

    # SessionMiddleware signs cookies with a stable secret. The secret is
    # either supplied via env (DECKBRIDGE_SESSION_SECRET_KEY), already in
    # storage, or generated and persisted under data_dir/secrets/session.key.
    secret = resolved_settings.session_secret_key or get_or_create_session_secret(
        resolved_settings.data_dir
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret,
        session_cookie="deckbridge_session",
        max_age=30 * 24 * 60 * 60,  # 30 days
        same_site="lax",
        https_only=False,  # HTTP-only LAN deployment per the architecture decision
    )

    # Public routes (no auth dependency).
    app.include_router(diagnostics_router)
    app.include_router(setup_router)
    app.include_router(auth_router)

    # Auth-gated routes. Modules that already declare the dependency on
    # their router (settings/pages/keys) don't need it re-applied here;
    # icons gets it applied because those routes are intentionally
    # un-gated at the module level for testability of the public shape.
    app.include_router(settings_router)
    app.include_router(pages_router)
    app.include_router(keys_router)
    app.include_router(icons_router, dependencies=[Depends(require_auth)])
    app.include_router(config_router)

    # M7 inbound state webhook — bearer-token-auth, NOT the session cookie
    # (external apps don't carry a browser session). Mounted under /api/pages
    # to share the URL shape with the editor's CRUD surface.
    app.include_router(inbound_router)

    # M8 diagnostics WebSocket — session-cookie auth at handshake.
    app.include_router(ws_router)

    # The SPA mount must come AFTER all /api/* routes so it doesn't shadow
    # them. If the SPA hasn't been built yet, this is a logged no-op.
    mount_spa(app)

    return app
