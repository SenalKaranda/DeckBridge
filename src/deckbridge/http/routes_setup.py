"""First-run setup wizard.

Two endpoints, both unauthenticated:

    GET  /api/setup/needed     -> {"needed": true|false}
    POST /api/setup/complete   -> sets the admin password (only valid if needed)

The frontend hits ``GET /api/setup/needed`` on load. If true, it renders the
setup wizard form and POSTs the chosen password to ``/api/setup/complete``.
After completion, the same endpoint refuses subsequent calls (409) so a
second person can't grab the admin slot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from deckbridge.http.auth import hash_password, is_setup_needed, login_session

if TYPE_CHECKING:
    pass

router = APIRouter(prefix="/api/setup", tags=["setup"])


class SetupStatus(BaseModel):
    needed: bool


class SetupCompleteRequest(BaseModel):
    password: str = Field(min_length=8, max_length=256)


@router.get("/needed", response_model=SetupStatus)
def setup_needed(request: Request) -> SetupStatus:
    return SetupStatus(needed=is_setup_needed(request.app.state.storage))


@router.post("/complete", response_model=SetupStatus, status_code=status.HTTP_201_CREATED)
def setup_complete(payload: SetupCompleteRequest, request: Request) -> SetupStatus:
    storage = request.app.state.storage
    if not is_setup_needed(storage):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Setup already complete; use the password-change endpoint instead.",
        )

    prefs = storage.get_preferences()
    new_prefs = prefs.model_copy(update={"password_hash": hash_password(payload.password)})
    storage.set_preferences(new_prefs)

    # Auto-login so the wizard transitions straight into the editor instead of
    # forcing the user to re-enter the password they just set.
    login_session(request)
    return SetupStatus(needed=False)
