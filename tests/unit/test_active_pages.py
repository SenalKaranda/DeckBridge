"""ActivePages tracker — basic get/set/clear semantics."""

from __future__ import annotations

from deckbridge.actions import ActivePages


def test_get_unknown_returns_none() -> None:
    ap = ActivePages()
    assert ap.get("ABC") is None


def test_set_then_get() -> None:
    ap = ActivePages()
    ap.set("ABC", "page-1")
    assert ap.get("ABC") == "page-1"


def test_set_overwrites() -> None:
    ap = ActivePages()
    ap.set("ABC", "page-1")
    ap.set("ABC", "page-2")
    assert ap.get("ABC") == "page-2"


def test_clear_removes_entry() -> None:
    ap = ActivePages()
    ap.set("ABC", "page-1")
    ap.clear("ABC")
    assert ap.get("ABC") is None


def test_clear_unknown_is_noop() -> None:
    ap = ActivePages()
    ap.clear("missing")  # must not raise


def test_per_deck_isolation() -> None:
    ap = ActivePages()
    ap.set("A", "p1")
    ap.set("B", "p2")
    assert ap.get("A") == "p1"
    assert ap.get("B") == "p2"


def test_all_returns_snapshot() -> None:
    ap = ActivePages()
    ap.set("A", "p1")
    ap.set("B", "p2")
    snap = ap.all()
    assert snap == {"A": "p1", "B": "p2"}
    # Mutating the snapshot must not affect the tracker.
    snap["A"] = "mutated"
    assert ap.get("A") == "p1"
