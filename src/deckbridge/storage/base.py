"""Storage protocol and shared types.

A :class:`Storage` is a domain-level interface — callers reason in terms of
:class:`~deckbridge.storage.schema.Deck`, :class:`~deckbridge.storage.schema.Page`,
:class:`~deckbridge.storage.schema.Key`, and :class:`~deckbridge.storage.schema.Icon`
objects, not SQL or file paths. Two backends implement this protocol:
:class:`~deckbridge.storage.sqlite_store.SqliteStorage` and
:class:`~deckbridge.storage.file_store.FileStorage`.

Both backends produce the same observable behavior — see the parity tests in
``tests/unit/test_storage_parity.py``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from deckbridge.storage.schema import (
    CURRENT_SCHEMA_VERSION,
    Deck,
    Icon,
    Key,
    Page,
    Preferences,
)


class Snapshot(BaseModel):
    """A complete export of every entity in storage. Used for migration and backup."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION)
    preferences: Preferences = Field(default_factory=Preferences)
    decks: list[Deck] = Field(default_factory=list)
    pages: list[Page] = Field(default_factory=list)
    keys: list[Key] = Field(default_factory=list)
    icons: list[Icon] = Field(default_factory=list)


@runtime_checkable
class Storage(Protocol):
    """Single source of truth for persisted DeckBridge state.

    Operations are synchronous — they're cheap (microseconds for SQLite, ms
    for file flushes) and called from async route handlers without offload.
    If a future operation grows expensive, wrap that specific call in
    ``loop.run_in_executor`` at the call site.
    """

    # ---- schema version (driven by migrations runner) ----

    def schema_version(self) -> int:
        """Read the persisted schema version, or 0 if uninitialized."""

    def set_schema_version(self, version: int) -> None:
        """Persist the schema version after applying migrations."""

    # ---- preferences (singleton) ----

    def get_preferences(self) -> Preferences:
        """Return the persisted preferences, or defaults if none have been saved."""

    def set_preferences(self, prefs: Preferences) -> None:
        """Replace the persisted preferences atomically."""

    # ---- decks ----

    def list_decks(self) -> list[Deck]: ...

    def get_deck(self, serial: str) -> Deck | None: ...

    def upsert_deck(self, deck: Deck) -> None: ...

    # ---- pages ----

    def list_pages(self, deck_serial: str | None = None) -> list[Page]:
        """Pages, optionally filtered to one deck. Order: ``Page.order`` ascending."""

    def get_page(self, page_id: str) -> Page | None: ...

    def upsert_page(self, page: Page) -> None: ...

    def delete_page(self, page_id: str) -> None:
        """Delete a page and cascade-delete its keys."""

    # ---- keys ----

    def list_keys(self, page_id: str) -> list[Key]:
        """All keys on a page, ordered by ``slot`` ascending."""

    def get_key(self, page_id: str, slot: int) -> Key | None: ...

    def upsert_key(self, key: Key) -> None: ...

    def delete_key(self, page_id: str, slot: int) -> None: ...

    # ---- icons ----

    def list_icons(self) -> list[Icon]: ...

    def get_icon(self, icon_id: str) -> Icon | None: ...

    def upsert_icon(self, icon: Icon) -> None: ...

    def delete_icon(self, icon_id: str) -> None: ...

    # ---- snapshot (for migrate / export / import) ----

    def export_snapshot(self) -> Snapshot:
        """Read every entity into a single Snapshot for backup or backend swap."""

    def import_snapshot(self, snapshot: Snapshot) -> None:
        """Replace all current data with the contents of ``snapshot``."""

    # ---- lifecycle ----

    def close(self) -> None:
        """Release any underlying resources (file handles, DB connections)."""
