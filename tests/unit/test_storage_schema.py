"""Pydantic schema validation: discriminated union, slot range, required fields."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from deckbridge.storage.schema import (
    HTTPWebhookAction,
    Icon,
    IconSource,
    Key,
    MQTTPublishAction,
    NoOpAction,
    Page,
    PageSwitchAction,
    PressAction,
    StateSubscription,
)

# ---- PressAction discriminated union --------------------------------------


def test_press_action_round_trips_each_variant() -> None:
    adapter: TypeAdapter[PressAction] = TypeAdapter(PressAction)
    cases: list[PressAction] = [
        MQTTPublishAction(topic="home/light/set", payload="ON"),
        HTTPWebhookAction(url="http://example.com/hook", method="POST"),
        PageSwitchAction(target_page_id="home"),
        NoOpAction(),
    ]
    for case in cases:
        rebuilt = adapter.validate_json(adapter.dump_json(case))
        assert rebuilt == case
        # Type discriminator must round-trip.
        assert type(rebuilt) is type(case)


def test_press_action_dispatches_on_type_field() -> None:
    adapter: TypeAdapter[PressAction] = TypeAdapter(PressAction)
    raw = '{"type":"mqtt_publish","topic":"x","payload":""}'
    parsed = adapter.validate_json(raw)
    assert isinstance(parsed, MQTTPublishAction)
    assert parsed.topic == "x"


def test_press_action_rejects_unknown_type() -> None:
    adapter: TypeAdapter[PressAction] = TypeAdapter(PressAction)
    with pytest.raises(ValidationError):
        adapter.validate_json('{"type":"unknown","payload":"x"}')


def test_mqtt_publish_requires_topic() -> None:
    with pytest.raises(ValidationError):
        MQTTPublishAction(topic="")  # min_length=1


def test_http_webhook_method_validated() -> None:
    with pytest.raises(ValidationError):
        HTTPWebhookAction(url="http://x", method="PATCH")  # type: ignore[arg-type]


# ---- Key ----------------------------------------------------------------


def test_key_slot_in_range() -> None:
    Key(page_id="p", slot=0)
    Key(page_id="p", slot=14)
    Key(page_id="p", slot=31)


def test_key_slot_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        Key(page_id="p", slot=-1)
    with pytest.raises(ValidationError):
        Key(page_id="p", slot=32)


def test_key_default_press_is_no_op() -> None:
    key = Key(page_id="p", slot=0)
    assert isinstance(key.press, NoOpAction)


def test_key_round_trips_through_json() -> None:
    key = Key(
        page_id="page-1",
        slot=3,
        label="Lights",
        icon_id="lucide:lightbulb",
        press=MQTTPublishAction(topic="home/light/set", payload="TOGGLE", retain=False),
        state=StateSubscription(
            topic="home/light/state",
            jmespath="state",
            icon_map={"on": "lucide:lightbulb", "off": "lucide:lightbulb-off"},
            default_icon_id="lucide:question-mark",
        ),
    )
    rebuilt = Key.model_validate_json(key.model_dump_json())
    assert rebuilt == key
    assert isinstance(rebuilt.press, MQTTPublishAction)


def test_key_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Key.model_validate({"page_id": "p", "slot": 0, "garbage": "field"})


def test_key_padding_defaults_to_zero() -> None:
    """Backwards compat: a key persisted before the padding field existed
    deserializes with padding=0 (no behavior change for existing data)."""
    key = Key.model_validate({"page_id": "p", "slot": 0})
    assert key.padding == 0


def test_key_padding_in_range() -> None:
    Key(page_id="p", slot=0, padding=0)
    Key(page_id="p", slot=0, padding=20)


def test_key_padding_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        Key(page_id="p", slot=0, padding=-1)
    with pytest.raises(ValidationError):
        Key(page_id="p", slot=0, padding=21)


# ---- v1.1 presentation knobs ----------------------------------------------


def test_key_presentation_defaults_match_v1_0() -> None:
    """Backwards compat: a key persisted before the v1.1 fields existed
    deserializes with v1.0-equivalent defaults — show flags True, black bg,
    white label, no bg image, no icon tint."""
    key = Key.model_validate({"page_id": "p", "slot": 0})
    assert key.show_icon is True
    assert key.show_label is True
    assert key.bg_color == "#000000"
    assert key.bg_image_id is None
    assert key.label_color == "#FFFFFF"
    assert key.icon_color is None


def test_key_color_fields_accept_six_digit_hex() -> None:
    Key(page_id="p", slot=0, bg_color="#1a2b3c", label_color="#FFFFFF", icon_color="#abcdef")


def test_key_color_fields_reject_invalid_hex() -> None:
    for bad in ("000000", "#FFF", "#GGGGGG", "rgb(0,0,0)", "#1234567"):
        with pytest.raises(ValidationError):
            Key(page_id="p", slot=0, bg_color=bad)
        with pytest.raises(ValidationError):
            Key(page_id="p", slot=0, label_color=bad)
        with pytest.raises(ValidationError):
            Key(page_id="p", slot=0, icon_color=bad)


def test_key_icon_color_allows_null() -> None:
    """`null` is the documented sentinel for "no tint" — must validate."""
    Key(page_id="p", slot=0, icon_color=None)


def test_key_show_flags_round_trip_through_json() -> None:
    key = Key(
        page_id="p",
        slot=0,
        show_icon=False,
        show_label=False,
        bg_color="#123456",
        label_color="#abcdef",
        icon_color="#ff00ff",
        bg_image_id="img-42",
    )
    rebuilt = Key.model_validate_json(key.model_dump_json())
    assert rebuilt == key


def test_key_font_size_defaults_to_14() -> None:
    """Backwards compat: keys persisted before font_size existed deserialize
    at 14, which is the literal value v1.0.x always used."""
    key = Key.model_validate({"page_id": "p", "slot": 0})
    assert key.font_size == 14


def test_key_font_size_in_range() -> None:
    Key(page_id="p", slot=0, font_size=8)
    Key(page_id="p", slot=0, font_size=32)


def test_key_font_size_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        Key(page_id="p", slot=0, font_size=7)
    with pytest.raises(ValidationError):
        Key(page_id="p", slot=0, font_size=33)


# ---- Page ----------------------------------------------------------------


def test_page_required_fields() -> None:
    page = Page(id="p1", deck_serial="ABC")
    assert page.name == ""
    assert page.order == 0


def test_page_id_must_be_nonempty() -> None:
    with pytest.raises(ValidationError):
        Page(id="", deck_serial="ABC")


# ---- Icon ----------------------------------------------------------------


def test_icon_bundled_and_uploaded_round_trip() -> None:
    bundled = Icon(id="lucide:home", source=IconSource.BUNDLED, reference="home")
    uploaded = Icon(
        id="upl-abc",
        name="My Logo",
        source=IconSource.UPLOADED,
        reference="icons/uploaded/abc.png",
        sha256="0" * 64,
    )
    assert Icon.model_validate_json(bundled.model_dump_json()) == bundled
    assert Icon.model_validate_json(uploaded.model_dump_json()) == uploaded


def test_icon_invalid_source_rejected() -> None:
    with pytest.raises(ValidationError):
        Icon(id="x", source="badsource", reference="ref")  # type: ignore[arg-type]


# ---- StateSubscription -------------------------------------------------


def test_state_subscription_minimal() -> None:
    sub = StateSubscription(topic="home/x")
    assert sub.icon_map == {}
    assert sub.jmespath is None
    assert sub.default_icon_id is None
