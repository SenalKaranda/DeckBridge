"""DeckPainter — render+push on ActivePageChanged, KeyStateUpdated, KeyConfigChanged."""

from __future__ import annotations

from pathlib import Path

from deckbridge.actions import ActivePages
from deckbridge.device import DeckManager
from deckbridge.device.cache import KeyImageCache
from deckbridge.device.painter import DeckPainter, _resolve_icon_id
from deckbridge.device.renderer import ImageRenderer
from deckbridge.events import EventBus
from deckbridge.events.types import (
    ActivePageChanged,
    KeyConfigChanged,
    KeyStateUpdated,
)
from deckbridge.icons.library import IconLibrary
from deckbridge.storage import SqliteStorage, run_migrations
from deckbridge.storage.schema import (
    Icon,
    IconSource,
    Key,
    Page,
    StateSubscription,
)
from tests.fixtures.fake_deck import FakeStreamDeck

# ---- pure helper --------------------------------------------------------


def test_resolve_icon_id_no_state_uses_default() -> None:
    key = Key(page_id="p", slot=0, icon_id="lucide:home")
    assert _resolve_icon_id(key, None) == "lucide:home"


def test_resolve_icon_id_state_value_takes_priority() -> None:
    key = Key(
        page_id="p",
        slot=0,
        icon_id="lucide:home",
        state=StateSubscription(topic="x", icon_map={"on": "lucide:lightbulb"}),
    )
    assert _resolve_icon_id(key, "on") == "lucide:lightbulb"


def test_resolve_icon_id_falls_back_to_state_default() -> None:
    key = Key(
        page_id="p",
        slot=0,
        icon_id="lucide:home",
        state=StateSubscription(
            topic="x", icon_map={"on": "lucide:lightbulb"}, default_icon_id="lucide:question"
        ),
    )
    assert _resolve_icon_id(key, "unknown") == "lucide:question"


def test_resolve_icon_id_falls_back_to_key_icon_when_no_state_default() -> None:
    key = Key(
        page_id="p",
        slot=0,
        icon_id="lucide:home",
        state=StateSubscription(topic="x", icon_map={"on": "lucide:lightbulb"}),
    )
    assert _resolve_icon_id(key, "off") == "lucide:home"


# ---- painter integration ------------------------------------------------


async def _make_painter(
    tmp_path: Path,
) -> tuple[DeckPainter, EventBus, DeckManager, FakeStreamDeck, ActivePages, SqliteStorage]:
    bus = EventBus()
    storage = SqliteStorage(":memory:")
    run_migrations(storage)
    fake = FakeStreamDeck(serial="ABC")
    manager = DeckManager(bus, lambda: [fake])
    await manager.start()  # attaches the fake
    icon_library = IconLibrary(storage, tmp_path)
    cache = KeyImageCache(tmp_path)
    active_pages = ActivePages()
    painter = DeckPainter(
        bus,
        storage,
        manager,
        icon_library,
        ImageRenderer(),
        cache,
        active_pages,
    )
    return painter, bus, manager, fake, active_pages, storage


async def test_active_page_changed_paints_every_slot(tmp_path: Path) -> None:
    painter, bus, manager, fake, active_pages, storage = await _make_painter(tmp_path)
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    active_pages.set("ABC", "p1")
    fake.calls.clear()

    await bus.publish(ActivePageChanged(serial="ABC", page_id="p1"))

    set_calls = [c for c in fake.calls if c[0] == "set_key_image"]
    assert len(set_calls) == fake.key_count()
    await manager.stop()
    del painter  # silence linter


async def test_key_state_updated_re_renders_only_that_slot(tmp_path: Path) -> None:
    painter, bus, manager, fake, active_pages, storage = await _make_painter(tmp_path)
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    active_pages.set("ABC", "p1")
    fake.calls.clear()

    await bus.publish(KeyStateUpdated(page_id="p1", slot=7, value="on"))

    set_calls = [c for c in fake.calls if c[0] == "set_key_image"]
    assert len(set_calls) == 1
    assert set_calls[0][1][0] == 7
    await manager.stop()
    del painter


async def test_key_state_updated_for_inactive_page_is_noop(tmp_path: Path) -> None:
    painter, bus, manager, fake, active_pages, storage = await _make_painter(tmp_path)
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    storage.upsert_page(Page(id="p2", deck_serial="ABC"))
    active_pages.set("ABC", "p1")
    fake.calls.clear()

    await bus.publish(KeyStateUpdated(page_id="p2", slot=0, value="on"))

    set_calls = [c for c in fake.calls if c[0] == "set_key_image"]
    assert set_calls == []
    await manager.stop()
    del painter


