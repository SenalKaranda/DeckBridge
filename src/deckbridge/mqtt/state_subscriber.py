"""StateSubscriber — wire MQTT messages into per-key state events.

For every key that has a ``state`` subscription, subscribes to the topic on
the broker and emits :class:`~deckbridge.events.KeyStateUpdated` whenever a
matching message arrives. JMESPath extracts the value from JSON payloads;
plaintext payloads are used directly (utf-8, replacement-decoded).

Re-evaluates its subscription set on every :class:`BrokerConnected` (so the
subscriber recovers after a reconnect) and every
:class:`~deckbridge.events.KeyConfigChanged` (so newly-configured topics
get picked up immediately and removed-topic keys stop emitting).

Note: we never explicitly unsubscribe at the broker level (MqttClient's
unsubscribe is best-effort); over-subscribed topics just get a few extra
inbound messages we ignore.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import jmespath

from deckbridge.events.types import (
    BrokerConnected,
    Event,
    KeyConfigChanged,
    KeyStateUpdated,
)
from deckbridge.logging_ import get_logger

if TYPE_CHECKING:
    from deckbridge.events import EventBus
    from deckbridge.mqtt.client import MqttClient
    from deckbridge.storage import Storage
    from deckbridge.storage.schema import StateSubscription


class StateSubscriber:
    def __init__(self, bus: EventBus, storage: Storage, mqtt_client: MqttClient) -> None:
        self._bus = bus
        self._storage = storage
        self._mqtt = mqtt_client
        # Topics we've already asked the broker to send to us. Used to skip
        # redundant resubscribes on every config change.
        self._subscribed_topics: set[str] = set()
        self._log = get_logger(__name__)

        bus.subscribe(BrokerConnected, self._on_broker_connected)
        bus.subscribe(KeyConfigChanged, self._on_key_config_changed)

    # ---- event handlers --------------------------------------------------

    async def _on_broker_connected(self, event: Event) -> None:
        if not isinstance(event, BrokerConnected):
            return
        # Force resubscribe of every topic — the broker forgot us when the
        # session dropped.
        self._subscribed_topics.clear()
        self._refresh_subscriptions()

    async def _on_key_config_changed(self, event: Event) -> None:
        if not isinstance(event, KeyConfigChanged):
            return
        self._refresh_subscriptions()

    # ---- subscription bookkeeping ---------------------------------------

    def _refresh_subscriptions(self) -> None:
        """Subscribe to every state topic referenced by any key in storage."""
        wanted = self._collect_topics()
        new_topics = wanted - self._subscribed_topics
        for topic in new_topics:
            self._mqtt.subscribe(topic, self._on_message)
            self._subscribed_topics.add(topic)
        if new_topics:
            self._log.info("state_topics_subscribed", count=len(new_topics))

    def _collect_topics(self) -> set[str]:
        topics: set[str] = set()
        for page in self._storage.list_pages():
            for key in self._storage.list_keys(page.id):
                if key.state and key.state.topic:
                    topics.add(key.state.topic)
        return topics

    # ---- inbound MQTT message dispatch ----------------------------------

    async def _on_message(self, topic: str, payload: bytes) -> None:
        # Pre-decode once for the JSON path; raw text reuse below.
        text = payload.decode("utf-8", errors="replace")
        for page in self._storage.list_pages():
            for key in self._storage.list_keys(page.id):
                if not (key.state and key.state.topic == topic):
                    continue
                value = self._extract(key.state, text)
                if value is None:
                    continue
                await self._bus.publish(
                    KeyStateUpdated(page_id=page.id, slot=key.slot, value=value)
                )

    @staticmethod
    def _extract(state: StateSubscription, text: str) -> str | None:
        """Apply JMESPath when configured; else use the whole payload as a
        trimmed string."""
        if not state.jmespath:
            return text.strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Configured as JSON but received non-JSON — treat raw payload as
            # the value rather than dropping the message.
            return text.strip()
        try:
            result = jmespath.search(state.jmespath, data)
        except jmespath.exceptions.JMESPathError:
            return None
        if result is None:
            return None
        return str(result)
