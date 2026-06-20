"""Plain-file implementation of :class:`~deckbridge.storage.base.Storage`.

Single JSON file at ``settings.data_dir / "data.json"``. The whole store is
held in memory and re-serialized on each mutation via an atomic
write-temp-then-rename, so a crash mid-save cannot corrupt the file.

This backend is for users who want their config in a hand-inspectable form
(or git-trackable). Both backends produce identical observable behavior —
the parity test suite enforces this.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

from deckbridge.storage.base import Snapshot, Storage
from deckbridge.storage.schema import (
    Deck,
    Icon,
    Key,
    Page,
    Preferences,
)


class FileStorage(Storage):
    """JSON-file storage backend. Atomic writes via tempfile + rename."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._snapshot = self._load()

    # ---- IO --------------------------------------------------------------

    def _load(self) -> Snapshot:
        if not self._path.exists():
            return Snapshot()
        text = self._path.read_text(encoding="utf-8")
        if not text.strip():
            return Snapshot()
        return Snapshot.model_validate_json(text)

    def _flush(self) -> None:
        """Write the current snapshot to disk atomically."""
        payload = self._snapshot.model_dump_json(indent=2)
        # NamedTemporaryFile + rename gives us atomicity on POSIX and Windows.
        # On Windows, os.replace handles the existing-target case.
        directory = self._path.parent
        fd, tmp_path = tempfile.mkstemp(
            prefix=f".{self._path.name}.",
            suffix=".tmp",
            dir=str(directory),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp_path, self._path)
        except BaseException:
            # Best-effort cleanup of the partial temp file on any failure.
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

    # ---- schema version --------------------------------------------------

    def schema_version(self) -> int:
        return self._snapshot.schema_version

    def set_schema_version(self, version: int) -> None:
        self._snapshot = self._snapshot.model_copy(update={"schema_version": version})
        self._flush()

    # ---- preferences -----------------------------------------------------

    def get_preferences(self) -> Preferences:
        return self._snapshot.preferences.model_copy(deep=True)

    def set_preferences(self, prefs: Preferences) -> None:
        self._snapshot = self._snapshot.model_copy(update={"preferences": prefs})
        self._flush()

    # ---- decks -----------------------------------------------------------

    def list_decks(self) -> list[Deck]:
        return sorted(self._snapshot.decks, key=lambda d: d.serial)

    def get_deck(self, serial: str) -> Deck | None:
        return next((d for d in self._snapshot.decks if d.serial == serial), None)

    def upsert_deck(self, deck: Deck) -> None:
        decks = [d for d in self._snapshot.decks if d.serial != deck.serial]
        decks.append(deck)
        self._snapshot = self._snapshot.model_copy(update={"decks": decks})
        self._flush()

    # ---- pages -----------------------------------------------------------

    def list_pages(self, deck_serial: str | None = None) -> list[Page]:
        pages = self._snapshot.pages
        if deck_serial is not None:
            pages = [p for p in pages if p.deck_serial == deck_serial]
        return sorted(pages, key=lambda p: (p.deck_serial, p.order, p.id))

    def get_page(self, page_id: str) -> Page | None:
        return next((p for p in self._snapshot.pages if p.id == page_id), None)

    def upsert_page(self, page: Page) -> None:
        pages = [p for p in self._snapshot.pages if p.id != page.id]
        pages.append(page)
        self._snapshot = self._snapshot.model_copy(update={"pages": pages})
        self._flush()

    def delete_page(self, page_id: str) -> None:
        pages = [p for p in self._snapshot.pages if p.id != page_id]
        # Cascade: drop keys belonging to the deleted page.
        keys = [k for k in self._snapshot.keys if k.page_id != page_id]
        self._snapshot = self._snapshot.model_copy(update={"pages": pages, "keys": keys})
        self._flush()

    # ---- keys ------------------------------------------------------------

    def list_keys(self, page_id: str) -> list[Key]:
        return sorted(
            (k for k in self._snapshot.keys if k.page_id == page_id),
            key=lambda k: k.slot,
        )

    def get_key(self, page_id: str, slot: int) -> Key | None:
        return next(
            (k for k in self._snapshot.keys if k.page_id == page_id and k.slot == slot),
            None,
        )

    def upsert_key(self, key: Key) -> None:
        keys = [
            k for k in self._snapshot.keys if not (k.page_id == key.page_id and k.slot == key.slot)
        ]
        keys.append(key)
        self._snapshot = self._snapshot.model_copy(update={"keys": keys})
        self._flush()

    def delete_key(self, page_id: str, slot: int) -> None:
        keys = [k for k in self._snapshot.keys if not (k.page_id == page_id and k.slot == slot)]
        self._snapshot = self._snapshot.model_copy(update={"keys": keys})
        self._flush()

    # ---- icons -----------------------------------------------------------

    def list_icons(self) -> list[Icon]:
        return sorted(self._snapshot.icons, key=lambda i: (i.name, i.id))

    def get_icon(self, icon_id: str) -> Icon | None:
        return next((i for i in self._snapshot.icons if i.id == icon_id), None)

    def upsert_icon(self, icon: Icon) -> None:
        icons = [i for i in self._snapshot.icons if i.id != icon.id]
        icons.append(icon)
        self._snapshot = self._snapshot.model_copy(update={"icons": icons})
        self._flush()

    def delete_icon(self, icon_id: str) -> None:
        icons = [i for i in self._snapshot.icons if i.id != icon_id]
        self._snapshot = self._snapshot.model_copy(update={"icons": icons})
        self._flush()

    # ---- snapshot --------------------------------------------------------

    def export_snapshot(self) -> Snapshot:
        return self._snapshot.model_copy(deep=True)

    def import_snapshot(self, snapshot: Snapshot) -> None:
        self._snapshot = snapshot.model_copy(deep=True)
        self._flush()

    # ---- lifecycle -------------------------------------------------------

    def close(self) -> None:
        # No persistent handle to close — every mutation already flushed.
        pass

    def __repr__(self) -> str:  # pragma: no cover
        return f"FileStorage(path={self._path!r})"
