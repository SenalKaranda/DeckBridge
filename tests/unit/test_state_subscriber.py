"""StateSubscriber — topic discovery, JMESPath extraction, KeyStateUpdated."""

from __future__ import annotations

from deckbridge.events import EventBus
from deckbridge.events.types import (
    BrokerConnected,
    Event,
    KeyConfigChanged,
    KeyStateUpdated,
)
from deckbridge.mqtt import MqttClient
from deckbridge.mqtt.state_subscriber import StateSubscriber
from deckbridge.storage import SqliteStorage, run_migrations
from deckbridge.storage.schema import Key, Page, Preferences, StateSubscription


def _build_storage() -> SqliteStorage:
    storage = SqliteStorage(":memory:")
    run_migrations(storage)
    return storage


def _build_mqtt() -> MqttClient:
    return MqttClient(EventBus(), lambda: Preferences())


def _collect(bus: EventBus) -> list[Event]:
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(Event, handler)
    return received


# ---- topic subscription bookkeeping --------------------------------------


async def test_broker_connected_subscribes_unique_topics() -> None:
    bus = EventBus()
    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    storage.upsert_key(Key(page_id="p1", slot=0, state=StateSubscription(topic="home/light/state")))
    storage.upsert_key(
        Key(page_id="p1", slot=1, state=StateSubscription(topic="home/light/state"))  # dup
    )
    storage.upsert_key(Key(page_id="p1", slot=2, state=StateSubscription(topic="home/lock/state")))
    mqtt = _build_mqtt()
    StateSubscriber(bus, storage, mqtt)

    await bus.publish(BrokerConnected(host="broker"))

    # Two unique topics registered with the MQTT client.
    assert "home/light/state" in mqtt._subscribers
    assert "home/lock/state" in mqtt._subscribers


async def test_key_config_changed_picks_up_new_topic() -> None:
    bus = EventBus()
    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    mqtt = _build_mqtt()
    sub = StateSubscriber(bus, storage, mqtt)
    await bus.publish(BrokerConnected(host="broker"))
    assert mqtt._subscribers == {}

    storage.upsert_key(Key(page_id="p1", slot=0, state=StateSubscription(topic="new/topic")))
    await bus.publish(KeyConfigChanged(page_id="p1", slot=0))

    assert "new/topic" in mqtt._subscribers
    del sub  # unused, silences linter


async def test_keys_with_no_state_subscription_dont_subscribe() -> None:
    bus = EventBus()
    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    storage.upsert_key(Key(page_id="p1", slot=0))  # no state
    mqtt = _build_mqtt()
    StateSubscriber(bus, storage, mqtt)

    await bus.publish(BrokerConnected(host="broker"))
    assert mqtt._subscribers == {}


# ---- inbound message extraction -----------------------------------------


async def test_plaintext_payload_emits_trimmed_value() -> None:
    bus = EventBus()
    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    storage.upsert_key(Key(page_id="p1", slot=0, state=StateSubscription(topic="home/x")))
    mqtt = _build_mqtt()
    sub = StateSubscriber(bus, storage, mqtt)
    received = _collect(bus)
    await bus.publish(BrokerConnected(host="broker"))

    await sub._on_message("home/x", b"  ON  ")

    state_events = [e for e in received if isinstance(e, KeyStateUpdated)]
    assert len(state_events) == 1
    assert state_events[0].value == "ON"
    assert state_events[0].page_id == "p1"
    assert state_events[0].slot == 0


async def test_json_payload_with_jmespath_extracts_field() -> None:
    bus = EventBus()
    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    storage.upsert_key(
        Key(
            page_id="p1",
            slot=0,
            state=StateSubscription(topic="home/x", jmespath="state.power"),
        )
    )
    mqtt = _build_mqtt()
    sub = StateSubscriber(bus, storage, mqtt)
    received = _collect(bus)
    await bus.publish(BrokerConnected(host="broker"))

    await sub._on_message("home/x", b'{"state":{"power":"on","brightness":120}}')

    state_events = [e for e in received if isinstance(e, KeyStateUpdated)]
    assert len(state_events) == 1
    assert state_events[0].value == "on"


async def test_jmespath_against_nonjson_falls_back_to_raw() -> None:
    bus = EventBus()
    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    storage.upsert_key(
        Key(
            page_id="p1",
            slot=0,
            state=StateSubscription(topic="home/x", jmespath="state.power"),
        )
    )
    mqtt = _build_mqtt()
    sub = StateSubscriber(bus, storage, mqtt)
    received = _collect(bus)
    await bus.publish(BrokerConnected(host="broker"))

    await sub._on_message("home/x", b"plain-text")

    state_events = [e for e in received if isinstance(e, KeyStateUpdated)]
    assert len(state_events) == 1
    assert state_events[0].value == "plain-text"


async def test_jmespath_no_match_emits_nothing() -> None:
    bus = EventBus()
    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    storage.upsert_key(
        Key(
            page_id="p1",
            slot=0,
            state=StateSubscription(topic="home/x", jmespath="state.power"),
        )
    )
    mqtt = _build_mqtt()
    sub = StateSubscriber(bus, storage, mqtt)
    received = _collect(bus)
    await bus.publish(BrokerConnected(host="broker"))

    await sub._on_message("home/x", b'{"state":{"other":"value"}}')

    state_events = [e for e in received if isinstance(e, KeyStateUpdated)]
    assert len(state_events) == 0


async def test_multiple_keys_sharing_topic_each_get_event() -> None:
    bus = EventBus()
    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    storage.upsert_key(Key(page_id="p1", slot=0, state=StateSubscription(topic="home/shared")))
    storage.upsert_key(Key(page_id="p1", slot=3, state=StateSubscription(topic="home/shared")))
    mqtt = _build_mqtt()
    sub = StateSubscriber(bus, storage, mqtt)
    received = _collect(bus)
    await bus.publish(BrokerConnected(host="broker"))

    await sub._on_message("home/shared", b"VALUE")

    state_events = [e for e in received if isinstance(e, KeyStateUpdated)]
    assert {(e.slot, e.value) for e in state_events} == {(0, "VALUE"), (3, "VALUE")}
