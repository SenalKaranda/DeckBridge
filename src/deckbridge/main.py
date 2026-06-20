"""Daemon entrypoint.

Wires together settings, structured logging, and the FastAPI app, then hands
control to uvicorn. Invoked by the ``deckbridge run`` CLI subcommand and by
the Docker image's default ``CMD``.
"""

from __future__ import annotations

import uvicorn

from deckbridge.http import create_app
from deckbridge.logging_ import configure as configure_logging
from deckbridge.logging_ import get_logger
from deckbridge.settings import Settings, load_settings


def run(settings: Settings | None = None) -> None:
    """Start the daemon. Blocks until uvicorn shuts down."""
    resolved = settings or load_settings()

    fmt = resolved.log_format
    if resolved.dev_mode and fmt == "json":
        # Sensible default flip for local development unless explicitly overridden.
        fmt = "console"
    configure_logging(level=resolved.log_level, fmt=fmt)

    log = get_logger(__name__)
    log.info(
        "uvicorn_starting",
        host=resolved.host,
        port=resolved.port,
        dev_mode=resolved.dev_mode,
    )

    app = create_app(settings=resolved)
    uvicorn.run(
        app,
        host=resolved.host,
        port=resolved.port,
        log_config=None,  # we own logging via structlog; do not let uvicorn re-init it
        access_log=False,  # access logs land via middleware in M5+
    )
