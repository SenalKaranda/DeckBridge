"""Home Assistant MQTT Discovery integration.

Publishes a device-trigger configuration to the broker for every slot on
every attached deck so HA picks them up automatically (no YAML on the HA
side). When a key is pressed, we publish ``{slot}`` to the deck's trigger
topic; HA fires whatever automation the user wired to that trigger.

Topic shape:

    homeassistant/device_automation/deckbridge_{serial}_key_{slot}/config
        -> retained JSON describing the trigger (per HA's MQTT Discovery spec)

    deckbridge/{serial}/key_pressed
        -> ``str(slot)`` published every time the deck fires a KeyPressed event

Re-publishes on every broker reconnect (HA persists the retained discovery
payloads but the broker may have lost them too — re-publishing is cheap and
idempotent). Best-effort retract on daemon shutdown by sending an empty
retained payload to each discovery topic.

The publisher is a no-op when ``preferences.ha_discovery_enabled`` is
False — the user can toggle this in the settings UI.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from deckbridge import __version__
from deckbridge.events.types import (
    BrokerConnected,
    DaemonStopping,
    DeckConnected,
    Event,
    KeyPressed,
)
from deckbridge.logging_ import get_logger

if TYPE_CHECKING:
    from deckbridge.device.manager import DeckManager
    from deckbridge.events import EventBus
    from deckbridge.mqtt.client import MqttClient
    from deckbridge.storage import Storage


def discovery_topic(serial: str, slot: int) -> str:
    return f"homeassistant/device_automation/deckbridge_{serial}_key_{slot}/config"


def trigger_topic(serial: str) -> str:
    return f"deckbridge/{serial}/key_pressed"


class HADiscovery:
    def __init__(
        self,
        bus: EventBus,
        storage: Storage,
        mqtt_client: MqttClient,
        deck_manager: DeckManager,
    ) -> None:
        self._bus = bus
        self._storage = storage
        self._mqtt = mqtt_client
        self._deck_manager = deck_manager
        # Track what we've ever published so we know what to retract on stop.
        self._published: set[tuple[str, int]] = set()
        self._log = get_logger(__name__)

        bus.subscribe(BrokerConnected, self._on_broker_connected)
        bus.subscribe(DeckConnected, self._on_deck_connected)
        bus.subscribe(KeyPressed, self._on_key_pressed)
        bus.subscribe(DaemonStopping, self._on_daemon_stopping)

    # ---- enablement gate ------------------------------------------------

    def _enabled(self) -> bool:
        return self._storage.get_preferences().ha_discovery_enabled

    # ---- handlers --------------------------------------------------------

    async def _on_broker_connected(self, event: Event) -> None:
        if not isinstance(event, BrokerConnected) or not self._enabled():
            return
        for deck in self._deck_manager.decks.values():
            await self._publish_for_deck(deck.serial, deck.model, deck.key_count)

    async def _on_deck_connected(self, event: Event) -> None:
        if not isinstance(event, DeckConnected) or not self._enabled():
            return
        # Use the deck instance from the manager for key_count (DeckConnected
        # only carries serial + model).
        deck = self._deck_manager.decks.get(event.serial)
        key_count = deck.key_count if deck is not None else 15
        await self._publish_for_deck(event.serial, event.model, key_count)

    async def _on_key_pressed(self, event: Event) -> None:
        if not isinstance(event, KeyPressed) or not self._enabled():
            return
        await self._mqtt.publish(trigger_topic(event.serial), str(event.key))

    async def _on_daemon_stopping(self, event: Event) -> None:
        if not isinstance(event, DaemonStopping):
            return
        # Always attempt retract on shutdown so that toggling HA Discovery
        # off mid-life and then restarting cleans up automatically. Empty
        # retained payload is the documented HA retract idiom.
        for serial, slot in list(self._published):
            await self._mqtt.publish(discovery_topic(serial, slot), "", retain=True)
        self._published.clear()

    # ---- publish helpers ------------------------------------------------

    async def _publish_for_deck(self, serial: str, model: str, key_count: int) -> None:
        for slot in range(key_count):
            payload = self._discovery_payload(serial, model, slot)
            await self._mqtt.publish(
                discovery_topic(serial, slot),
                json.dumps(payload),
                retain=True,
                qos=1,
            )
            self._published.add((serial, slot))
        self._log.info(
            "ha_discovery_published",
            serial=serial,
            model=model,
            count=key_count,
        )

    @staticmethod
    def _discovery_payload(serial: str, model: str, slot: int) -> dict[str, object]:
        return {
            "automation_type": "trigger",
            "topic": trigger_topic(serial),
            "payload": str(slot),
            "type": "button_short_press",
            "subtype": f"key_{slot}",
            "device": {
                "identifiers": [f"deckbridge_{serial}"],
                "name": f"DeckBridge {serial}",
                "manufacturer": "DeckBridge",
                "model": model or "Stream Deck",
                "sw_version": __version__,
            },
        }
