"""Icon library — bundled (Lucide) and user-uploaded.

Two lookup paths:

* **Bundled icons** are PNGs shipped under :mod:`deckbridge.icons.bundled`.
  They're discovered from the package's installed location and exposed under
  the icon ID prefix ``lucide:``. v1 ships ~85 curated Lucide icons; see
  ``scripts/build_bundled_assets.py`` to refresh the set.

* **Uploaded icons** are PNGs/JPEGs the user has POSTed via the API. They
  live under ``data_dir / icons / uploaded`` and are content-addressed by
  SHA-256 so re-uploading the same image is a no-op.

The library mediates between :class:`~deckbridge.storage.Storage` (which
holds metadata) and the filesystem (which holds bytes). Callers who only
need bytes use :meth:`get_bytes`; those who need to enumerate use the
storage's :meth:`~deckbridge.storage.Storage.list_icons`.
"""

from __future__ import annotations

import hashlib
from importlib.resources import as_file, files
from typing import TYPE_CHECKING

from deckbridge.logging_ import get_logger
from deckbridge.storage.schema import Icon, IconSource

if TYPE_CHECKING:
    from pathlib import Path

    from deckbridge.storage import Storage

log = get_logger(__name__)

ALLOWED_CONTENT_TYPES = frozenset({"image/png", "image/jpeg"})
"""Content types accepted by :meth:`IconLibrary.upload`. Stream Deck rendering
prefers PNG; JPEG is allowed for convenience."""

MAX_UPLOAD_BYTES = 1 * 1024 * 1024  # 1 MiB
"""Reject uploads larger than this. A 72x72 PNG is well under 100 KiB; 1 MiB
is a generous upper bound that still rejects accidental 4K uploads."""


class IconError(Exception):
    """Raised for invalid uploads (wrong type, too big, malformed)."""


class IconLibrary:
    """Manages icon bytes on disk and metadata in storage."""

    BUNDLED_PREFIX = "lucide:"

    def __init__(self, storage: Storage, data_dir: Path) -> None:
        self._storage = storage
        self._uploaded_dir = data_dir / "icons" / "uploaded"
        self._uploaded_dir.mkdir(parents=True, exist_ok=True)

    # ---- read ------------------------------------------------------------

    def get_bytes(self, icon_id: str) -> bytes | None:
        """Return raw image bytes for an icon, or None if missing."""
        icon = self._storage.get_icon(icon_id)
        if icon is None:
            return None
        if icon.source == IconSource.BUNDLED:
            return self._read_bundled(icon.reference)
        return self._read_uploaded(icon.reference)

    def _read_bundled(self, reference: str) -> bytes | None:
        # Use importlib.resources so this works whether the package is
        # installed editable, in a wheel, or zipped.
        try:
            resource = files("deckbridge.icons.bundled") / f"{reference}.png"
        except ModuleNotFoundError:
            return None
        with as_file(resource) as path:
            if not path.is_file():
                return None
            return path.read_bytes()

    def _read_uploaded(self, reference: str) -> bytes | None:
        path = self._uploaded_dir / reference
        if not path.is_file():
            return None
        return path.read_bytes()

    # ---- write -----------------------------------------------------------

    def upload(self, *, name: str, content_type: str, raw: bytes) -> Icon:
        """Persist an uploaded image, returning the (new or existing) Icon record.

        Validation and dedupe:

        * Rejects non-PNG/JPEG content types.
        * Rejects bodies larger than :data:`MAX_UPLOAD_BYTES`.
        * If the SHA-256 of *raw* matches an existing uploaded icon, returns
          that existing icon (no second copy on disk).
        """
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise IconError(
                f"Unsupported content type {content_type!r}. "
                f"Allowed: {sorted(ALLOWED_CONTENT_TYPES)}."
            )
        if len(raw) > MAX_UPLOAD_BYTES:
            raise IconError(f"Upload too large: {len(raw)} bytes (max {MAX_UPLOAD_BYTES}).")
        if not raw:
            raise IconError("Upload is empty.")

        digest = hashlib.sha256(raw).hexdigest()

        # Dedupe: if the same bytes were already uploaded, return that record.
        for existing in self._storage.list_icons():
            if existing.source == IconSource.UPLOADED and existing.sha256 == digest:
                log.info("icon_upload_dedup", icon_id=existing.id, sha256=digest)
                return existing

        suffix = ".png" if content_type == "image/png" else ".jpg"
        filename = f"{digest}{suffix}"
        path = self._uploaded_dir / filename
        path.write_bytes(raw)

        icon = Icon(
            id=f"upl:{digest[:12]}",
            name=name or filename,
            source=IconSource.UPLOADED,
            reference=filename,
            sha256=digest,
        )
        self._storage.upsert_icon(icon)
        log.info("icon_uploaded", icon_id=icon.id, sha256=digest, bytes=len(raw))
        return icon

    def delete(self, icon_id: str) -> None:
        """Delete an uploaded icon (metadata + bytes). Bundled icons are immutable."""
        icon = self._storage.get_icon(icon_id)
        if icon is None:
            return
        if icon.source != IconSource.UPLOADED:
            raise IconError("Bundled icons cannot be deleted.")
        path = self._uploaded_dir / icon.reference
        if path.exists():
            path.unlink()
        self._storage.delete_icon(icon_id)
        log.info("icon_deleted", icon_id=icon_id)

    # ---- bundled discovery -----------------------------------------------

    def discover_bundled(self) -> int:
        """Scan the bundled icons directory and ensure every file has a storage record.

        Returns the number of NEW bundled icons registered (those already
        registered are left alone). Safe to call repeatedly; called once at
        daemon startup so newly-bundled icons in upgrades become available.
        """
        try:
            bundled = files("deckbridge.icons.bundled")
        except ModuleNotFoundError:
            return 0

        added = 0
        for entry in bundled.iterdir():
            name = entry.name
            if not name.endswith(".png"):
                continue
            stem = name[:-4]
            icon_id = f"{self.BUNDLED_PREFIX}{stem}"
            if self._storage.get_icon(icon_id) is not None:
                continue
            self._storage.upsert_icon(
                Icon(
                    id=icon_id,
                    name=stem.replace("-", " ").title(),
                    source=IconSource.BUNDLED,
                    reference=stem,
                )
            )
            added += 1

        if added:
            log.info("bundled_icons_registered", count=added)
        return added