async def test_key_config_changed_invalidates_and_repaints(tmp_path: Path) -> None:
    painter, bus, manager, fake, active_pages, storage = await _make_painter(tmp_path)
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    active_pages.set("ABC", "p1")
    # Pre-populate the cache so we can prove invalidation happened.
    cache = painter._cache
    cache.put("p1", 5, None, b"OLD-CACHED-BYTES")
    assert cache.get("p1", 5, None) == b"OLD-CACHED-BYTES"
    fake.calls.clear()

    await bus.publish(KeyConfigChanged(page_id="p1", slot=5))

    # Cache entry was invalidated then re-populated with newly rendered bytes.
    fresh = cache.get("p1", 5, None)
    assert fresh is not None
    assert fresh != b"OLD-CACHED-BYTES"
    assert fresh.startswith(b"\x89PNG")
    set_calls = [c for c in fake.calls if c[0] == "set_key_image"]
    assert len(set_calls) == 1
    assert set_calls[0][1][0] == 5
    await manager.stop()


async def test_cache_hit_short_circuits_render(tmp_path: Path) -> None:
    """A cached entry should be pushed without invoking the renderer.

    Verified by pre-populating the cache with a renderer-produced PNG that
    has a distinctive size (a 32x32 blank), then asserting the same byte
    length lands on the deck for that slot.
    """
    painter, bus, manager, fake, active_pages, storage = await _make_painter(tmp_path)
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    active_pages.set("ABC", "p1")

    # Build a real PNG that's distinctly sized vs the renderer's default
    # 72x72 output, so we can tell cached-hit bytes apart from re-rendered.
    sentinel = ImageRenderer().render_solid((255, 0, 255), size=(32, 32))
    painter._cache.put("p1", 0, None, sentinel)

    fake.calls.clear()
    await bus.publish(ActivePageChanged(serial="ABC", page_id="p1"))

    slot0_calls = [c for c in fake.calls if c[0] == "set_key_image" and c[1][0] == 0]
    assert len(slot0_calls) == 1
    # FakeStreamDeck records (slot, len(bytes)). Sentinel length must match.
    assert slot0_calls[0][1][1] == len(sentinel)
    await manager.stop()


async def test_no_active_page_no_renders_on_state_update(tmp_path: Path) -> None:
    painter, bus, manager, fake, active_pages, storage = await _make_painter(tmp_path)
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    # active_pages intentionally empty
    fake.calls.clear()

    await bus.publish(KeyStateUpdated(page_id="p1", slot=0, value="on"))

    assert [c for c in fake.calls if c[0] == "set_key_image"] == []
    await manager.stop()
    del painter
    del active_pages


async def test_state_value_picks_mapped_icon(tmp_path: Path) -> None:
    """Render path with state→icon mapping uses the mapped icon's bytes."""
    _painter, bus, manager, fake, active_pages, storage = await _make_painter(tmp_path)
    storage.upsert_page(Page(id="p1", deck_serial="ABC"))
    storage.upsert_icon(
        Icon(id="lucide:lightbulb", source=IconSource.BUNDLED, reference="lightbulb")
    )
    storage.upsert_icon(
        Icon(
            id="lucide:lightbulb-off",
            source=IconSource.BUNDLED,
            reference="lightbulb-off",
        )
    )
    storage.upsert_key(
        Key(
            page_id="p1",
            slot=0,
            state=StateSubscription(
                topic="home/light/state",
                icon_map={"on": "lucide:lightbulb", "off": "lucide:lightbulb-off"},
            ),
        )
    )
    active_pages.set("ABC", "p1")
    fake.calls.clear()

    await bus.publish(KeyStateUpdated(page_id="p1", slot=0, value="on"))
    on_bytes = next(c for c in fake.calls if c[0] == "set_key_image" and c[1][0] == 0)[1][1]

    fake.calls.clear()
    await bus.publish(KeyStateUpdated(page_id="p1", slot=0, value="off"))
    off_bytes = next(c for c in fake.calls if c[0] == "set_key_image" and c[1][0] == 0)[1][1]

    # Different state -> different rendered byte length (icons differ).
    assert on_bytes != off_bytes
    await manager.stop()
