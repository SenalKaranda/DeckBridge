"""Typed events flowing on the DeckBridge in-process EventBus.

Each subsystem (device, mqtt, http, etc.) publishes events of one of these
types and may subscribe to any others. The set is intentionally small in M1
and grows alongside the subsystems that emit them (M2: device, M6: mqtt,
M8: log streaming).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Event:
    """Marker base class for every typed event."""


# ---- Lifecycle ----


@dataclass(frozen=True, slots=True)
class DaemonStarted(Event):
    """Emitted once after all subsystems have completed startup."""


@dataclass(frozen=True, slots=True)
class DaemonStopping(Event):
    """Emitted at the start of graceful shutdown, before any subsystem closes."""


# ---- Device (M2 will populate the rest) ----


@dataclass(frozen=True, slots=True)
class DeckConnected(Event):
    serial: str
    model: str


@dataclass(frozen=True, slots=True)
class DeckDisconnected(Event):
    serial: str


@dataclass(frozen=True, slots=True)
class KeyPressed(Event):
    serial: str
    key: int


# ---- Broker (M6) -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class BrokerConnected(Event):
    """Emitted whenever the MQTT client opens a fresh session."""

    host: str


@dataclass(frozen=True, slots=True)
class BrokerDisconnected(Event):
    """Emitted whenever the active MQTT session ends (graceful or error)."""


# ---- Page navigation (M6) -------------------------------------------


@dataclass(frozen=True, slots=True)
class ActivePageChanged(Event):
    """Emitted when a deck switches to a different page (page-switch action,
    deck-attach default, or programmatic change). The painter listens to
    redraw the deck for the new page."""

    serial: str
    page_id: str


# ---- State + key config (M6c) ---------------------------------------


@dataclass(frozen=True, slots=True)
class KeyStateUpdated(Event):
    """Emitted when an MQTT subscription resolves a new state value for a key.

    The painter listens for this and re-renders the affected key with the
    state-mapped icon. ``value`` is always a string (JMESPath result is
    coerced to ``str``; raw payloads are decoded as utf-8 with replacement).
    """

    page_id: str
    slot: int
    value: str


@dataclass(frozen=True, slots=True)
class KeyConfigChanged(Event):
    """Emitted when a key's stored configuration changed (PUT/DELETE on the
    keys API). The painter invalidates its render cache for this key and
    re-renders if the key's page is currently visible. The state subscriber
    re-evaluates the topic-to-keys subscription map.
    """

    page_id: str
    slot: int


@dataclass(frozen=True, slots=True)
class PageConfigChanged(Event):
    """Emitted when a page's stored configuration changed (POST/PATCH/DELETE
    on the pages API). The dispatcher uses this to wake up an attached deck
    that didn't have any pages at attach-time: when the user authors the
    first page from the editor, the dispatcher picks it up here, sets it
    as the active page, and the painter re-renders the deck.

    ``deck_serial`` is the page's binding (or its OLD binding on delete)
    so subscribers can scope their reaction to one deck without scanning
    the whole storage.
    """

    page_id: str
    deck_serial: str
