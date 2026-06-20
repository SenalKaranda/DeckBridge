"""In-memory fake Stream Deck for tests.

Implements the duck-typed contract required by
:class:`deckbridge.device.deck.Deck` and the duck-typed handle interface
inspected by :class:`deckbridge.device.manager.DeckManager`. No USB, no
hidapi — pure Python.

Tests can:
    * construct a fake with a unique serial
    * pass it (or a list of them) to a discoverer for tests of DeckManager
    * call ``simulate_press(key)`` to invoke the registered key callback as
      if the device fired an HID event from its background thread
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


class FakeStreamDeck:
    """Pretends to be a 15-key Stream Deck MK.2."""

    KEY_COUNT = 15
    KEY_PIXEL_WIDTH = 72
    KEY_PIXEL_HEIGHT = 72
    DEFAULT_SERIAL = "FAKE-MK2-0001"

    def __init__(self, serial: str | None = None) -> None:
        self._serial = serial or self.DEFAULT_SERIAL
        self._open = False
        self._key_images: dict[int, bytes] = {}
        self._key_callback: Callable[[Any, int, bool], None] | None = None
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    # ---- lifecycle ----

    def open(self) -> None:
        if self._open:
            raise RuntimeError("FakeStreamDeck already opened")
        self._open = True
        self.calls.append(("open", ()))

    def close(self) -> None:
        self._open = False
        self.calls.append(("close", ()))

    def is_open(self) -> bool:
        return self._open

    def reset(self) -> None:
        """Mirror the real handle's reset: drop pushed images so the next
        observed state matches what a real device shows after reset."""
        self._key_images.clear()
        self.calls.append(("reset", ()))

    # ---- introspection ----

    def id(self) -> str:
        """Stable HID-path-like identifier; unique per device serial."""
        return f"fake:hid:{self._serial}"

    def get_serial_number(self) -> str:
        return self._serial

    def key_count(self) -> int:
        return self.KEY_COUNT

    # ---- rendering (M4 will exercise this) ----

    def set_key_image(self, key: int, image: bytes) -> None:
        self._key_images[key] = image
        self.calls.append(("set_key_image", (key, len(image))))

    def get_key_image(self, key: int) -> bytes | None:
        return self._key_images.get(key)

    # ---- input ----

    def set_key_callback(self, callback: Callable[[Any, int, bool], None]) -> None:
        self._key_callback = callback
        self.calls.append(("set_key_callback", ()))

    def simulate_press(self, key: int, *, pressed: bool = True) -> None:
        """Invoke the registered key callback as if the device fired an HID event.

        Real Stream Decks fire on press AND release; tests can pass
        ``pressed=False`` to simulate a release.
        """
        if self._key_callback is None:
            raise RuntimeError("No key callback registered — did you call attach()?")
        self._key_callback(self, key, pressed)
