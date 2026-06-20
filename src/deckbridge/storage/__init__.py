"""Persistent storage for DeckBridge — SQLite and file backends behind one protocol."""

from __future__ import annotations

from pathlib import Path

from deckbridge.storage.base import Snapshot, Storage
from deckbridge.storage.file_store import FileStorage
from deckbridge.storage.migrations import run_migrations
from deckbridge.storage.schema import (
    CURRENT_SCHEMA_VERSION,
    Deck,
    HTTPWebhookAction,
    Icon,
    IconSource,
    Key,
    MQTTPublishAction,
    NoOpAction,
    Page,
    PageSwitchAction,
    Preferences,
    PressAction,
    StateSubscription,
)
from deckbridge.storage.sqlite_store import SqliteStorage

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "Deck",
    "FileStorage",
    "HTTPWebhookAction",
    "Icon",
    "IconSource",
    "Key",
    "MQTTPublishAction",
    "NoOpAction",
    "Page",
    "PageSwitchAction",
    "Preferences",
    "PressAction",
    "Snapshot",
    "SqliteStorage",
    "StateSubscription",
    "Storage",
    "open_storage",
    "run_migrations",
]


def open_storage(backend: str, data_dir: Path) -> Storage:
    """Construct the configured backend, ensuring its data location exists.

    Args:
        backend: ``"sqlite"`` (default in production) or ``"files"``.
        data_dir: Directory under which the backend stores its file(s).

    The returned instance has migrations applied; callers can use it directly.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    storage: Storage
    if backend == "sqlite":
        storage = SqliteStorage(data_dir / "data.db")
    elif backend == "files":
        storage = FileStorage(data_dir / "data.json")
    else:
        raise ValueError(f"Unknown storage backend {backend!r}. Expected 'sqlite' or 'files'.")
    run_migrations(storage)
    return storage
