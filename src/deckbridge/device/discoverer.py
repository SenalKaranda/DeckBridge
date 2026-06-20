"""Stream Deck device discovery.

A *discoverer* is a callable that returns the currently-connected (but
unopened) deck handles. The production discoverer wraps the third-party
``StreamDeck`` library; tests inject their own discoverer that returns
:class:`tests.fixtures.fake_deck.FakeStreamDeck` instances instead.

This is the only module in the package that imports ``StreamDeck`` (and it
does so lazily so that import-time problems on systems without ``hidapi``
never crash the daemon — they just produce an empty enumeration).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from deckbridge.logging_ import get_logger

log = get_logger(__name__)

# A Discoverer returns currently-connected, unopened deck handles. Each handle
# must satisfy the duck-typed interface used by deckbridge.device.deck.Deck:
# open(), close(), key_count(), get_serial_number(), set_key_callback(...).
Discoverer = Callable[[], Iterable[Any]]


def real_discoverer() -> list[Any]:
    """Production discoverer.

    Returns currently-connected Stream Deck handles via the third-party
    library. On any failure (missing ``hidapi`` shared library, USB transport
    init error, no permission, etc.) the failure is logged at WARNING and an
    empty list is returned so the daemon continues to start.
    """
    try:
        from StreamDeck.DeviceManager import DeviceManager

        return list(DeviceManager().enumerate())
    except Exception as exc:
        log.warning("deck_enumeration_failed", error=repr(exc))
        return []
