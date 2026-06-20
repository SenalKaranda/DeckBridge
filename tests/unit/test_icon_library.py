"""IconLibrary: bundled lookup, upload + dedupe + validation, delete."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest
from PIL import Image

from deckbridge.icons.library import (
    ALLOWED_CONTENT_TYPES,
    MAX_UPLOAD_BYTES,
    IconError,
    IconLibrary,
)
from deckbridge.storage import SqliteStorage, run_migrations
from deckbridge.storage.schema import Icon, IconSource


def _png_bytes(
    color: tuple[int, int, int] = (10, 20, 30), size: tuple[int, int] = (16, 16)
) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def library(tmp_path: Path) -> IconLibrary:
    storage = SqliteStorage(":memory:")
    run_migrations(storage)
    return IconLibrary(storage, tmp_path)


# ---- upload --------------------------------------------------------------


def test_upload_persists_record_and_bytes(library: IconLibrary, tmp_path: Path) -> None:
    raw = _png_bytes((200, 50, 50))
    icon = library.upload(name="kitchen", content_type="image/png", raw=raw)

    assert icon.source == IconSource.UPLOADED
    assert icon.sha256 == hashlib.sha256(raw).hexdigest()
    assert icon.id.startswith("upl:")
    # Bytes are retrievable.
    assert library.get_bytes(icon.id) == raw
    # File exists on disk under data_dir/icons/uploaded/.
    on_disk = tmp_path / "icons" / "uploaded" / icon.reference
    assert on_disk.is_file()


def test_upload_dedupes_by_sha256(library: IconLibrary) -> None:
    raw = _png_bytes((1, 2, 3))
    first = library.upload(name="first", content_type="image/png", raw=raw)
    second = library.upload(name="second-name", content_type="image/png", raw=raw)
    assert first.id == second.id


def test_upload_rejects_unknown_content_type(library: IconLibrary) -> None:
    with pytest.raises(IconError, match="Unsupported"):
        library.upload(name="x", content_type="image/gif", raw=_png_bytes())


def test_upload_rejects_empty(library: IconLibrary) -> None:
    with pytest.raises(IconError, match="empty"):
        library.upload(name="x", content_type="image/png", raw=b"")


def test_upload_rejects_too_large(library: IconLibrary) -> None:
    with pytest.raises(IconError, match="too large"):
        library.upload(
            name="x",
            content_type="image/png",
            raw=b"\x89PNG" + b"0" * (MAX_UPLOAD_BYTES),
        )


def test_upload_accepts_jpeg(library: IconLibrary) -> None:
    img = Image.new("RGB", (20, 20), (40, 40, 40))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    raw = buf.getvalue()
    icon = library.upload(name="x", content_type="image/jpeg", raw=raw)
    assert icon.reference.endswith(".jpg")
    assert library.get_bytes(icon.id) == raw


def test_allowed_content_types_includes_png_and_jpeg() -> None:
    assert "image/png" in ALLOWED_CONTENT_TYPES
    assert "image/jpeg" in ALLOWED_CONTENT_TYPES


# ---- read / delete -------------------------------------------------------


def test_get_bytes_missing_icon_returns_none(library: IconLibrary) -> None:
    assert library.get_bytes("upl:nope") is None


def test_delete_removes_file_and_record(library: IconLibrary, tmp_path: Path) -> None:
    icon = library.upload(name="x", content_type="image/png", raw=_png_bytes((9, 9, 9)))
    on_disk = tmp_path / "icons" / "uploaded" / icon.reference
    assert on_disk.is_file()

    library.delete(icon.id)
    assert not on_disk.exists()
    assert library.get_bytes(icon.id) is None


def test_delete_missing_icon_is_noop(library: IconLibrary) -> None:
    library.delete("upl:nope")  # must not raise


def test_cannot_delete_bundled(library: IconLibrary) -> None:
    """Bundled icons are package resources and must not be deletable."""
    storage = library._storage
    storage.upsert_icon(Icon(id="lucide:home", source=IconSource.BUNDLED, reference="home"))
    with pytest.raises(IconError, match="Bundled"):
        library.delete("lucide:home")


# ---- bundled discovery ---------------------------------------------------


def test_discover_bundled_registers_lucide_icons(library: IconLibrary) -> None:
    """v1 bundles ~80 Lucide PNGs; discover registers each as a storage record."""
    added = library.discover_bundled()
    assert added > 50, f"expected most of the curated Lucide set, got {added}"
    # Spot-check a known icon from the v1 list.
    icon = library._storage.get_icon("lucide:lightbulb")
    assert icon is not None
    assert icon.source == IconSource.BUNDLED
    assert icon.reference == "lightbulb"
    # Bytes are readable.
    raw = library.get_bytes("lucide:lightbulb")
    assert raw is not None
    assert raw.startswith(b"\x89PNG")


def test_discover_bundled_is_idempotent(library: IconLibrary) -> None:
    library.discover_bundled()
    second_pass = library.discover_bundled()
    assert second_pass == 0, "second pass should add no new icons"
