"""HADiscovery — publish/retract device-trigger configs, fire trigger payloads."""

from __future__ import annotations

import json

from deckbridge.device import DeckManager
from deckbridge.events import EventBus
from deckbridge.events.types import (
    BrokerConnected,
    DaemonStopping,
    DeckConnected,
    KeyPressed,
)
from deckbridge.mqtt import MqttClient
from deckbridge.mqtt.ha_discovery import (
    HADiscovery,
    discovery_topic,
    trigger_topic,
)
from deckbridge.storage import SqliteStorage, run_migrations
from deckbridge.storage.schema import Preferences
from tests.fixtures.fake_deck import FakeStreamDeck


def _build_storage(*, enabled: bool = True) -> SqliteStorage:
    storage = SqliteStorage(":memory:")
    run_migrations(storage)
    storage.set_preferences(Preferences(ha_discovery_enabled=enabled))
    return storage


def _build_mqtt() -> MqttClient:
    return MqttClient(EventBus(), lambda: Preferences())


def _drain_publishes(mqtt: MqttClient) -> list[tuple[str, bytes, bool, int]]:
    out = []
    while not mqtt._publish_queue.empty():
        out.append(mqtt._publish_queue.get_nowait())
    return out


async def _attached_manager(bus: EventBus, fake: FakeStreamDeck) -> DeckManager:
    manager = DeckManager(bus, lambda: [fake])
    await manager.start()
    return manager


# ---- enablement gate ---------------------------------------------------


async def test_disabled_discovery_publishes_nothing() -> None:
    bus = EventBus()
    storage = _build_storage(enabled=False)
    mqtt = _build_mqtt()
    fake = FakeStreamDeck(serial="ABC")
    manager = await _attached_manager(bus, fake)
    HADiscovery(bus, storage, mqtt, manager)

    await bus.publish(BrokerConnected(host="broker"))
    await bus.publish(DeckConnected(serial="ABC", model="MK2"))
    await bus.publish(KeyPressed(serial="ABC", key=3))

    assert _drain_publishes(mqtt) == []
    await manager.stop()


# ---- discovery payload publication ------------------------------------


async def test_deck_connected_publishes_one_config_per_slot() -> None:
    bus = EventBus()
    storage = _build_storage()
    mqtt = _build_mqtt()
    fake = FakeStreamDeck(serial="ABC")  # KEY_COUNT=15
    manager = await _attached_manager(bus, fake)
    HADiscovery(bus, storage, mqtt, manager)

    await bus.publish(DeckConnected(serial="ABC", model="MK2"))

    publishes = _drain_publishes(mqtt)
    assert len(publishes) == fake.key_count()
    for slot in range(fake.key_count()):
        topic = discovery_topic("ABC", slot)
        assert any(p[0] == topic for p in publishes), f"missing {topic}"


async def test_discovery_payload_shape_is_ha_compatible() -> None:
    bus = EventBus()
    storage = _build_storage()
    mqtt = _build_mqtt()
    fake = FakeStreamDeck(serial="ABC")
    manager = await _attached_manager(bus, fake)
    HADiscovery(bus, storage, mqtt, manager)

    await bus.publish(DeckConnected(serial="ABC", model="StreamDeckMK2"))

    publishes = _drain_publishes(mqtt)
    _topic, payload, retain, qos = next(p for p in publishes if p[0] == discovery_topic("ABC", 0))
    assert retain is True
    assert qos == 1
    body = json.loads(payload)
    assert body["automation_type"] == "trigger"
    assert body["topic"] == trigger_topic("ABC")
    assert body["payload"] == "0"
    assert body["type"] == "button_short_press"
    assert body["subtype"] == "key_0"
    assert body["device"]["identifiers"] == ["deckbridge_ABC"]
    assert body["device"]["model"] == "StreamDeckMK2"
    assert body["device"]["manufacturer"] == "DeckBridge"


async def test_broker_connected_republishes_for_attached_decks() -> None:
    """After a reconnect, we re-publish discovery for every attached deck."""
    bus = EventBus()
    storage = _build_storage()
    mqtt = _build_mqtt()
    fake = FakeStreamDeck(serial="ABC")
    manager = await _attached_manager(bus, fake)
    HADiscovery(bus, storage, mqtt, manager)
    _drain_publishes(mqtt)  # discard whatever DeckConnected from manager.start did

    await bus.publish(BrokerConnected(host="broker"))

    publishes = _drain_publishes(mqtt)
    assert len(publishes) == fake.key_count()


# ---- trigger payload --------------------------------------------------


async def test_key_pressed_publishes_trigger_payload() -> None:
    bus = EventBus()
    storage = _build_storage()
    mqtt = _build_mqtt()
    fake = FakeStreamDeck(serial="ABC")
    manager = await _attached_manager(bus, fake)
    HADiscovery(bus, storage, mqtt, manager)
    _drain_publishes(mqtt)

    await bus.publish(KeyPressed(serial="ABC", key=7))

    publishes = _drain_publishes(mqtt)
    matching = [p for p in publishes if p[0] == trigger_topic("ABC")]
    assert len(matching) == 1
    assert matching[0][1] == b"7"


# ---- retract on shutdown ---------------------------------------------


async def test_daemon_stopping_retracts_published_configs() -> None:
    bus = EventBus()
    storage = _build_storage()
    mqtt = _build_mqtt()
    fake = FakeStreamDeck(serial="ABC")
    manager = await _attached_manager(bus, fake)
    HADiscovery(bus, storage, mqtt, manager)

    await bus.publish(DeckConnected(serial="ABC", model="MK2"))
    _drain_publishes(mqtt)  # ignore initial publishes

    await bus.publish(DaemonStopping())

    publishes = _drain_publishes(mqtt)
    # One empty retained payload per (serial, slot) we previously published.
    assert len(publishes) == fake.key_count()
    for topic, payload, retain, _qos in publishes:
        assert topic.startswith("homeassistant/device_automation/deckbridge_ABC_key_")
        assert payload == b""
        assert retain is True
