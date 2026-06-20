"""SQLite-backed implementation of :class:`~deckbridge.storage.base.Storage`.

Single file at ``settings.data_dir / "data.db"`` (or ``":memory:"`` for tests).
Uses WAL journaling for safer concurrent access, foreign keys for cascade
delete, and JSON columns for nested fields (``Key.press`` / ``Key.state``).

Pydantic models round-trip through ``model_dump_json()`` /
``model_validate_json()`` — the schema is the source of truth.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from deckbridge.storage.base import Snapshot, Storage
from deckbridge.storage.schema import (
    CURRENT_SCHEMA_VERSION,
    Deck,
    Icon,
    IconSource,
    Key,
    Page,
    Preferences,
)

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decks (
    serial       TEXT PRIMARY KEY,
    model        TEXT NOT NULL DEFAULT '',
    first_seen   TEXT,
    last_seen    TEXT,
    home_page_id TEXT
);

CREATE TABLE IF NOT EXISTS pages (
    id          TEXT PRIMARY KEY,
    deck_serial TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    order_idx   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_pages_deck ON pages(deck_serial);

CREATE TABLE IF NOT EXISTS keys (
    page_id TEXT NOT NULL,
    slot    INTEGER NOT NULL,
    data    TEXT NOT NULL,
    PRIMARY KEY (page_id, slot),
    FOREIGN KEY (page_id) REFERENCES pages(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS icons (
    id        TEXT PRIMARY KEY,
    name      TEXT NOT NULL DEFAULT '',
    source    TEXT NOT NULL,
    reference TEXT NOT NULL,
    sha256    TEXT
);
"""


