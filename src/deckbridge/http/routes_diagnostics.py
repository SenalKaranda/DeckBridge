"""Diagnostic HTTP endpoints — healthcheck, version, status.

    GET /api/healthz   unauth, cheap liveness probe
    GET /api/status    auth, structured snapshot of attached decks + broker state

The full Diagnostics tab (logs, event timeline) lands in M8.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from deckbridge import __version__
from deckbridge.http.auth import require_auth

router = APIRouter()


class HealthzResponse(BaseModel):
    status: str
    version: str


class DeckStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    serial: str
    model: str


class StatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    decks: list[DeckStatus]
    broker_connected: bool = False
    """True when an MQTT session is currently open. False when no broker
    is configured, the connection is being retried, or the daemon is
    starting up."""


@router.get("/api/healthz", response_model=HealthzResponse, tags=["diagnostics"])
async def healthz() -> HealthzResponse:
    """Liveness check. Returns 200 with current daemon version while the process is up.

    Unauthenticated so external monitors (Docker healthcheck, systemd watchdog,
    uptime probes) can hit it without ceremony. Does NOT verify deeper
    subsystems — see ``/api/status`` for broker connectivity, deck attachment.
    """
    return HealthzResponse(status="ok", version=__version__)


@router.get(
    "/api/status",
    response_model=StatusResponse,
    tags=["diagnostics"],
    dependencies=[Depends(require_auth)],
)
def status(request: Request) -> StatusResponse:
    """Snapshot of currently attached decks plus broker connectivity."""
    deck_manager = getattr(request.app.state, "deck_manager", None)
    decks = (
        [DeckStatus(serial=d.serial, model=d.model) for d in deck_manager.decks.values()]
        if deck_manager is not None
        else []
    )
    mqtt_client = getattr(request.app.state, "mqtt_client", None)
    broker_connected = bool(mqtt_client is not None and mqtt_client.connected)
    return StatusResponse(version=__version__, decks=decks, broker_connected=broker_connected)
