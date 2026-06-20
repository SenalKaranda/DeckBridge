"""Per-deck active-page tracker.

Plain in-memory dict, indexed by deck serial. Active page state is intentionally
not persisted across restarts in v1: when a deck reconnects, the dispatcher
re-initializes from storage (Deck.home_page_id, falling back to the first page
in the deck's pages list).
"""

from __future__ import annotations


class ActivePages:
    """Tracks which page is currently visible on each connected deck."""

    def __init__(self) -> None:
        self._by_deck: dict[str, str] = {}

    def get(self, deck_serial: str) -> str | None:
        return self._by_deck.get(deck_serial)

    def set(self, deck_serial: str, page_id: str) -> None:
        self._by_deck[deck_serial] = page_id

    def clear(self, deck_serial: str) -> None:
        self._by_deck.pop(deck_serial, None)

    def all(self) -> dict[str, str]:
        """Snapshot copy."""
        return dict(self._by_deck)
