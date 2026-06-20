"""PressDispatcher — translate KeyPressed events into the configured action.

Subscribes to :class:`~deckbridge.events.KeyPressed` events on the bus.
For each event, looks up the active page for the deck, fetches the configured
:class:`~deckbridge.storage.schema.Key`, and executes its press action:

* :class:`~deckbridge.storage.schema.MQTTPublishAction` -> queue a publish on
  the broker (delivered when the broker is reachable).
* :class:`~deckbridge.storage.schema.HTTPWebhookAction` -> async HTTP request
  via the injected httpx client.
* :class:`~deckbridge.storage.schema.PageSwitchAction` -> update the active
  page for the deck and emit
  :class:`~deckbridge.events.ActivePageChanged` so the painter (M6c) redraws.
* :class:`~deckbridge.storage.schema.NoOpAction` -> log only.

Also handles :class:`~deckbridge.events.DeckConnected` events: on connect, if
no active page is set yet, pick the deck's ``home_page_id`` (if it points to
a real page) or the first page in deck-order; emit ActivePageChanged so the
painter renders the initial layout.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from deckbridge.events.types import (
    ActivePageChanged,
    DeckConnected,
    Event,
    KeyPressed,
    PageConfigChanged,
)
from deckbridge.logging_ import get_logger
from deckbridge.storage.schema import (
    HTTPWebhookAction,
    MQTTPublishAction,
    NoOpAction,
    PageSwitchAction,
)

if TYPE_CHECKING:
    import httpx

    from deckbridge.actions.active_pages import ActivePages
    from deckbridge.device.manager import DeckManager
    from deckbridge.events import EventBus
    from deckbridge.mqtt import MqttClient
    from deckbridge.storage import Storage
    from deckbridge.storage.schema import PressAction


_HTTP_TIMEOUT_SECONDS = 10.0


class PressDispatcher:
    """Subscribes to KeyPressed/DeckConnected and runs the corresponding action."""

    def __init__(
        self,
        bus: EventBus,
        storage: Storage,
        mqtt_client: MqttClient,
        active_pages: ActivePages,
        http_client: httpx.AsyncClient,
        deck_manager: DeckManager | None = None,
    ) -> None:
        self._bus = bus
        self._storage = storage
        self._mqtt = mqtt_client
        self._active_pages = active_pages
        self._http = http_client
        # Optional so existing tests (which build a dispatcher without
        # device hardware) continue to construct it the old way. The
        # PageConfigChanged auto-activate path needs it; everything else
        # works without.
        self._deck_manager = deck_manager
        self._log = get_logger(__name__)

        bus.subscribe(KeyPressed, self._on_key_pressed)
        bus.subscribe(DeckConnected, self._on_deck_connected)
        bus.subscribe(PageConfigChanged, self._on_page_config_changed)

    # ---- event handlers --------------------------------------------------

    async def _on_deck_connected(self, event: Event) -> None:
        if not isinstance(event, DeckConnected):
            return
        await self._activate_page_if_needed(event.serial)

    async def _on_page_config_changed(self, event: Event) -> None:
        """A page was created/edited/deleted via the API.

        Wake up any attached deck that doesn't yet have an active page —
        the user typically authors the first page from the editor AFTER
        the deck has already attached, and without this nudge the
        dispatcher's `_active_pages` would stay empty (and the painter
        would never paint the deck).
        """
        if not isinstance(event, PageConfigChanged):
            return
        # Try to (re)activate every attached deck. The method short-
        # circuits for decks that already have an active page, so this
        # is cheap. We use the DeckManager because storage doesn't
        # persist a record of attached decks (attach is in-memory only).
        if self._deck_manager is not None:
            for serial in list(self._deck_manager.decks.keys()):
                await self._activate_page_if_needed(serial)
        # Always also try the event's deck_serial directly: covers the
        # narrow case where the dispatcher has no DeckManager wired up
        # (older tests) and the page was bound to a real attached deck.
        if event.deck_serial:
            await self._activate_page_if_needed(event.deck_serial)

    async def _activate_page_if_needed(self, deck_serial: str) -> None:
        if self._active_pages.get(deck_serial) is not None:
            # Already initialized (e.g. from a previous attach in this run).
            return
        page_id = self._pick_initial_page(deck_serial)
        if page_id is None:
            self._log.info("no_pages_configured", serial=deck_serial)
            return
        self._active_pages.set(deck_serial, page_id)
        await self._bus.publish(ActivePageChanged(serial=deck_serial, page_id=page_id))

    async def _on_key_pressed(self, event: Event) -> None:
        if not isinstance(event, KeyPressed):
            return
        active_page_id = self._active_pages.get(event.serial)
        if active_page_id is None:
            self._log.info("press_ignored_no_active_page", serial=event.serial, slot=event.key)
            return
        key = self._storage.get_key(active_page_id, event.key)
        if key is None:
            self._log.debug(
                "press_on_empty_slot",
                serial=event.serial,
                page_id=active_page_id,
                slot=event.key,
            )
            return
        await self.execute(event.serial, key.press)

    # ---- public action runner (used by KeyPressed handler + test-press M6d)

    async def execute(self, serial: str, action: PressAction) -> None:
        if isinstance(action, NoOpAction):
            self._log.debug("action_noop", serial=serial)
            return
        if isinstance(action, MQTTPublishAction):
            await self._mqtt.publish(
                action.topic,
                action.payload,
                retain=action.retain,
                qos=action.qos,
            )
            self._log.info(
                "action_mqtt_published",
                serial=serial,
                topic=action.topic,
                qos=action.qos,
                retain=action.retain,
            )
            return
        if isinstance(action, HTTPWebhookAction):
            try:
                response = await self._http.request(
                    action.method,
                    action.url,
                    headers=action.headers or None,
                    content=action.body.encode("utf-8") if action.body else None,
                    timeout=_HTTP_TIMEOUT_SECONDS,
                )
                self._log.info(
                    "action_http_fired",
                    serial=serial,
                    url=action.url,
                    method=action.method,
                    status_code=response.status_code,
                )
            except Exception as exc:
                self._log.warning(
                    "action_http_failed",
                    serial=serial,
                    url=action.url,
                    error=repr(exc),
                )
            return
        if isinstance(action, PageSwitchAction):
            target = action.target_page_id
            if self._storage.get_page(target) is None:
                self._log.warning(
                    "page_switch_target_missing", serial=serial, target_page_id=target
                )
                return
            self._active_pages.set(serial, target)
            await self._bus.publish(ActivePageChanged(serial=serial, page_id=target))
            self._log.info("action_page_switch", serial=serial, target_page_id=target)
            return
        # Unknown PressAction subtype — schema discriminator should prevent this,
        # but log loudly if it happens.
        self._log.warning("unknown_press_action_type", action_type=type(action).__name__)

    # ---- internals -------------------------------------------------------

    def _pick_initial_page(self, deck_serial: str) -> str | None:
        deck = self._storage.get_deck(deck_serial)
        if deck is not None and deck.home_page_id:
            home = self._storage.get_page(deck.home_page_id)
            if home is not None and home.deck_serial == deck_serial:
                return home.id
        # Fall back to the first page bound to this deck (storage sorts by order).
        pages = self._storage.list_pages(deck_serial=deck_serial)
        if pages:
            return pages[0].id
        # Editor-without-deck flow: pages may have been authored against the
        # literal "default" serial before the deck attached. Fall back to that.
        if deck_serial != "default":
            default_pages = self._storage.list_pages(deck_serial="default")
            if default_pages:
                return default_pages[0].id
        return None
