"""DeckPainter — render keys and push them to attached Stream Decks.

Subscribes to:

* :class:`~deckbridge.events.ActivePageChanged` — re-render every slot on
  the deck for the new page.
* :class:`~deckbridge.events.KeyStateUpdated` — re-render only the affected
  key (with the state-mapped icon).
* :class:`~deckbridge.events.KeyConfigChanged` — invalidate the painter's
  cache for that key, then re-render if its page is currently visible.

The painter doesn't own deck lifecycle (that's :class:`DeckManager`) or
event routing (that's the bus); it's strictly a renderer + dispatcher.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from deckbridge.events.types import (
    ActivePageChanged,
    Event,
    KeyConfigChanged,
    KeyStateUpdated,
)
from deckbridge.logging_ import get_logger

if TYPE_CHECKING:
    from deckbridge.actions import ActivePages
    from deckbridge.device.cache import KeyImageCache
    from deckbridge.device.deck import Deck
    from deckbridge.device.manager import DeckManager
    from deckbridge.device.renderer import ImageRenderer
    from deckbridge.events import EventBus
    from deckbridge.icons.library import IconLibrary
    from deckbridge.storage import Storage
    from deckbridge.storage.schema import Key


class DeckPainter:
    def __init__(
        self,
        bus: EventBus,
        storage: Storage,
        deck_manager: DeckManager,
        icon_library: IconLibrary,
        renderer: ImageRenderer,
        cache: KeyImageCache,
        active_pages: ActivePages,
    ) -> None:
        self._bus = bus
        self._storage = storage
        self._deck_manager = deck_manager
        self._icon_library = icon_library
        self._renderer = renderer
        self._cache = cache
        self._active_pages = active_pages
        # Last seen state value per (page_id, slot). Kept in memory only;
        # MQTT republishes any retained state on reconnect, so we'd repopulate
        # naturally even after a daemon restart.
        self._last_state: dict[tuple[str, int], str] = {}
        self._log = get_logger(__name__)

        bus.subscribe(ActivePageChanged, self._on_active_page_changed)
        bus.subscribe(KeyStateUpdated, self._on_key_state_updated)
        bus.subscribe(KeyConfigChanged, self._on_key_config_changed)

    # ---- event handlers --------------------------------------------------

    async def _on_active_page_changed(self, event: Event) -> None:
        if not isinstance(event, ActivePageChanged):
            return
        deck = self._deck_manager.decks.get(event.serial)
        if deck is None:
            return
        await self._render_page(deck, event.page_id)

    async def _on_key_state_updated(self, event: Event) -> None:
        if not isinstance(event, KeyStateUpdated):
            return
        self._last_state[(event.page_id, event.slot)] = event.value
        for serial, page_id in self._active_pages.all().items():
            if page_id != event.page_id:
                continue
            deck = self._deck_manager.decks.get(serial)
            if deck is not None:
                await self._render_slot(deck, event.page_id, event.slot)

    async def _on_key_config_changed(self, event: Event) -> None:
        if not isinstance(event, KeyConfigChanged):
            return
        self._cache.invalidate_key(event.page_id, event.slot)
        for serial, page_id in self._active_pages.all().items():
            if page_id != event.page_id:
                continue
            deck = self._deck_manager.decks.get(serial)
            if deck is not None:
                await self._render_slot(deck, event.page_id, event.slot)

    # ---- rendering -------------------------------------------------------

    async def _render_page(self, deck: Deck, page_id: str) -> None:
        for slot in range(deck.key_count):
            await self._render_slot(deck, page_id, slot)

    async def _render_slot(self, deck: Deck, page_id: str, slot: int) -> None:
        key = self._storage.get_key(page_id, slot)
        state_value = self._last_state.get((page_id, slot))
        cached = self._cache.get(page_id, slot, state_value)
        if cached is not None:
            deck.set_key_image(slot, cached)
            return

        png_bytes = self._compose(key, state_value)
        self._cache.put(page_id, slot, state_value, png_bytes)
        deck.set_key_image(slot, png_bytes)

    def _compose(self, key: Key | None, state_value: str | None) -> bytes:
        if key is None:
            return self._renderer.render_solid((12, 12, 12))
        # Honor show_icon / show_label gates by short-circuiting here so
        # the renderer never sees data the user asked to hide. The stored
        # label/icon_id values are preserved across toggles either way.
        icon_bytes: bytes | None = None
        if key.show_icon:
            icon_id = _resolve_icon_id(key, state_value)
            if icon_id:
                icon_bytes = self._icon_library.get_bytes(icon_id)
        bg_image_bytes = self._icon_library.get_bytes(key.bg_image_id) if key.bg_image_id else None
        return self._renderer.render(
            icon=icon_bytes,
            label=key.label if key.show_label else "",
            padding=key.padding,
            bg=_hex_to_rgb(key.bg_color),
            fg=_hex_to_rgb(key.label_color),
            bg_image=bg_image_bytes,
            icon_tint=_hex_to_rgb(key.icon_color) if key.icon_color else None,
            font_size=key.font_size,
        )


def _resolve_icon_id(key: Key, state_value: str | None) -> str | None:
    """Pick the icon for this key given the current state value, if any."""
    if key.state is not None and state_value is not None:
        mapped = key.state.icon_map.get(state_value)
        if mapped:
            return mapped
        if key.state.default_icon_id:
            return key.state.default_icon_id
    return key.icon_id


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert `#RRGGBB` to a 3-tuple. The schema's pattern guard means
    we don't need defensive parsing here — invalid values can't reach this."""
    return (
        int(hex_color[1:3], 16),
        int(hex_color[3:5], 16),
        int(hex_color[5:7], 16),
    )
