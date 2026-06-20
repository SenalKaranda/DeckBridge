"""PressDispatcher — KeyPressed routing + DeckConnected initial page selection.

These tests don't touch a real broker or the network — the MqttClient runs
with no broker host (publishes go to its in-memory queue) and httpx requests
go through ``httpx.MockTransport`` so we can assert on what was sent.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx

from deckbridge.actions import ActivePages, PressDispatcher
from deckbridge.events import (
    ActivePageChanged,
    DeckConnected,
    EventBus,
    KeyPressed,
)
from deckbridge.events.types import Event, PageConfigChanged
from deckbridge.mqtt import MqttClient
from deckbridge.storage import SqliteStorage, run_migrations
from deckbridge.storage.schema import (
    Deck,
    HTTPWebhookAction,
    Key,
    MQTTPublishAction,
    NoOpAction,
    Page,
    PageSwitchAction,
    Preferences,
)

# ---- helpers ------------------------------------------------------------


def _build_storage() -> SqliteStorage:
    storage = SqliteStorage(":memory:")
    run_migrations(storage)
    return storage


def _build_mqtt() -> MqttClient:
    """A MqttClient that never connects (no host configured)."""
    return MqttClient(EventBus(), lambda: Preferences())


def _build_http(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


def _collect(bus: EventBus, event_type: type[Event] = Event) -> list[Event]:
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    bus.subscribe(event_type, handler)
    return received


class _FakeDeckManager:
    """Minimal stand-in for DeckManager — only exposes the .decks mapping that
    the dispatcher reads. Avoids pulling pyudev/HID into unit tests."""

    def __init__(self, serials: list[str]) -> None:
        # The real manager's value is a Deck instance; the dispatcher only
        # uses .keys() so a sentinel object is enough.
        self.decks = {s: object() for s in serials}


def _make_dispatcher(
    storage: SqliteStorage | None = None,
    mqtt_client: MqttClient | None = None,
    http_client: httpx.AsyncClient | None = None,
    deck_manager: _FakeDeckManager | None = None,
) -> tuple[PressDispatcher, EventBus, ActivePages, SqliteStorage, MqttClient]:
    bus = EventBus()
    storage = storage or _build_storage()
    mqtt_client = mqtt_client or _build_mqtt()
    http_client = http_client or _build_http(lambda req: httpx.Response(204))
    active_pages = ActivePages()
    dispatcher = PressDispatcher(
        bus,
        storage,
        mqtt_client,
        active_pages,
        http_client,
        deck_manager=deck_manager,
    )
    return dispatcher, bus, active_pages, storage, mqtt_client


# ---- DeckConnected initial page selection -------------------------------


async def test_deck_connected_with_no_pages_leaves_active_unset() -> None:
    _, bus, active_pages, _, _ = _make_dispatcher()
    await bus.publish(DeckConnected(serial="ABC", model="MK2"))
    assert active_pages.get("ABC") is None


async def test_deck_connected_picks_first_page_by_order() -> None:
    storage = _build_storage()
    storage.upsert_page(Page(id="p2", deck_serial="ABC", order=1))
    storage.upsert_page(Page(id="p1", deck_serial="ABC", order=0))
    _, bus, active_pages, _, _ = _make_dispatcher(storage=storage)

    received = _collect(bus, ActivePageChanged)
    await bus.publish(DeckConnected(serial="ABC", model="MK2"))
    await asyncio.sleep(0)  # let event handlers run

    assert active_pages.get("ABC") == "p1"
    assert any(isinstance(e, ActivePageChanged) and e.page_id == "p1" for e in received)


async def test_deck_connected_prefers_home_page_id() -> None:
    storage = _build_storage()
    storage.upsert_deck(Deck(serial="ABC", home_page_id="home"))
    storage.upsert_page(Page(id="other", deck_serial="ABC", order=0))
    storage.upsert_page(Page(id="home", deck_serial="ABC", order=1))
    _, bus, active_pages, _, _ = _make_dispatcher(storage=storage)

    await bus.publish(DeckConnected(serial="ABC", model="MK2"))
    assert active_pages.get("ABC") == "home"


async def test_deck_connected_falls_back_to_default_pages() -> None:
    """When the deck has no pages of its own, fall back to pages bound to the
    'default' serial (editor-without-deck flow)."""
    storage = _build_storage()
    storage.upsert_page(Page(id="dp", deck_serial="default", order=0))
    _, bus, active_pages, _, _ = _make_dispatcher(storage=storage)

    await bus.publish(DeckConnected(serial="REAL-DECK", model="MK2"))
    assert active_pages.get("REAL-DECK") == "dp"


async def test_deck_connected_does_not_reinit_existing() -> None:
    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    _, bus, active_pages, _, _ = _make_dispatcher(storage=storage)
    active_pages.set("ABC", "manually-set")

    await bus.publish(DeckConnected(serial="ABC", model="MK2"))
    assert active_pages.get("ABC") == "manually-set"


# ---- KeyPressed routing -------------------------------------------------


async def test_press_with_no_active_page_is_ignored() -> None:
    _, bus, _, storage, mqtt = _make_dispatcher()
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    storage.upsert_key(Key(page_id="p1", slot=0, press=MQTTPublishAction(topic="x", payload="y")))
    await bus.publish(KeyPressed(serial="ABC", key=0))
    # Nothing should have been queued on the MQTT client.
    assert mqtt._publish_queue.qsize() == 0


async def test_press_on_empty_slot_is_ignored() -> None:
    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    _, bus, active_pages, _, mqtt = _make_dispatcher(storage=storage)
    active_pages.set("ABC", "p1")

    await bus.publish(KeyPressed(serial="ABC", key=5))  # no key configured
    assert mqtt._publish_queue.qsize() == 0


async def test_press_mqtt_publish_action_queues_message() -> None:
    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    storage.upsert_key(
        Key(
            page_id="p1",
            slot=0,
            press=MQTTPublishAction(topic="home/x/set", payload="ON", retain=True, qos=1),
        )
    )
    _, bus, active_pages, _, mqtt = _make_dispatcher(storage=storage)
    active_pages.set("ABC", "p1")

    await bus.publish(KeyPressed(serial="ABC", key=0))
    topic, payload, retain, qos = mqtt._publish_queue.get_nowait()
    assert topic == "home/x/set"
    assert payload == b"ON"
    assert retain is True
    assert qos == 1


async def test_press_http_webhook_action_fires_request() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(202)

    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    storage.upsert_key(
        Key(
            page_id="p1",
            slot=0,
            press=HTTPWebhookAction(
                url="http://example/test",
                method="POST",
                headers={"X-Custom": "yes"},
                body='{"hello":"world"}',
            ),
        )
    )
    http = _build_http(handler)
    _, bus, active_pages, _, _ = _make_dispatcher(storage=storage, http_client=http)
    active_pages.set("ABC", "p1")

    await bus.publish(KeyPressed(serial="ABC", key=0))
    assert len(captured) == 1
    assert str(captured[0].url) == "http://example/test"
    assert captured[0].method == "POST"
    assert captured[0].headers.get("x-custom") == "yes"
    assert captured[0].content == b'{"hello":"world"}'


async def test_press_http_webhook_failure_does_not_raise() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    storage.upsert_key(
        Key(
            page_id="p1",
            slot=0,
            press=HTTPWebhookAction(url="http://example/test", method="GET"),
        )
    )
    http = _build_http(handler)
    _, bus, active_pages, _, _ = _make_dispatcher(storage=storage, http_client=http)
    active_pages.set("ABC", "p1")

    # Must not propagate the connection error.
    await bus.publish(KeyPressed(serial="ABC", key=0))


async def test_press_page_switch_updates_active_and_emits_event() -> None:
    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="ABC", order=0))
    storage.upsert_page(Page(id="p2", deck_serial="ABC", order=1))
    storage.upsert_key(Key(page_id="p1", slot=0, press=PageSwitchAction(target_page_id="p2")))
    _, bus, active_pages, _, _ = _make_dispatcher(storage=storage)
    active_pages.set("ABC", "p1")

    received = _collect(bus, ActivePageChanged)
    await bus.publish(KeyPressed(serial="ABC", key=0))

    assert active_pages.get("ABC") == "p2"
    assert any(isinstance(e, ActivePageChanged) and e.page_id == "p2" for e in received)


async def test_press_page_switch_to_missing_page_is_warning_only() -> None:
    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    storage.upsert_key(Key(page_id="p1", slot=0, press=PageSwitchAction(target_page_id="nope")))
    _, bus, active_pages, _, _ = _make_dispatcher(storage=storage)
    active_pages.set("ABC", "p1")

    await bus.publish(KeyPressed(serial="ABC", key=0))
    # Active page unchanged.
    assert active_pages.get("ABC") == "p1"


async def test_press_no_op_action_does_nothing() -> None:
    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    storage.upsert_key(Key(page_id="p1", slot=0, press=NoOpAction()))
    _, bus, active_pages, _, mqtt = _make_dispatcher(storage=storage)
    active_pages.set("ABC", "p1")

    await bus.publish(KeyPressed(serial="ABC", key=0))
    assert mqtt._publish_queue.qsize() == 0


# ---- public execute() entry point ---------------------------------------


async def test_execute_called_directly_without_active_page() -> None:
    """The test-press endpoint (M6d) calls dispatcher.execute() bypassing
    KeyPressed. Make sure that path works without ActivePages state."""
    dispatcher, _, _, storage, mqtt = _make_dispatcher()
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))

    await dispatcher.execute(
        "ABC",
        MQTTPublishAction(topic="home/test", payload="hello"),
    )
    topic, payload, _, _ = mqtt._publish_queue.get_nowait()
    assert topic == "home/test"
    assert payload == b"hello"


# ---- PageConfigChanged auto-activation ----------------------------------
#
# Regression test for the v1.0.0 bug where pages created from the editor
# AFTER the deck attached never displayed. Sequence: deck attaches (no
# pages yet -> active_pages stays empty) -> user creates a page via the
# API -> PageConfigChanged fires -> dispatcher must activate the page.


async def test_page_config_changed_activates_attached_deck_with_no_active_page() -> None:
    """User creates the first page after the deck attached: the dispatcher
    picks it up and emits ActivePageChanged so the painter renders."""
    deck_manager = _FakeDeckManager(["REAL-DECK"])
    storage = _build_storage()
    _, bus, active_pages, _, _ = _make_dispatcher(storage=storage, deck_manager=deck_manager)

    # Simulate the attach happening first (no pages yet).
    await bus.publish(DeckConnected(serial="REAL-DECK", model="MK2"))
    assert active_pages.get("REAL-DECK") is None

    # Now the user creates a page. The route would persist + publish:
    storage.upsert_page(Page(id="p1", deck_serial="REAL-DECK", order=0))
    received = _collect(bus, ActivePageChanged)
    await bus.publish(PageConfigChanged(page_id="p1", deck_serial="REAL-DECK"))
    await asyncio.sleep(0)

    assert active_pages.get("REAL-DECK") == "p1"
    assert any(
        isinstance(e, ActivePageChanged) and e.serial == "REAL-DECK" and e.page_id == "p1"
        for e in received
    )


async def test_page_config_changed_is_idempotent_when_active_page_already_set() -> None:
    """Don't reset an existing active page (e.g. user edits an UNRELATED page)."""
    deck_manager = _FakeDeckManager(["REAL-DECK"])
    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="REAL-DECK", order=0))
    storage.upsert_page(Page(id="p2", deck_serial="REAL-DECK", order=1))
    _, bus, active_pages, _, _ = _make_dispatcher(storage=storage, deck_manager=deck_manager)

    await bus.publish(DeckConnected(serial="REAL-DECK", model="MK2"))
    assert active_pages.get("REAL-DECK") == "p1"

    # User patches p2 (rename). Should NOT bump the active page back to p1's slot.
    received = _collect(bus, ActivePageChanged)
    await bus.publish(PageConfigChanged(page_id="p2", deck_serial="REAL-DECK"))
    await asyncio.sleep(0)

    assert active_pages.get("REAL-DECK") == "p1"
    # No new ActivePageChanged fired (the deck already had one).
    assert received == []


