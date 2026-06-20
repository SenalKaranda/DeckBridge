"""MqttClient — public API + no-broker-configured lifecycle.

Full session-level testing (publish/receive round-trip, reconnect-on-disconnect)
needs a live broker and is exercised by integration tests in CI. These unit
tests verify the policy bits that don't require a network: subscriber
bookkeeping, publish queueing, lifecycle when no broker is configured, and
the ``configured``/``connected`` properties.

mypy doesn't complain about reading "private" `_subscribers`/`_publish_queue`
attributes from instance scope, so we just access them directly without
type-ignore noise.
"""

from __future__ import annotations

import asyncio

from deckbridge.events import EventBus
from deckbridge.mqtt import MqttClient
from deckbridge.storage.schema import Preferences


def _no_broker_prefs() -> Preferences:
    return Preferences()  # mqtt_host=None


def _broker_prefs(host: str = "broker.lan", port: int = 1883) -> Preferences:
    return Preferences(mqtt_host=host, mqtt_port=port)


# ---- public API (synchronous) -------------------------------------------


def test_initially_disconnected() -> None:
    client = MqttClient(EventBus(), _no_broker_prefs)
    assert client.connected is False
    assert client.configured is False


def test_configured_reflects_prefs_host() -> None:
    client = MqttClient(EventBus(), _broker_prefs)
    assert client.configured is True


def test_subscribe_tracks_handler() -> None:
    client = MqttClient(EventBus(), _no_broker_prefs)

    async def handler(topic: str, payload: bytes) -> None:
        del topic, payload

    client.subscribe("home/x", handler)
    assert "home/x" in client._subscribers
    assert handler in client._subscribers["home/x"]


def test_subscribe_supports_multiple_handlers_per_topic() -> None:
    client = MqttClient(EventBus(), _no_broker_prefs)

    async def h1(topic: str, payload: bytes) -> None:
        del topic, payload

    async def h2(topic: str, payload: bytes) -> None:
        del topic, payload

    client.subscribe("home/x", h1)
    client.subscribe("home/x", h2)
    assert client._subscribers["home/x"] == [h1, h2]


def test_unsubscribe_removes_handler() -> None:
    client = MqttClient(EventBus(), _no_broker_prefs)

    async def handler(topic: str, payload: bytes) -> None:
        del topic, payload

    client.subscribe("home/x", handler)
    client.unsubscribe("home/x", handler)
    assert "home/x" not in client._subscribers


def test_unsubscribe_unknown_handler_is_noop() -> None:
    client = MqttClient(EventBus(), _no_broker_prefs)

    async def handler(topic: str, payload: bytes) -> None:
        del topic, payload

    client.unsubscribe("home/x", handler)  # must not raise


# ---- async behavior -----------------------------------------------------


async def test_publish_enqueues_message() -> None:
    client = MqttClient(EventBus(), _no_broker_prefs)
    await client.publish("home/x", "ON", retain=True, qos=1)
    assert client._publish_queue.qsize() == 1
    topic, payload, retain, qos = client._publish_queue.get_nowait()
    assert topic == "home/x"
    assert payload == b"ON"
    assert retain is True
    assert qos == 1


async def test_publish_accepts_bytes_directly() -> None:
    client = MqttClient(EventBus(), _no_broker_prefs)
    await client.publish("home/x", b"\x00\x01\x02")
    _, payload, _, _ = client._publish_queue.get_nowait()
    assert payload == b"\x00\x01\x02"


async def test_lifecycle_with_no_broker_starts_and_stops_cleanly() -> None:
    """When no broker is configured the loop waits for reload/stop without
    attempting a network connection. Stopping must be quick and clean."""
    client = MqttClient(EventBus(), _no_broker_prefs)
    client.start()
    # Give the run loop one tick to reach the wait state.
    await asyncio.sleep(0.05)
    assert client.connected is False

    await asyncio.wait_for(client.stop(), timeout=2.0)
    assert client._task is None


async def test_double_start_is_idempotent() -> None:
    client = MqttClient(EventBus(), _no_broker_prefs)
    client.start()
    first_task = client._task
    client.start()  # second call should be a no-op
    assert client._task is first_task
    await client.stop()


async def test_stop_without_start_is_noop() -> None:
    client = MqttClient(EventBus(), _no_broker_prefs)
    await client.stop()  # must not raise


async def test_reload_when_running_does_not_crash() -> None:
    """Reload should be safe to call any time; it only sets a flag."""
    client = MqttClient(EventBus(), _no_broker_prefs)
    client.start()
    await asyncio.sleep(0.05)
    client.reload()
    await asyncio.sleep(0.05)  # let the loop wake and re-evaluate
    await asyncio.wait_for(client.stop(), timeout=2.0)


async def test_pending_publishes_survive_until_stop() -> None:
    """Messages queued before any connection happens stay in the queue."""
    client = MqttClient(EventBus(), _no_broker_prefs)
    await client.publish("home/a", "1")
    await client.publish("home/b", "2")
    client.start()
    await asyncio.sleep(0.05)
    # No broker -> nothing dequeued. Both messages should still be there.
    assert client._publish_queue.qsize() == 2
    await client.stop()


# ---- aiomqtt import sanity ----------------------------------------------


def test_aiomqtt_is_importable() -> None:
    """Smoke check that aiomqtt landed in the venv."""
    import aiomqtt

    assert hasattr(aiomqtt, "Client")
