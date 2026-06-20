"""Press-action dispatch and per-deck active-page tracking.

The :class:`PressDispatcher` translates :class:`~deckbridge.events.KeyPressed`
events into the configured action (MQTT publish, HTTP webhook, page switch,
no-op). Active-page state is held by :class:`ActivePages`, a small in-memory
tracker indexed by deck serial.
"""

from deckbridge.actions.active_pages import ActivePages
from deckbridge.actions.dispatcher import PressDispatcher

__all__ = ["ActivePages", "PressDispatcher"]
