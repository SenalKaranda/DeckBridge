"""Structured logging configuration for DeckBridge.

The daemon logs structured records via ``structlog`` and renders them as JSON
to stderr by default (one log line per JSON object). Operators read logs via
``journalctl -u deckbridge`` or ``docker logs deckbridge``; the in-UI log
viewer (M8) subscribes to the same processor pipeline through a ringbuffer.

Call :func:`configure` exactly once during process startup, before any logger
is acquired by application code.
"""

from __future__ import annotations

import logging
import sys
from typing import Literal

import structlog

from deckbridge.logging_.ringbuffer import buffering_processor

LogFormat = Literal["json", "console"]


def configure(level: str = "INFO", fmt: LogFormat = "json") -> None:
    """Configure structlog and the stdlib root logger.

    Args:
        level: Minimum level name (DEBUG/INFO/WARNING/ERROR).
        fmt: ``"json"`` for line-delimited JSON (production), ``"console"``
            for colorized human-readable output (local development).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    # Shared processor chain: enrich every record with timestamp, level, logger
    # name, and any context bound earlier in the call stack.
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        # Capture each enriched record into the in-memory ringbuffer for the
        # diagnostics WebSocket. Runs BEFORE the renderer so the buffer holds
        # a structured copy regardless of the human-facing format.
        buffering_processor,
    ]

    renderer: structlog.types.Processor
    if fmt == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        # stdlib.LoggerFactory bridges into the stdlib root logger configured
        # below (which is what writes to stderr). PrintLoggerFactory looks
        # tempting but its underlying PrintLogger has no `.name` attribute,
        # which the `add_logger_name` processor needs.
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bridge the stdlib `logging` module (used by uvicorn, FastAPI, etc.) into
    # the same output stream and level. Without this, uvicorn prints its own
    # plain-text access log alongside our structured records.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=log_level,
        force=True,
    )

    # Quiet the noisy access logger; we'll re-emit access events via structlog
    # if/when we add a middleware in M5+. For M1 the default level on the
    # uvicorn loggers is fine.
    logging.getLogger("uvicorn.access").setLevel(log_level)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Acquire a logger. Pass ``__name__`` from the calling module."""
    return structlog.get_logger(name)
