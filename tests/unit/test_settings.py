"""Settings load environment variables with the DECKBRIDGE_ prefix."""

from __future__ import annotations

from pathlib import Path

import pytest

from deckbridge.settings import Settings, load_settings


def test_defaults_when_no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Strip any inherited DECKBRIDGE_* env so this test is hermetic.
    for key in (
        "DECKBRIDGE_PORT",
        "DECKBRIDGE_HOST",
        "DECKBRIDGE_DATA_DIR",
        "DECKBRIDGE_CONFIG_DIR",
        "DECKBRIDGE_MQTT_HOST",
        "DECKBRIDGE_MQTT_PORT",
        "DECKBRIDGE_STORAGE_BACKEND",
        "DECKBRIDGE_HA_DISCOVERY",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = load_settings()
    assert settings.port == 7878
    assert settings.host == "0.0.0.0"
    assert settings.storage_backend == "sqlite"
    assert settings.config_dir == Path("/etc/deckbridge")
    assert settings.data_dir == Path("/var/lib/deckbridge")
    assert settings.mqtt_host is None
    assert settings.ha_discovery is True


def test_env_vars_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECKBRIDGE_PORT", "9999")
    monkeypatch.setenv("DECKBRIDGE_MQTT_HOST", "broker.lan")
    monkeypatch.setenv("DECKBRIDGE_MQTT_PORT", "8883")
    monkeypatch.setenv("DECKBRIDGE_STORAGE_BACKEND", "files")
    monkeypatch.setenv("DECKBRIDGE_HA_DISCOVERY", "false")

    settings = load_settings()
    assert settings.port == 9999
    assert settings.mqtt_host == "broker.lan"
    assert settings.mqtt_port == 8883
    assert settings.storage_backend == "files"
    assert settings.ha_discovery is False


def test_invalid_storage_backend_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import ValidationError

    monkeypatch.setenv("DECKBRIDGE_STORAGE_BACKEND", "mongodb")
    with pytest.raises(ValidationError, match="storage_backend"):
        Settings()
