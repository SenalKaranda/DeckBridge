"""KeyImageCache — disk get/put/invalidate semantics."""

from __future__ import annotations

from pathlib import Path

from deckbridge.device.cache import DEFAULT_STATE, KeyImageCache


def test_get_missing_returns_none(tmp_path: Path) -> None:
    cache = KeyImageCache(tmp_path)
    assert cache.get("p1", 0, "on") is None


def test_put_then_get(tmp_path: Path) -> None:
    cache = KeyImageCache(tmp_path)
    cache.put("p1", 0, "on", b"\x89PNG-data")
    assert cache.get("p1", 0, "on") == b"\x89PNG-data"


def test_default_state_when_value_is_none(tmp_path: Path) -> None:
    cache = KeyImageCache(tmp_path)
    cache.put("p1", 0, None, b"x")
    expected = tmp_path / "cache" / "keys" / "p1" / "0" / f"{DEFAULT_STATE}.png"
    assert expected.is_file()
    assert cache.get("p1", 0, None) == b"x"


def test_state_value_is_filesystem_safe(tmp_path: Path) -> None:
    cache = KeyImageCache(tmp_path)
    cache.put("p1", 0, "on/off:weird", b"x")
    # Slashes / colons sanitized. Round-trip works.
    assert cache.get("p1", 0, "on/off:weird") == b"x"


def test_invalidate_key_removes_all_variants(tmp_path: Path) -> None:
    cache = KeyImageCache(tmp_path)
    cache.put("p1", 0, "on", b"on")
    cache.put("p1", 0, "off", b"off")
    cache.put("p1", 1, "on", b"x")  # different slot

    cache.invalidate_key("p1", 0)

    assert cache.get("p1", 0, "on") is None
    assert cache.get("p1", 0, "off") is None
    # Different slot untouched.
    assert cache.get("p1", 1, "on") == b"x"


def test_invalidate_page_removes_all_keys(tmp_path: Path) -> None:
    cache = KeyImageCache(tmp_path)
    cache.put("p1", 0, "on", b"a")
    cache.put("p1", 5, "off", b"b")
    cache.put("p2", 0, "on", b"c")

    cache.invalidate_page("p1")

    assert cache.get("p1", 0, "on") is None
    assert cache.get("p1", 5, "off") is None
    assert cache.get("p2", 0, "on") == b"c"


def test_invalidate_unknown_is_noop(tmp_path: Path) -> None:
    cache = KeyImageCache(tmp_path)
    cache.invalidate_key("nope", 99)  # must not raise
    cache.invalidate_page("nope")
