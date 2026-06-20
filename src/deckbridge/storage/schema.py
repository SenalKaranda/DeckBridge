"""Pydantic v2 schema — the single source of truth for DeckBridge's data shape.

These models are shared by both storage backends (SQLite and JSON files) and
by the HTTP API. Fields are validated at the boundary; downstream code can
trust that any :class:`Key`, :class:`Page`, etc. it receives is well-formed.

Schema changes flow through :mod:`deckbridge.storage.migrations` — bumping
:data:`CURRENT_SCHEMA_VERSION` and adding a migration function that
transforms the previous version's :class:`Snapshot` into the new shape.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

CURRENT_SCHEMA_VERSION = 1
"""Bump this whenever the schema changes; add a migration in migrations.py."""


# ---- Icon -----------------------------------------------------------------


class IconSource(StrEnum):
    BUNDLED = "bundled"  # references a name in the Lucide bundle
    UPLOADED = "uploaded"  # user-uploaded; reference is a storage path/key


class Icon(BaseModel):
    """A renderable icon, either bundled (Lucide) or user-uploaded."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, description="Stable opaque identifier.")
    name: str = Field(default="", description="Human-friendly name shown in UI.")
    source: IconSource
    reference: str = Field(
        min_length=1,
        description="For BUNDLED: Lucide icon name. For UPLOADED: storage path/key.",
    )
    sha256: str | None = Field(
        default=None,
        description="Hex digest of the original bytes; populated for uploaded icons "
        "to support deduplication.",
    )


# ---- Press actions (discriminated union by `type`) ------------------------


class _PressActionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MQTTPublishAction(_PressActionBase):
    """Publish a message to an MQTT topic on key press."""

    type: Literal["mqtt_publish"] = "mqtt_publish"
    topic: str = Field(min_length=1)
    payload: str = ""
    retain: bool = False
    qos: Literal[0, 1, 2] = 0


class HTTPWebhookAction(_PressActionBase):
    """Fire an HTTP request on key press."""

    type: Literal["http_webhook"] = "http_webhook"
    url: str = Field(min_length=1)
    method: Literal["GET", "POST", "PUT", "DELETE"] = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""


class PageSwitchAction(_PressActionBase):
    """Switch the deck's active page."""

    type: Literal["page_switch"] = "page_switch"
    target_page_id: str = Field(min_length=1)


class NoOpAction(_PressActionBase):
    """No-op press; useful as a default."""

    type: Literal["no_op"] = "no_op"


PressAction = Annotated[
    MQTTPublishAction | HTTPWebhookAction | PageSwitchAction | NoOpAction,
    Field(discriminator="type"),
]


# ---- State subscription ---------------------------------------------------


class StateSubscription(BaseModel):
    """Subscribe to a topic and re-render the key based on the value received."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1)
    jmespath: str | None = Field(
        default=None,
        description="Optional JMESPath expression applied to a JSON payload to "
        "extract the state value. Empty means 'use the whole payload as a string'.",
    )
    icon_map: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from extracted state value → icon id.",
    )
    default_icon_id: str | None = Field(
        default=None,
        description="Icon shown when the extracted value matches no key in icon_map.",
    )


# ---- Entities -------------------------------------------------------------


class Deck(BaseModel):
    """A physical Stream Deck known to the system. Persisted across runs."""

    model_config = ConfigDict(extra="forbid")

    serial: str = Field(min_length=1)
    model: str = Field(default="", description="Device class name (e.g. StreamDeckMK2).")
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    home_page_id: str | None = Field(
        default=None,
        description="Page shown when the deck connects. None = first page in `order`.",
    )


class Page(BaseModel):
    """A page belongs to a deck and contains up to 15 keys (slots 0-14 for MK.2)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, description="Opaque identifier (UUID).")
    deck_serial: str = Field(min_length=1)
    name: str = ""
    order: int = Field(default=0, description="Sort order within the deck.")


_HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class Key(BaseModel):
    """A single slot on a page. Identified by (page_id, slot)."""

    model_config = ConfigDict(extra="forbid")

    page_id: str = Field(min_length=1)
    slot: int = Field(
        ge=0,
        le=31,
        description="0-indexed slot. v1 UI uses 0-14 (MK.2). Range allows up to "
        "32-key XL for forward compatibility (not exposed in v1 UI).",
    )
    label: str = Field(default="", description="Optional text overlaid on the icon.")
    icon_id: str | None = Field(
        default=None,
        description="Default icon when no state subscription matches.",
    )
    press: PressAction = Field(default_factory=NoOpAction)
    state: StateSubscription | None = None
    padding: int = Field(
        default=0,
        ge=0,
        le=20,
        description="Extra inset (in pixels) added to all four sides of the key's "
        "icon + label region. 0 = renderer defaults (already includes a small "
        "built-in margin). Increase to give the icon more breathing room when it "
        "feels cropped against the key's edge. Capped at 20 because at 72x72 a "
        "value much larger erases all the content area.",
    )

    # ---- presentation (v1.1) -------------------------------------------
    show_icon: bool = Field(
        default=True,
        description="When False, the painter skips drawing the icon. Useful for "
        "label-only keys; the label is centered vertically instead of bottom-anchored.",
    )
    show_label: bool = Field(
        default=True,
        description="When False, the painter skips drawing the label even if "
        "`label` is non-empty. The label text is preserved across toggles.",
    )
    bg_color: str = Field(
        default="#000000",
        pattern=_HEX_COLOR_PATTERN,
        description="Solid background color as `#RRGGBB`. Drawn under the icon "
        "and (when set) under the bg_image. Default black matches v1.0.x.",
    )
    bg_image_id: str | None = Field(
        default=None,
        description="Optional background image (icon-library id). Drawn over the "
        "bg_color, fitted with cover semantics (scale-to-fill + center-crop). "
        "Useful for branded/photographic backgrounds; uploaded via the same "
        "icon system as foreground icons.",
    )
    label_color: str = Field(
        default="#FFFFFF",
        pattern=_HEX_COLOR_PATTERN,
        description="Label text color as `#RRGGBB`. Default white matches v1.0.x. "
        "The renderer always draws a 1px black drop-shadow for legibility.",
    )
    icon_color: str | None = Field(
        default=None,
        pattern=_HEX_COLOR_PATTERN,
        description="Optional tint applied to the icon: each pixel's RGB is "
        "multiplied by this color (alpha preserved). `None` leaves the icon "
        "untouched. Best for white/grayscale icons (the bundled Lucide set); "
        "applying a tint to an already-colored icon will recolor it.",
    )
    font_size: int = Field(
        default=14,
        ge=8,
        le=32,
        description="Label font size in pixels. Default 14 matches v1.0.x "
        "rendering exactly. Lower values let longer labels fit; higher values "
        "make short labels more readable from a distance. Capped at 32 because "
        "anything larger overflows the 72px key height.",
    )


# ---- Preferences (user-configurable settings stored in the backend) ----


class Preferences(BaseModel):
    """User-configurable settings persisted in the storage backend.

    Distinct from :class:`deckbridge.settings.Settings`, which is operational
    config sourced from environment variables (port, paths, log level, etc.).
    These preferences are editable via the web UI and survive restarts.

    A fresh install has ``password_hash is None`` — the first hit to the web
    UI redirects to the setup wizard, which collects the password and stores
    its argon2 hash here.
    """

    model_config = ConfigDict(extra="forbid")

    # Web UI auth
    password_hash: str | None = Field(
        default=None,
        description="argon2 hash of the admin password. None means setup is needed.",
    )
    api_token_hash: str | None = Field(
        default=None,
        description="sha256 hash of the bearer token used for the inbound webhook "
        "API. The plaintext is shown once on rotation. M7 wires the consumer.",
    )

    # MQTT broker connection (overrides Settings.mqtt_* once configured here)
    mqtt_host: str | None = None
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_tls: bool = False

    # Home Assistant integration
    ha_discovery_enabled: bool = True
