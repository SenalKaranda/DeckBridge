"""Compose key images.

A key image is a small PNG (72x72 for MK.2) that gets pushed to a Stream Deck
LCD button. We always emit RGB (no alpha) — the device draws onto an opaque
background — and let the streamdeck library convert to whatever the device
actually wants over the wire.

The renderer is intentionally pure: given inputs, it produces bytes. The
deck-painter (M6) wires this to events and the device.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

from deckbridge.fonts import load_inter

if TYPE_CHECKING:
    from collections.abc import Iterable

DEFAULT_SIZE = (72, 72)
"""Stream Deck MK.2 key resolution. XL is the same per-key size."""


class ImageRenderer:
    """Composites an optional icon and an optional text label onto a colored canvas.

    Designed for v1 simplicity: one font, one composition layout. The Editor
    UI (M5) doesn't expose font/layout choices, so we don't either.
    """

    def __init__(
        self,
        font: ImageFont.ImageFont | ImageFont.FreeTypeFont | None = None,
        *,
        label_size: int = 14,
    ) -> None:
        # The constructor's font is the renderer's default — used when render()
        # is called without an explicit font_size. Per-key font_size loads on
        # demand and is cached on the instance so repeat renders at the same
        # size don't re-read the OTF off disk.
        self._default_label_size = label_size
        self._font = font or load_inter("regular", size=label_size)
        # Pre-populate the cache with the default so callers passing the
        # exact default size hit the constructor's font (matters when the
        # caller injected a custom font fixture for tests).
        self._font_cache: dict[int, ImageFont.ImageFont | ImageFont.FreeTypeFont] = {
            label_size: self._font,
        }

    def _font_at(self, size: int | None) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
        if size is None or size == self._default_label_size:
            return self._font
        cached = self._font_cache.get(size)
        if cached is not None:
            return cached
        loaded = load_inter("regular", size=size)
        self._font_cache[size] = loaded
        return loaded

    def render(
        self,
        icon: Image.Image | bytes | None = None,
        label: str = "",
        *,
        size: tuple[int, int] = DEFAULT_SIZE,
        bg: tuple[int, int, int] = (0, 0, 0),
        fg: tuple[int, int, int] = (255, 255, 255),
        padding: int = 0,
        bg_image: Image.Image | bytes | None = None,
        icon_tint: tuple[int, int, int] | None = None,
        font_size: int | None = None,
    ) -> bytes:
        """Compose background + icon + label and return PNG bytes.

        Args:
            icon: PIL Image, raw bytes (PNG/JPEG), or None to skip the icon.
                When None, the label (if present) is centered vertically.
            label: Text drawn over the icon. Empty string skips the label.
            size: Output size in pixels. Defaults to MK.2 key size.
            bg: Solid background color drawn first.
            fg: Label text color.
            padding: Extra inset added to all four sides of the icon+label
                region. 0 keeps the built-in defaults.
            bg_image: Optional image drawn over `bg` before the icon. Fitted
                with cover semantics (scale-to-fill, center-crop) so the
                user's image always fills the key.
            icon_tint: Optional RGB tuple. When set, the icon's RGB channels
                are multiplied by this color (alpha preserved). Best for
                grayscale/white icons; will recolor a colored icon.
            font_size: Override the renderer's default label font size for
                this render only. None uses the constructor's default
                (14px in v1.0.x).
        """
        canvas = Image.new("RGB", size, bg)

        if bg_image is not None:
            self._paste_bg_image(canvas, self._coerce_icon(bg_image), size)

        if icon is not None:
            icon_image = self._coerce_icon(icon)
            if icon_tint is not None:
                icon_image = self._tint_image(icon_image, icon_tint)
            self._paste_icon(canvas, icon_image, size, has_label=bool(label), padding=padding)

        if label:
            self._draw_label(
                canvas,
                label,
                size,
                fg,
                padding=padding,
                center_vertically=icon is None,
                font=self._font_at(font_size),
            )

        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        return buf.getvalue()

    def render_solid(
        self, color: tuple[int, int, int], size: tuple[int, int] = DEFAULT_SIZE
    ) -> bytes:
        """Return PNG bytes for a single solid color. Useful as a paint-blank default."""
        canvas = Image.new("RGB", size, color)
        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        return buf.getvalue()

    # ---- internals ----

    @staticmethod
    def _coerce_icon(icon: Image.Image | bytes) -> Image.Image:
        if isinstance(icon, Image.Image):
            return icon
        return Image.open(io.BytesIO(icon))

    @staticmethod
    def _paste_icon(
        canvas: Image.Image,
        icon: Image.Image,
        size: tuple[int, int],
        *,
        has_label: bool,
        padding: int = 0,
    ) -> None:
        # Reserve space for the label at the bottom if there is one.
        # Per-key `padding` is added on top of the built-in defaults so
        # padding=0 preserves the v1.0 behavior exactly.
        margin_x = 6 + padding
        margin_top = 4 + padding
        margin_bottom = (18 if has_label else 4) + padding
        target_w = max(1, size[0] - 2 * margin_x)
        target_h = max(1, size[1] - margin_top - margin_bottom)

        # Preserve aspect ratio.
        icon = icon.convert("RGBA")
        icon.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
        offset_x = (size[0] - icon.width) // 2
        offset_y = margin_top + (target_h - icon.height) // 2
        canvas.paste(icon, (offset_x, offset_y), icon)

    def _draw_label(
        self,
        canvas: Image.Image,
        label: str,
        size: tuple[int, int],
        fg: tuple[int, int, int],
        *,
        padding: int = 0,
        center_vertically: bool = False,
        font: ImageFont.ImageFont | ImageFont.FreeTypeFont | None = None,
    ) -> None:
        draw = ImageDraw.Draw(canvas)
        active_font = font or self._font
        bbox = draw.textbbox((0, 0), label, font=active_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (size[0] - text_w) // 2
        # Label-only key: center in the canvas instead of bottom-anchoring.
        y = (size[1] - text_h) // 2 if center_vertically else size[1] - text_h - 4 - padding
        # Cheap shadow for legibility on light icons.
        draw.text((x + 1, y + 1), label, font=active_font, fill=(0, 0, 0))
        draw.text((x, y), label, font=active_font, fill=fg)

    @staticmethod
    def _paste_bg_image(
        canvas: Image.Image,
        image: Image.Image,
        size: tuple[int, int],
    ) -> None:
        """Cover-fit `image` onto `canvas`: scale to fill, center-crop excess.

        Always produces a fully-painted background regardless of the source
        aspect ratio. For non-RGBA sources we still composite via alpha so
        a transparent source falls back to whatever's underneath (the
        solid bg color from the canvas init).
        """
        rgba = image.convert("RGBA")
        src_w, src_h = rgba.size
        dst_w, dst_h = size
        if src_w == 0 or src_h == 0:
            return
        # Cover scale: pick the larger of the two ratios so the smaller
        # dimension fills the destination.
        scale = max(dst_w / src_w, dst_h / src_h)
        new_w = max(1, round(src_w * scale))
        new_h = max(1, round(src_h * scale))
        rgba = rgba.resize((new_w, new_h), Image.Resampling.LANCZOS)
        # Center-crop to destination size.
        left = (new_w - dst_w) // 2
        top = (new_h - dst_h) // 2
        rgba = rgba.crop((left, top, left + dst_w, top + dst_h))
        canvas.paste(rgba, (0, 0), rgba)

    @staticmethod
    def _tint_image(image: Image.Image, tint: tuple[int, int, int]) -> Image.Image:
        """Multiply each pixel's RGB by `tint`, preserving alpha.

        For a pure-white grayscale icon this produces exactly the tint
        color; for a colored icon it shifts every pixel toward the tint.
        """
        rgba = image.convert("RGBA")
        r, g, b, a = rgba.split()
        tr, tg, tb = tint
        r = r.point(lambda p: (p * tr) // 255)
        g = g.point(lambda p: (p * tg) // 255)
        b = b.point(lambda p: (p * tb) // 255)
        return Image.merge("RGBA", (r, g, b, a))


def render_blank(
    color: tuple[int, int, int] = (12, 12, 12), size: tuple[int, int] = DEFAULT_SIZE
) -> bytes:
    """Module-level convenience for callers that don't need a renderer instance."""
    return ImageRenderer().render_solid(color, size)


def iter_default_palette() -> Iterable[tuple[int, int, int]]:
    """A small palette useful for tests and for diagnostic 'paint each key' modes."""
    yield (40, 40, 40)
    yield (160, 32, 32)
    yield (32, 160, 32)
    yield (32, 32, 160)
    yield (200, 200, 32)
