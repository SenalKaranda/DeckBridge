"""POST /api/pages/{id}/keys/{slot}/test-press — fire actions without a press.

Wires the editor's "Test" button to the press dispatcher. Tests inject a
storage with known keys + page and assert the right action fires.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from deckbridge.storage import Storage
from deckbridge.storage.schema import (
    HTTPWebhookAction,
    Key,
    MQTTPublishAction,
    NoOpAction,
    Page,
    PageSwitchAction,
)


def test_test_press_404_on_missing_page(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, _ = authed_client
    r = client.post("/api/pages/nope/keys/0/test-press")
    assert r.status_code == 404


def test_test_press_404_on_missing_key(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, storage = authed_client
    storage.upsert_page(Page(id="p1", deck_serial="default"))
    r = client.post("/api/pages/p1/keys/0/test-press")
    assert r.status_code == 404


def test_test_press_no_op_returns_ok(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, storage = authed_client
    storage.upsert_page(Page(id="p1", deck_serial="default"))
    storage.upsert_key(Key(page_id="p1", slot=0, press=NoOpAction()))

    r = client.post("/api/pages/p1/keys/0/test-press")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["action_type"] == "no_op"
    assert body["deck_serial"] == "default"


def test_test_press_mqtt_publish_queues_message(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, storage = authed_client
    storage.upsert_page(Page(id="p1", deck_serial="default"))
    storage.upsert_key(
        Key(
            page_id="p1",
            slot=0,
            press=MQTTPublishAction(topic="home/test", payload="HI"),
        )
    )

    r = client.post("/api/pages/p1/keys/0/test-press")
    assert r.status_code == 200, r.text
    assert r.json()["action_type"] == "mqtt_publish"

    mqtt = client.app.state.mqtt_client  # type: ignore[attr-defined]
    topic, payload, _, _ = mqtt._publish_queue.get_nowait()
    assert topic == "home/test"
    assert payload == b"HI"


def test_test_press_with_explicit_deck_serial_query_param(
    authed_client: tuple[TestClient, Storage],
) -> None:
    client, storage = authed_client
    storage.upsert_page(Page(id="p1", deck_serial="default"))
    storage.upsert_key(Key(page_id="p1", slot=0, press=NoOpAction()))

    r = client.post("/api/pages/p1/keys/0/test-press", params={"deck_serial": "EXPLICIT-ABC"})
    assert r.status_code == 200
    assert r.json()["deck_serial"] == "EXPLICIT-ABC"


def test_test_press_page_switch_does_not_blow_up_on_missing_target(
    authed_client: tuple[TestClient, Storage],
) -> None:
    """Page-switch to a missing page is a logged warning in the dispatcher;
    the endpoint still responds 200."""
    client, storage = authed_client
    storage.upsert_page(Page(id="p1", deck_serial="default"))
    storage.upsert_key(Key(page_id="p1", slot=0, press=PageSwitchAction(target_page_id="nope")))
    r = client.post("/api/pages/p1/keys/0/test-press")
    assert r.status_code == 200


def test_test_press_http_webhook(authed_client: tuple[TestClient, Storage]) -> None:
    """The TestClient's app uses a real httpx.AsyncClient; this test points
    the webhook at /api/healthz on the same app, which always returns 200."""
    client, storage = authed_client
    storage.upsert_page(Page(id="p1", deck_serial="default"))
    storage.upsert_key(
        Key(
            page_id="p1",
            slot=0,
            press=HTTPWebhookAction(
                url="http://127.0.0.1:1/",
                method="POST",  # connection-refused
            ),
        )
    )
    # Even with a connection failure, the dispatcher catches and logs it
    # rather than propagating; the endpoint should still return 200.
    r = client.post("/api/pages/p1/keys/0/test-press")
    assert r.status_code == 200


def test_test_press_requires_auth(unauth_client: tuple[TestClient, Storage]) -> None:
    client, _ = unauth_client
    r = client.post("/api/pages/p1/keys/0/test-press")
    assert r.status_code == 401
