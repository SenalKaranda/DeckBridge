"""Auth utilities — argon2 hashing, setup detection, session-secret bootstrap."""

from __future__ import annotations

from pathlib import Path

import pytest

from deckbridge.http.auth import (
    get_or_create_session_secret,
    hash_password,
    is_setup_needed,
    verify_password,
)
from deckbridge.storage import SqliteStorage, run_migrations
from deckbridge.storage.schema import Preferences


def test_hash_password_returns_argon2_string() -> None:
    h = hash_password("hunter2")
    assert h.startswith("$argon2")
    # Argon2 hashes are non-deterministic (random salt) — every call differs.
    assert h != hash_password("hunter2")


def test_verify_password_succeeds_on_match() -> None:
    h = hash_password("hunter2")
    assert verify_password("hunter2", h) is True


def test_verify_password_fails_on_mismatch() -> None:
    h = hash_password("hunter2")
    assert verify_password("wrong-pw", h) is False


def test_hash_rejects_empty_password() -> None:
    with pytest.raises(ValueError, match="empty"):
        hash_password("")


def test_is_setup_needed_when_storage_is_fresh() -> None:
    storage = SqliteStorage(":memory:")
    run_migrations(storage)
    assert is_setup_needed(storage) is True


def test_is_setup_needed_false_after_password_set() -> None:
    storage = SqliteStorage(":memory:")
    run_migrations(storage)
    storage.set_preferences(Preferences(password_hash=hash_password("p")))
    assert is_setup_needed(storage) is False


def test_session_secret_persists_across_calls(tmp_path: Path) -> None:
    first = get_or_create_session_secret(tmp_path)
    second = get_or_create_session_secret(tmp_path)
    assert first == second
    assert (tmp_path / "secrets" / "session.key").is_file()


def test_session_secret_unique_per_data_dir(tmp_path_factory: pytest.TempPathFactory) -> None:
    a_dir = tmp_path_factory.mktemp("a")
    b_dir = tmp_path_factory.mktemp("b")
    assert get_or_create_session_secret(a_dir) != get_or_create_session_secret(b_dir)


def test_session_secret_is_long_enough(tmp_path: Path) -> None:
    """Don't ship a short signing secret by accident."""
    secret = get_or_create_session_secret(tmp_path)
    assert len(secret) >= 40, f"session secret too short: {len(secret)}"