async def test_page_config_changed_falls_back_to_event_serial_without_deck_manager() -> None:
    """When the dispatcher has no DeckManager wired (older test setups),
    the event's deck_serial is used as a best-effort hint so the activation
    still happens for that specific deck."""
    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="HEADLESS", order=0))
    _, bus, active_pages, _, _ = _make_dispatcher(storage=storage, deck_manager=None)

    await bus.publish(PageConfigChanged(page_id="p1", deck_serial="HEADLESS"))
    await asyncio.sleep(0)

    assert active_pages.get("HEADLESS") == "p1"


async def test_page_config_changed_after_delete_picks_a_new_active_page() -> None:
    """Deleting the active page should activate the next available page on
    the same deck (the route clears active_pages first; the dispatcher's
    PageConfigChanged handler then re-picks)."""
    deck_manager = _FakeDeckManager(["REAL-DECK"])
    storage = _build_storage()
    storage.upsert_page(Page(id="p1", deck_serial="REAL-DECK", order=0))
    storage.upsert_page(Page(id="p2", deck_serial="REAL-DECK", order=1))
    _, bus, active_pages, _, _ = _make_dispatcher(storage=storage, deck_manager=deck_manager)

    await bus.publish(DeckConnected(serial="REAL-DECK", model="MK2"))
    assert active_pages.get("REAL-DECK") == "p1"

    # Simulate the route's delete cascade: storage drop + active_pages clear.
    storage.delete_page("p1")
    active_pages.clear("REAL-DECK")
    await bus.publish(PageConfigChanged(page_id="p1", deck_serial="REAL-DECK"))
    await asyncio.sleep(0)

    assert active_pages.get("REAL-DECK") == "p2"
