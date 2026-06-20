"""Runtime settings for the DeckBridge daemon.

Single source of truth for ports, paths, broker config, and feature flags. All
values are loadable from environment variables prefixed with ``DECKBRIDGE_``,
falling back to FHS-style defaults appropriate for a system service install.

For Docker deployments the install layer typically sets ``DECKBRIDGE_DATA_DIR``
to ``/data`` and lets the rest default; for bare-metal systemd installs the
defaults already match ``/var/lib/deckbridge`` and ``/etc/deckbridge``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

StorageBackend = Literal["sqlite", "files"]


class Settings(BaseSettings):
    """Daemon configuration. Environment variables override defaults."""

    model_config = SettingsConfigDict(
        env_prefix="DECKBRIDGE_",
        env_file=None,  # explicit env_file loading happens at the entrypoint, not here
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Network ----
    host: str = Field(default="0.0.0.0", description="Bind address for the web UI")
    port: int = Field(default=7878, description="Port for the web UI and HTTP API")

    # ---- Filesystem ----
    config_dir: Path = Field(
        default=Path("/etc/deckbridge"),
        description="Directory for editable config (FHS layout). Docker: /data.",
    )
    data_dir: Path = Field(
        default=Path("/var/lib/deckbridge"),
        description="Directory for SQLite, cache, uploaded icons. Docker: /data.",
    )

    # ---- Storage backend ----
    storage_backend: StorageBackend = Field(
        default="sqlite",
        description="Which storage adapter to use. 'sqlite' or 'files'.",
    )

    # ---- MQTT (broker config; broker itself is external) ----
    mqtt_host: str | None = Field(
        default=None,
        description="External MQTT broker hostname. Required for full operation.",
    )
    mqtt_port: int = Field(default=1883, description="MQTT broker port.")
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_tls: bool = False

    # ---- Feature flags ----
    ha_discovery: bool = Field(
        default=True,
        description="Publish Home Assistant MQTT Discovery payloads on startup and config change.",
    )

    # ---- Auth ----
    session_secret_key: str | None = Field(
        default=None,
        description="Secret key for signing session cookies. If unset, the daemon "
        "auto-generates one and persists it under data_dir/secrets/session.key on "
        "first start. Tests pass an explicit deterministic value.",
    )

    # ---- Operational ----
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = Field(
        default="json",
        description="structlog renderer. 'json' for production, 'console' for human-readable dev output.",
    )
    dev_mode: bool = Field(
        default=False,
        description="Enables uvicorn auto-reload and switches log_format to 'console' if not set.",
    )


def load_settings() -> Settings:
    """Construct a Settings instance from the environment.

    Wrapped in a function so tests can monkey-patch the environment, call this,
    and get a fresh instance. Avoid module-level singletons elsewhere.
    """
    return Settings()
