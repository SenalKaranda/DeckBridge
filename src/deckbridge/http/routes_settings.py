"""Settings endpoints — preferences, password, API token rotation.

GET   /api/settings              return safe view of preferences (no hashes)
PATCH /api/settings              partial update (broker, HA, etc.)
POST  /api/settings/password     rotate the admin password
POST  /api/settings/token        generate a new inbound-webhook bearer token
"""

from __future__ import annotations

import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from deckbridge.http.auth import hash_password, require_auth, verify_password

router = APIRouter(
    prefix="/api/settings",
    tags=["settings"],
    dependencies=[Depends(require_auth)],
)


# ---- response / request models -------------------------------------------


class PreferencesView(BaseModel):
    """The user-facing slice of Preferences — secrets are excluded."""

    model_config = ConfigDict(extra="forbid")

    mqtt_host: str | None = None
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_tls: bool = False
    ha_discovery_enabled: bool = True
    has_api_token: bool = False  # derived: True iff api_token_hash is set


class PreferencesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mqtt_host: str | None = None
    mqtt_port: int | None = None
    mqtt_username: str | None = None
    # mqtt_password is updated via this endpoint as a write-only field.
    # Sending None means "leave unchanged" since None is the unset sentinel
    # — to clear, send empty string.
    mqtt_password: str | None = None
    mqtt_tls: bool | None = None
    ha_discovery_enabled: bool | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class OkResponse(BaseModel):
    ok: bool


class TokenRotationResponse(BaseModel):
    """Plaintext token returned ONCE at rotation time. Store it immediately."""

    token: str


# ---- routes --------------------------------------------------------------


@router.get("", response_model=PreferencesView)
def get_settings(request: Request) -> PreferencesView:
    prefs = request.app.state.storage.get_preferences()
    return PreferencesView(
        mqtt_host=prefs.mqtt_host,
        mqtt_port=prefs.mqtt_port,
        mqtt_username=prefs.mqtt_username,
        mqtt_tls=prefs.mqtt_tls,
        ha_discovery_enabled=prefs.ha_discovery_enabled,
        has_api_token=prefs.api_token_hash is not None,
    )


_BROKER_FIELDS = frozenset({"mqtt_host", "mqtt_port", "mqtt_username", "mqtt_password", "mqtt_tls"})


@router.patch("", response_model=PreferencesView)
def patch_settings(payload: PreferencesPatch, request: Request) -> PreferencesView:
    storage = request.app.state.storage
    prefs = storage.get_preferences()
    update_dict = payload.model_dump(exclude_unset=True)
    if update_dict:
        new_prefs = prefs.model_copy(update=update_dict)
        storage.set_preferences(new_prefs)
        prefs = new_prefs
        # If any broker-related field changed, signal the MQTT client to
        # tear down and reconnect with the new config. Reload is non-blocking.
        if _BROKER_FIELDS & update_dict.keys():
            mqtt_client = getattr(request.app.state, "mqtt_client", None)
            if mqtt_client is not None:
                mqtt_client.reload()
    return PreferencesView(
        mqtt_host=prefs.mqtt_host,
        mqtt_port=prefs.mqtt_port,
        mqtt_username=prefs.mqtt_username,
        mqtt_tls=prefs.mqtt_tls,
        ha_discovery_enabled=prefs.ha_discovery_enabled,
        has_api_token=prefs.api_token_hash is not None,
    )


@router.post("/password", response_model=OkResponse)
def change_password(payload: PasswordChangeRequest, request: Request) -> OkResponse:
    """Replace the admin password.

    Requires the current password — even an authenticated session can't rotate
    the password without proving knowledge of the current one. This protects
    against shoulder-surfed sessions on a left-unlocked browser.
    """
    storage = request.app.state.storage
    prefs = storage.get_preferences()
    if prefs.password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No password is set; complete the setup wizard first.",
        )
    if not verify_password(payload.current_password, prefs.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        )

    new_prefs = prefs.model_copy(update={"password_hash": hash_password(payload.new_password)})
    storage.set_preferences(new_prefs)
    return OkResponse(ok=True)


@router.post("/token", response_model=TokenRotationResponse)
def rotate_api_token(request: Request) -> TokenRotationResponse:
    """Generate a new inbound-webhook bearer token, return its plaintext once.

    Stored as sha256 hash in Preferences.api_token_hash. The plaintext is not
    persisted anywhere — if the user loses it before storing, they must
    rotate again. The consumer (POST /api/keys/{id}/state) lands in M7.
    """
    plaintext = secrets.token_urlsafe(32)
    digest = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    storage = request.app.state.storage
    prefs = storage.get_preferences()
    storage.set_preferences(prefs.model_copy(update={"api_token_hash": digest}))
    return TokenRotationResponse(token=plaintext)