class SqliteStorage(Storage):
    """Production storage backend. Single SQLite file, WAL-journaled."""

    def __init__(self, path: str | Path) -> None:
        # ":memory:" is allowed for tests; everything else is coerced through Path.
        # ``check_same_thread=False`` is intentional: in production every storage
        # call runs on the asyncio loop thread, so we are effectively single-
        # threaded; in tests the FastAPI lifespan's shutdown hook may run on a
        # different anyio worker thread than the one that constructed the store.
        # The default sqlite3 thread-affinity check rejects that legitimate
        # pattern. We never share the connection across threads concurrently.
        if path == ":memory:":
            self._path: str = ":memory:"
            self._conn = sqlite3.connect(":memory:", isolation_level=None, check_same_thread=False)
        else:
            db_path = Path(path)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._path = str(db_path)
            self._conn = sqlite3.connect(self._path, isolation_level=None, check_same_thread=False)

        self._conn.row_factory = sqlite3.Row
        # WAL is meaningless for :memory: and harmless to skip.
        if self._path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA_SQL)

    # ---- schema version --------------------------------------------------

    def schema_version(self) -> int:
        row = self._conn.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            return 0
        return int(row["value"])

    def set_schema_version(self, version: int) -> None:
        self._conn.execute(
            "INSERT INTO metadata (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(version),),
        )

    # ---- preferences -----------------------------------------------------

    def get_preferences(self) -> Preferences:
        row = self._conn.execute("SELECT value FROM metadata WHERE key = 'preferences'").fetchone()
        if row is None:
            return Preferences()
        return Preferences.model_validate_json(row["value"])

    def set_preferences(self, prefs: Preferences) -> None:
        self._conn.execute(
            "INSERT INTO metadata (key, value) VALUES ('preferences', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (prefs.model_dump_json(),),
        )

    # ---- decks -----------------------------------------------------------

    def list_decks(self) -> list[Deck]:
        rows = self._conn.execute(
            "SELECT serial, model, first_seen, last_seen, home_page_id FROM decks ORDER BY serial"
        ).fetchall()
        return [self._deck_from_row(r) for r in rows]

    def get_deck(self, serial: str) -> Deck | None:
        row = self._conn.execute(
            "SELECT serial, model, first_seen, last_seen, home_page_id FROM decks WHERE serial = ?",
            (serial,),
        ).fetchone()
        return self._deck_from_row(row) if row else None

    def upsert_deck(self, deck: Deck) -> None:
        self._conn.execute(
            """
            INSERT INTO decks (serial, model, first_seen, last_seen, home_page_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(serial) DO UPDATE SET
                model        = excluded.model,
                first_seen   = excluded.first_seen,
                last_seen    = excluded.last_seen,
                home_page_id = excluded.home_page_id
            """,
            (
                deck.serial,
                deck.model,
                deck.first_seen.isoformat() if deck.first_seen else None,
                deck.last_seen.isoformat() if deck.last_seen else None,
                deck.home_page_id,
            ),
        )

    # ---- pages -----------------------------------------------------------

    def list_pages(self, deck_serial: str | None = None) -> list[Page]:
        if deck_serial is None:
            rows = self._conn.execute(
                "SELECT id, deck_serial, name, order_idx FROM pages "
                "ORDER BY deck_serial, order_idx, id"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, deck_serial, name, order_idx FROM pages "
                "WHERE deck_serial = ? ORDER BY order_idx, id",
                (deck_serial,),
            ).fetchall()
        return [self._page_from_row(r) for r in rows]

    def get_page(self, page_id: str) -> Page | None:
        row = self._conn.execute(
            "SELECT id, deck_serial, name, order_idx FROM pages WHERE id = ?",
            (page_id,),
        ).fetchone()
        return self._page_from_row(row) if row else None

    def upsert_page(self, page: Page) -> None:
        self._conn.execute(
            """
            INSERT INTO pages (id, deck_serial, name, order_idx)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                deck_serial = excluded.deck_serial,
                name        = excluded.name,
                order_idx   = excluded.order_idx
            """,
            (page.id, page.deck_serial, page.name, page.order),
        )

    def delete_page(self, page_id: str) -> None:
        # Cascade to keys is enforced by FOREIGN KEY ON DELETE CASCADE.
        self._conn.execute("DELETE FROM pages WHERE id = ?", (page_id,))

    # ---- keys ------------------------------------------------------------

    def list_keys(self, page_id: str) -> list[Key]:
        rows = self._conn.execute(
            "SELECT data FROM keys WHERE page_id = ? ORDER BY slot",
            (page_id,),
        ).fetchall()
        return [Key.model_validate_json(r["data"]) for r in rows]

    def get_key(self, page_id: str, slot: int) -> Key | None:
        row = self._conn.execute(
            "SELECT data FROM keys WHERE page_id = ? AND slot = ?",
            (page_id, slot),
        ).fetchone()
        return Key.model_validate_json(row["data"]) if row else None

    def upsert_key(self, key: Key) -> None:
        self._conn.execute(
            """
            INSERT INTO keys (page_id, slot, data) VALUES (?, ?, ?)
            ON CONFLICT(page_id, slot) DO UPDATE SET data = excluded.data
            """,
            (key.page_id, key.slot, key.model_dump_json()),
        )

    def delete_key(self, page_id: str, slot: int) -> None:
        self._conn.execute(
            "DELETE FROM keys WHERE page_id = ? AND slot = ?",
            (page_id, slot),
        )

    # ---- icons -----------------------------------------------------------

    def list_icons(self) -> list[Icon]:
        rows = self._conn.execute(
            "SELECT id, name, source, reference, sha256 FROM icons ORDER BY name, id"
        ).fetchall()
        return [self._icon_from_row(r) for r in rows]

    def get_icon(self, icon_id: str) -> Icon | None:
        row = self._conn.execute(
            "SELECT id, name, source, reference, sha256 FROM icons WHERE id = ?",
            (icon_id,),
        ).fetchone()
        return self._icon_from_row(row) if row else None

    def upsert_icon(self, icon: Icon) -> None:
        self._conn.execute(
            """
            INSERT INTO icons (id, name, source, reference, sha256)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name      = excluded.name,
                source    = excluded.source,
                reference = excluded.reference,
                sha256    = excluded.sha256
            """,
            (icon.id, icon.name, icon.source.value, icon.reference, icon.sha256),
        )

    def delete_icon(self, icon_id: str) -> None:
        self._conn.execute("DELETE FROM icons WHERE id = ?", (icon_id,))

    # ---- snapshot --------------------------------------------------------

    def export_snapshot(self) -> Snapshot:
        return Snapshot(
            schema_version=self.schema_version() or CURRENT_SCHEMA_VERSION,
            preferences=self.get_preferences(),
            decks=self.list_decks(),
            pages=self.list_pages(),
            keys=[k for p in self.list_pages() for k in self.list_keys(p.id)],
            icons=self.list_icons(),
        )

    def import_snapshot(self, snapshot: Snapshot) -> None:
        # Wipe and reload atomically. SQLite's auto-commit (isolation_level=None)
        # plus an explicit transaction makes this all-or-nothing.
        self._conn.execute("BEGIN")
        try:
            for table in ("keys", "pages", "decks", "icons"):
                self._conn.execute(f"DELETE FROM {table}")
            self.set_preferences(snapshot.preferences)
            for deck in snapshot.decks:
                self.upsert_deck(deck)
            for page in snapshot.pages:
                self.upsert_page(page)
            for key in snapshot.keys:
                self.upsert_key(key)
            for icon in snapshot.icons:
                self.upsert_icon(icon)
            self.set_schema_version(snapshot.schema_version)
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    # ---- lifecycle -------------------------------------------------------

    def close(self) -> None:
        self._conn.close()

    # ---- row → model helpers --------------------------------------------

    @staticmethod
    def _deck_from_row(row: sqlite3.Row) -> Deck:
        return Deck(
            serial=row["serial"],
            model=row["model"],
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            home_page_id=row["home_page_id"],
        )

    @staticmethod
    def _page_from_row(row: sqlite3.Row) -> Page:
        return Page(
            id=row["id"],
            deck_serial=row["deck_serial"],
            name=row["name"],
            order=row["order_idx"],
        )

    @staticmethod
    def _icon_from_row(row: sqlite3.Row) -> Icon:
        return Icon(
            id=row["id"],
            name=row["name"],
            source=IconSource(row["source"]),
            reference=row["reference"],
            sha256=row["sha256"],
        )

    # ---- introspection ---------------------------------------------------

    def __repr__(self) -> str:  # pragma: no cover — diagnostic only
        return f"SqliteStorage(path={self._path!r})"

    # Imported here because the static analyzer wants `Any` if we ever expose
    # the connection. Keep the surface narrow — no public connection access.
    _: Any = None
