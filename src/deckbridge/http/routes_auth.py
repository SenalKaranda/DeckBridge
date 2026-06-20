"""Login / logout / whoami endpoints.

    POST /api/login     unauth, sets session on success
    POST /api/logout    auth, clears session
    GET  /api/me        auth, returns minimal "you are logged in" payload

There is only one user (the admin), so /api/me is more of a "is this session
still valid" probe than a user-info endpoint. The frontend calls it on app
load to decide between login and editor routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from deckbridge.http.auth import (
    is_setup_needed,
    login_session,
    logout_session,
    require_auth,
    verify_password,
)

router = APIRouter(prefix="/api", tags=["auth"])


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    ok: bool


class WhoAmIResponse(BaseModel):
    authenticated: bool


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request) -> LoginResponse:
    storage = request.app.state.storage
    if is_setup_needed(storage):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No password has been configured yet; complete the setup wizard first.",
        )

    prefs = storage.get_preferences()
    assert prefs.password_hash is not None  # narrowed by is_setup_needed check above
    if not verify_password(payload.password, prefs.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid password.",
        )

    login_session(request)
    return LoginResponse(ok=True)


@router.post("/logout", response_model=LoginResponse, dependencies=[Depends(require_auth)])
def logout(request: Request) -> LoginResponse:
    logout_session(request)
    return LoginResponse(ok=True)


@router.get("/me", response_model=WhoAmIResponse, dependencies=[Depends(require_auth)])
def whoami() -> WhoAmIResponse:
    return WhoAmIResponse(authenticated=True)
