"""Storage backend parity test suite.

Every test in this module runs twice — once against
:class:`~deckbridge.storage.SqliteStorage` (in-memory) and once against
:class:`~deckbridge.storage.FileStorage` (under ``tmp_path``). Both backends
must produce identical observable behavior for every operation; if a test
fails for one backend but passes the other, that's a parity bug to fix in
the failing backend, not a difference to paper over.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from deckbridge.storage import (
    CURRENT_SCHEMA_VERSION,
    Deck,
    FileStorage,
    Icon,
    IconSource,
    Key,
    MQTTPublishAction,
    Page,
    PageSwitchAction,
    Preferences,
    Snapshot,
    SqliteStorage,
    StateSubscription,
    Storage,
    open_storage,
    run_migrations,
)


@pytest.fixture(params=["sqlite", "files"], ids=["sqlite", "files"])
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Storage]:
    """Yields each backend in turn so tests run twice."""
    backend = request.param
    store: Storage
    if backend == "sqlite":
        store = SqliteStorage(":memory:")
    else:
        store = FileStorage(tmp_path / "data.json")
    run_migrations(store)
    try:
        yield store
    finally:
        store.close()


# ---- decks ---------------------------------------------------------------


def test_empty_storage_has_no_entities(storage: Storage) -> None:
    assert storage.list_decks() == []
    assert storage.list_pages() == []
    assert storage.list_icons() == []


def test_upsert_and_get_deck(storage: Storage) -> None:
    deck = Deck(serial="ABC-123", model="StreamDeckMK2")
    storage.upsert_deck(deck)
    assert storage.get_deck("ABC-123") == deck
    assert storage.get_deck("missing") is None


def test_upsert_deck_overwrites(storage: Storage) -> None:
    storage.upsert_deck(Deck(serial="ABC", model="OldModel"))
    storage.upsert_deck(Deck(serial="ABC", model="NewModel"))
    assert storage.get_deck("ABC").model == "NewModel"  # type: ignore[union-attr]
    assert len(storage.list_decks()) == 1


def test_list_decks_sorted_by_serial(storage: Storage) -> None:
    for s in ["C", "A", "B"]:
        storage.upsert_deck(Deck(serial=s))
    assert [d.serial for d in storage.list_decks()] == ["A", "B", "C"]


# ---- pages ---------------------------------------------------------------


def test_upsert_and_get_page(storage: Storage) -> None:
    page = Page(id="p1", deck_serial="ABC", name="Home", order=0)
    storage.upsert_page(page)
    assert storage.get_page("p1") == page


def test_list_pages_filtered_by_deck(storage: Storage) -> None:
    storage.upsert_page(Page(id="p1", deck_serial="A", order=0))
    storage.upsert_page(Page(id="p2", deck_serial="A", order=1))
    storage.upsert_page(Page(id="p3", deck_serial="B", order=0))
    a_pages = storage.list_pages(deck_serial="A")
    assert [p.id for p in a_pages] == ["p1", "p2"]
    assert {p.id for p in storage.list_pages()} == {"p1", "p2", "p3"}


def test_list_pages_sorted_by_order_then_id(storage: Storage) -> None:
    storage.upsert_page(Page(id="z", deck_serial="A", order=2))
    storage.upsert_page(Page(id="a", deck_serial="A", order=1))
    storage.upsert_page(Page(id="m", deck_serial="A", order=1))
    pages = storage.list_pages(deck_serial="A")
    assert [p.id for p in pages] == ["a", "m", "z"]


def test_delete_page_cascades_to_keys(storage: Storage) -> None:
    storage.upsert_page(Page(id="p1", deck_serial="A"))
    storage.upsert_page(Page(id="p2", deck_serial="A"))
    storage.upsert_key(Key(page_id="p1", slot=0))
    storage.upsert_key(Key(page_id="p1", slot=1))
    storage.upsert_key(Key(page_id="p2", slot=0))

    storage.delete_page("p1")

    assert storage.get_page("p1") is None
    assert storage.list_keys("p1") == []
    # p2's keys are untouched.
    assert len(storage.list_keys("p2")) == 1


# ---- keys ----------------------------------------------------------------


def test_upsert_key_round_trips_full_payload(storage: Storage) -> None:
    storage.upsert_page(Page(id="p1", deck_serial="A"))
    key = Key(
        page_id="p1",
        slot=5,
        label="Kitchen",
        icon_id="lucide:lamp",
        press=MQTTPublishAction(topic="home/kitchen/light/set", payload="TOGGLE"),
        state=StateSubscription(
            topic="home/kitchen/light/state",
            jmespath="power",
            icon_map={"on": "lucide:lamp", "off": "lucide:lamp-off"},
        ),
    )
    storage.upsert_key(key)
    fetched = storage.get_key("p1", 5)
    assert fetched == key
    assert isinstance(fetched.press, MQTTPublishAction)


def test_upsert_key_overwrites_same_slot(storage: Storage) -> None:
    storage.upsert_page(Page(id="p1", deck_serial="A"))
    storage.upsert_key(Key(page_id="p1", slot=0, label="A"))
    storage.upsert_key(Key(page_id="p1", slot=0, label="B"))
    assert storage.get_key("p1", 0).label == "B"  # type: ignore[union-attr]
    assert len(storage.list_keys("p1")) == 1


def test_list_keys_sorted_by_slot(storage: Storage) -> None:
    storage.upsert_page(Page(id="p1", deck_serial="A"))
    for s in [3, 0, 7, 1]:
        storage.upsert_key(Key(page_id="p1", slot=s))
    assert [k.slot for k in storage.list_keys("p1")] == [0, 1, 3, 7]


def test_delete_key(storage: Storage) -> None:
    storage.upsert_page(Page(id="p1", deck_serial="A"))
    storage.upsert_key(Key(page_id="p1", slot=0))
    storage.upsert_key(Key(page_id="p1", slot=1))
    storage.delete_key("p1", 0)
    assert storage.get_key("p1", 0) is None
    assert storage.get_key("p1", 1) is not None


def test_get_missing_key(storage: Storage) -> None:
    assert storage.get_key("nonexistent", 0) is None


# ---- icons ---------------------------------------------------------------


def test_upsert_and_get_icon(storage: Storage) -> None:
    icon = Icon(
        id="lucide:wifi",
        name="Wifi",
        source=IconSource.BUNDLED,
        reference="wifi",
    )
    storage.upsert_icon(icon)
    assert storage.get_icon("lucide:wifi") == icon


def test_list_icons_sorted_by_name(storage: Storage) -> None:
    storage.upsert_icon(Icon(id="z", name="Zebra", source=IconSource.BUNDLED, reference="z"))
    storage.upsert_icon(Icon(id="a", name="Apple", source=IconSource.BUNDLED, reference="a"))
    storage.upsert_icon(Icon(id="m", name="Mango", source=IconSource.BUNDLED, reference="m"))
    icons = storage.list_icons()
    assert [i.id for i in icons] == ["a", "m", "z"]


def test_delete_icon(storage: Storage) -> None:
    storage.upsert_icon(Icon(id="x", source=IconSource.BUNDLED, reference="x"))
    storage.delete_icon("x")
    assert storage.get_icon("x") is None


# ---- snapshot / migrations ----------------------------------------------


def test_export_and_import_snapshot_round_trips(storage: Storage) -> None:
    storage.upsert_deck(Deck(serial="ABC", model="MK2"))
    storage.upsert_page(Page(id="p1", deck_serial="ABC", name="Home"))
    storage.upsert_key(
        Key(
            page_id="p1",
            slot=0,
            press=PageSwitchAction(target_page_id="p2"),
        )
    )
    storage.upsert_icon(Icon(id="i1", source=IconSource.BUNDLED, reference="home"))

    snap = storage.export_snapshot()
    assert snap.schema_version == CURRENT_SCHEMA_VERSION
    assert {d.serial for d in snap.decks} == {"ABC"}
    assert {p.id for p in snap.pages} == {"p1"}
    assert len(snap.keys) == 1
    assert {i.id for i in snap.icons} == {"i1"}

    # Import the same snapshot — should be a no-op (same data).
    storage.import_snapshot(snap)
    assert storage.get_deck("ABC") is not None
    assert storage.get_key("p1", 0) is not None


def test_import_snapshot_replaces_existing_data(storage: Storage) -> None:
    storage.upsert_deck(Deck(serial="OLD"))
    storage.upsert_page(Page(id="oldp", deck_serial="OLD"))

    new = Snapshot(
        decks=[Deck(serial="NEW")],
        pages=[Page(id="newp", deck_serial="NEW")],
    )
    storage.import_snapshot(new)

    assert storage.get_deck("OLD") is None
    assert storage.get_deck("NEW") is not None
    assert storage.get_page("oldp") is None
    assert storage.get_page("newp") is not None


def test_run_migrations_stamps_fresh_store(storage: Storage) -> None:
    # Fixture already calls run_migrations; verify the version landed.
    assert storage.schema_version() == CURRENT_SCHEMA_VERSION


# ---- factory + persistence across reopens (file backend specific) -------


def test_open_storage_roundtrips_through_disk(tmp_path: Path) -> None:
    """A real on-disk file store should persist data across reopens."""
    store1 = open_storage("files", tmp_path)
    store1.upsert_deck(Deck(serial="PERSIST", model="MK2"))
    store1.close()

    store2 = open_storage("files", tmp_path)
    try:
        deck = store2.get_deck("PERSIST")
        assert deck is not None
        assert deck.model == "MK2"
        assert store2.schema_version() == CURRENT_SCHEMA_VERSION
    finally:
        store2.close()


def test_open_storage_rejects_unknown_backend(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown storage backend"):
        open_storage("mongodb", tmp_path)


# ---- preferences ---------------------------------------------------------


def test_default_preferences(storage: Storage) -> None:
    prefs = storage.get_preferences()
    assert prefs.password_hash is None
    assert prefs.api_token_hash is None
    assert prefs.mqtt_host is None
    assert prefs.mqtt_port == 1883
    assert prefs.ha_discovery_enabled is True


def test_set_and_get_preferences(storage: Storage) -> None:
    new_prefs = Preferences(
        password_hash="$argon2id$test-hash",
        mqtt_host="broker.lan",
        mqtt_port=8883,
        mqtt_username="hass",
        mqtt_tls=True,
        ha_discovery_enabled=False,
    )
    storage.set_preferences(new_prefs)
    fetched = storage.get_preferences()
    assert fetched == new_prefs


def test_set_preferences_overwrites(storage: Storage) -> None:
    storage.set_preferences(Preferences(mqtt_host="first"))
    storage.set_preferences(Preferences(mqtt_host="second"))
    assert storage.get_preferences().mqtt_host == "second"


def test_preferences_in_snapshot(storage: Storage) -> None:
    storage.set_preferences(Preferences(password_hash="$argon2id$x", mqtt_host="broker"))
    snap = storage.export_snapshot()
    assert snap.preferences.password_hash == "$argon2id$x"
    assert snap.preferences.mqtt_host == "broker"


def test_import_snapshot_restores_preferences(storage: Storage) -> None:
    snap = Snapshot(preferences=Preferences(password_hash="hash", mqtt_host="h", mqtt_port=8883))
    storage.import_snapshot(snap)
    prefs = storage.get_preferences()
    assert prefs.password_hash == "hash"
    assert prefs.mqtt_host == "h"
    assert prefs.mqtt_port == 8883
