"""On-disk pre-composited key-image cache.

Each cached entry is keyed by ``(page_id, slot, state_value)`` and lives at
``data_dir/cache/keys/<page_id>/<slot>/<safe_state>.png``. The painter
populates the cache lazily on first render of a (key, state) combination,
then re-uses the bytes on subsequent renders until invalidated.

State values are coerced to filesystem-safe filenames (alphanumerics + ``_``
+ ``-`` survive; everything else becomes ``_``). The empty / "no state yet"
case uses the literal sentinel ``__default__``.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from deckbridge.logging_ import get_logger

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger(__name__)

DEFAULT_STATE = "__default__"


class KeyImageCache:
    """Thin wrapper over ``data_dir/cache/keys/`` for pre-rendered PNG bytes."""

    def __init__(self, data_dir: Path) -> None:
        self._root = data_dir / "cache" / "keys"
        self._root.mkdir(parents=True, exist_ok=True)

    def get(self, page_id: str, slot: int, state_value: str | None) -> bytes | None:
        path = self._path(page_id, slot, state_value)
        if not path.is_file():
            return None
        try:
            return path.read_bytes()
        except OSError as exc:
            log.warning("cache_read_failed", path=str(path), error=repr(exc))
            return None

    def put(
        self,
        page_id: str,
        slot: int,
        state_value: str | None,
        image: bytes,
    ) -> None:
        path = self._path(page_id, slot, state_value)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_bytes(image)
        except OSError as exc:
            log.warning("cache_write_failed", path=str(path), error=repr(exc))

    def invalidate_key(self, page_id: str, slot: int) -> None:
        """Remove every cached variant for a single (page, slot)."""
        key_dir = self._root / _safe(page_id) / str(slot)
        if key_dir.is_dir():
            shutil.rmtree(key_dir, ignore_errors=True)

    def invalidate_page(self, page_id: str) -> None:
        """Remove every cached image under a page (used on page deletion)."""
        page_dir = self._root / _safe(page_id)
        if page_dir.is_dir():
            shutil.rmtree(page_dir, ignore_errors=True)

    def _path(self, page_id: str, slot: int, state_value: str | None) -> Path:
        state = _safe(state_value) if state_value else DEFAULT_STATE
        return self._root / _safe(page_id) / str(slot) / f"{state}.png"


def _safe(value: str) -> str:
    """Filesystem-safe version of *value* (alphanumerics + ``_``/``-`` survive)."""
    out = []
    for ch in value:
        out.append(ch if ch.isalnum() or ch in "-_" else "_")
    safe = "".join(out)
    return safe or "_"
