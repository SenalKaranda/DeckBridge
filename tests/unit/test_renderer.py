"""ImageRenderer composes icon + label into a 72x72 PNG."""

from __future__ import annotations

import io

from PIL import Image

from deckbridge.device.renderer import DEFAULT_SIZE, ImageRenderer, render_blank


def _decode(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


def _make_icon(
    color: tuple[int, int, int] = (200, 50, 50), size: tuple[int, int] = (40, 40)
) -> bytes:
    img = Image.new("RGBA", size, (*color, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_render_solid_emits_png_at_default_size() -> None:
    out = ImageRenderer().render_solid((255, 0, 0))
    assert out.startswith(b"\x89PNG")
    img = _decode(out)
    assert img.size == DEFAULT_SIZE
    assert img.mode == "RGB"
    assert img.getpixel((0, 0)) == (255, 0, 0)


def test_render_solid_custom_size() -> None:
    out = ImageRenderer().render_solid((0, 200, 0), size=(96, 96))
    assert _decode(out).size == (96, 96)


def test_render_blank_helper() -> None:
    out = render_blank((10, 20, 30))
    img = _decode(out)
    assert img.size == DEFAULT_SIZE
    assert img.getpixel((0, 0)) == (10, 20, 30)


def test_render_label_only_draws_some_foreground() -> None:
    out = ImageRenderer().render(label="OK", bg=(0, 0, 0), fg=(255, 255, 255))
    img = _decode(out)
    assert img.size == DEFAULT_SIZE
    # The label area should contain at least one non-black pixel (the text).
    # Walk a small region rather than calling the deprecated `getdata()`.
    has_fg = False
    for y in range(DEFAULT_SIZE[1]):
        for x in range(DEFAULT_SIZE[0]):
            if img.getpixel((x, y)) != (0, 0, 0):
                has_fg = True
                break
        if has_fg:
            break
    assert has_fg, "label pixels should be drawn"


def _center_rgb(img: Image.Image) -> tuple[int, int, int]:
    cx, cy = DEFAULT_SIZE[0] // 2, DEFAULT_SIZE[1] // 2
    pixel = img.getpixel((cx, cy))
    assert isinstance(pixel, tuple)
    assert len(pixel) >= 3
    return int(pixel[0]), int(pixel[1]), int(pixel[2])


def test_render_icon_only_centers_icon() -> None:
    icon_bytes = _make_icon((200, 50, 50), (40, 40))
    out = ImageRenderer().render(icon=icon_bytes, bg=(0, 0, 0))
    img = _decode(out)
    assert img.size == DEFAULT_SIZE
    # Center pixel should be reddish (the icon).
    r, g, b = _center_rgb(img)
    assert r > g
    assert r > b


def test_render_accepts_pil_image_directly() -> None:
    icon = Image.new("RGBA", (50, 50), (50, 50, 200, 255))
    out = ImageRenderer().render(icon=icon, bg=(0, 0, 0))
    img = _decode(out)
    assert img.size == DEFAULT_SIZE
    r, g, b = _center_rgb(img)
    assert b > r
    assert b > g


def test_render_with_icon_and_label() -> None:
    out = ImageRenderer().render(icon=_make_icon(), label="Hi")
    img = _decode(out)
    assert img.size == DEFAULT_SIZE
    # Check the bottom region contains some non-bg pixels (the label).
    bottom_band = [img.getpixel((x, DEFAULT_SIZE[1] - 6)) for x in range(DEFAULT_SIZE[0])]
    assert any(p != (0, 0, 0) for p in bottom_band)


def test_render_returns_bytes_decodable_as_png() -> None:
    out = ImageRenderer().render(label="x")
    assert out[:8] == b"\x89PNG\r\n\x1a\n"


# ---- per-key padding ----


def _icon_pixel_count(img: Image.Image, color_predicate: object) -> int:
    """How many pixels in the rendered key match the icon's color?"""
    count = 0
    for y in range(DEFAULT_SIZE[1]):
        for x in range(DEFAULT_SIZE[0]):
            pixel = img.getpixel((x, y))
            if isinstance(pixel, tuple) and len(pixel) >= 3:
                if color_predicate(int(pixel[0]), int(pixel[1]), int(pixel[2])):  # type: ignore[operator]
                    count += 1
    return count


def test_render_padding_shrinks_icon_footprint() -> None:
    """Higher padding means a smaller pasted icon (renderer thumbnails to fit
    a smaller target rect). The reddish icon should occupy strictly fewer
    pixels at padding=12 than at padding=0."""
    icon_bytes = _make_icon((200, 50, 50), (60, 60))

    def is_reddish(r: int, g: int, b: int) -> bool:
        return r > 150 and g < 100 and b < 100

    no_padding = _decode(ImageRenderer().render(icon=icon_bytes, bg=(0, 0, 0), padding=0))
    big_padding = _decode(ImageRenderer().render(icon=icon_bytes, bg=(0, 0, 0), padding=12))

    n0 = _icon_pixel_count(no_padding, is_reddish)
    n12 = _icon_pixel_count(big_padding, is_reddish)
    assert n0 > 0, "icon should be visible at padding=0"
    assert n12 > 0, "icon should still be visible at padding=12"
    assert n12 < n0, f"padding=12 should shrink icon footprint (got {n12} >= {n0})"


def test_render_padding_zero_matches_pre_padding_default() -> None:
    """padding=0 must produce identical bytes to omitting the kwarg, so
    existing keys (and existing cached PNGs) keep rendering identically."""
    r = ImageRenderer()
    icon = _make_icon()
    assert r.render(icon=icon, label="A") == r.render(icon=icon, label="A", padding=0)


def test_render_padding_caps_target_area_above_zero() -> None:
    """Even at the upper-bound padding=20 on a 72x72 canvas (which would
    leave a negative target rect for the label-reserved row), render must
    not raise. The renderer clamps target dims at 1px."""
    icon_bytes = _make_icon()
    out = ImageRenderer().render(icon=icon_bytes, label="X", padding=20)
    assert out.startswith(b"\x89PNG")


# ---- v1.1 presentation knobs ----


def test_render_custom_bg_color_paints_corners() -> None:
    """The bg color is painted before everything; corner pixels (well outside
    the icon's pasted area) must match it exactly."""
    out = ImageRenderer().render(bg=(40, 80, 120))
    img = _decode(out)
    assert img.getpixel((0, 0)) == (40, 80, 120)
    assert img.getpixel((71, 71)) == (40, 80, 120)


def test_render_bg_image_overrides_solid_color_at_corners() -> None:
    """When a bg image is supplied it cover-fills the canvas, so the solid
    bg color is no longer visible at the corners."""
    # Make a full 72x72 magenta image so cover fitting paints every pixel.
    bg_img = Image.new("RGBA", (72, 72), (200, 0, 200, 255))
    out = ImageRenderer().render(bg=(0, 0, 0), bg_image=bg_img)
    img = _decode(out)
    pixel = img.getpixel((0, 0))
    assert isinstance(pixel, tuple)
    r, g, b = int(pixel[0]), int(pixel[1]), int(pixel[2])
    assert r > 100, f"expected magenta R, got ({r},{g},{b})"
    assert b > 100, f"expected magenta B, got ({r},{g},{b})"


def test_render_bg_image_cover_fits_non_square_source() -> None:
    """A wide source is scaled until the SHORTER side fills the destination,
    then center-cropped — every output pixel is from the image, not from
    the canvas's solid bg fill underneath."""
    wide = Image.new("RGBA", (200, 50), (10, 200, 30, 255))
    out = ImageRenderer().render(bg=(255, 0, 0), bg_image=wide)
    img = _decode(out)
    # No red (bg) should remain visible anywhere.
    for y in (0, 35, 71):
        for x in (0, 35, 71):
            pixel = img.getpixel((x, y))
            assert isinstance(pixel, tuple)
            r, g, b = int(pixel[0]), int(pixel[1]), int(pixel[2])
            assert not (r > 200 and g < 50 and b < 50), (
                f"red bg leaked through at ({x},{y}): {pixel}"
            )


def test_render_label_centered_vertically_when_no_icon() -> None:
    """When `icon=None` is passed, the label is centered in the canvas
    instead of bottom-anchored. We assert by finding the topmost label
    pixel and checking it sits noticeably above the bottom-anchored
    baseline (~y=58 for default size)."""
    out = ImageRenderer().render(icon=None, label="HI")
    img = _decode(out)
    topmost = None
    for y in range(DEFAULT_SIZE[1]):
        for x in range(DEFAULT_SIZE[0]):
            if img.getpixel((x, y)) != (0, 0, 0):
                topmost = y
                break
        if topmost is not None:
            break
    assert topmost is not None, "label should be drawn"
    # Bottom-anchored label starts around y ≈ 54-56; centered should be much higher.
    assert topmost < 40, f"label not vertically centered (topmost pixel at y={topmost})"


def test_render_icon_tint_recolors_white_icon() -> None:
    """A white icon multiplied by green should produce green pixels."""
    white_icon = Image.new("RGBA", (40, 40), (255, 255, 255, 255))
    out = ImageRenderer().render(icon=white_icon, icon_tint=(0, 200, 0), bg=(0, 0, 0))
    img = _decode(out)
    r, g, b = _center_rgb(img)
    assert g > 100, f"tinted icon should be greenish at center, got ({r},{g},{b})"
    assert r < 50, f"red channel should be near zero, got ({r},{g},{b})"
    assert b < 50, f"blue channel should be near zero, got ({r},{g},{b})"


def test_render_label_color_changes_text_pixels() -> None:
    """Label fg controls the text pixel color (the shadow stays black)."""
    yellow = ImageRenderer().render(label="X", fg=(255, 255, 0), bg=(0, 0, 0))
    cyan = ImageRenderer().render(label="X", fg=(0, 255, 255), bg=(0, 0, 0))
    assert yellow != cyan, "label color must affect output bytes"


def test_render_defaults_are_byte_identical_to_pre_v1_1() -> None:
    """v1.1 added bg_image and icon_tint kwargs; calling render() without
    them must produce the exact same bytes as before, so existing keys and
    cached PNGs render identically after an upgrade."""
    r = ImageRenderer()
    icon = _make_icon()
    legacy = r.render(icon=icon, label="OK")
    explicit = r.render(icon=icon, label="OK", bg_image=None, icon_tint=None)
    assert legacy == explicit


# ---- per-key font size ----


def _label_pixel_count(img: Image.Image) -> int:
    """Count non-bg pixels in a black-bg label-only render — proxy for how
    much space the rasterized text occupies."""
    count = 0
    for y in range(DEFAULT_SIZE[1]):
        for x in range(DEFAULT_SIZE[0]):
            if img.getpixel((x, y)) != (0, 0, 0):
                count += 1
    return count


def test_render_font_size_default_matches_pre_font_size_kwarg() -> None:
    """Calling render() with font_size=None or font_size=14 must produce the
    same bytes as the pre-1.1.1 default — existing cached PNGs survive."""
    r = ImageRenderer()
    legacy = r.render(label="Hi")
    explicit_default = r.render(label="Hi", font_size=14)
    none_default = r.render(label="Hi", font_size=None)
    assert legacy == explicit_default == none_default


def test_render_font_size_smaller_yields_fewer_label_pixels() -> None:
    """A label drawn at 8pt should occupy strictly fewer non-bg pixels than
    the same label at the default 14pt — this is what makes long labels fit."""
    r = ImageRenderer()
    big = _decode(r.render(label="Hello", font_size=14))
    small = _decode(r.render(label="Hello", font_size=8))
    assert _label_pixel_count(small) < _label_pixel_count(big)


def test_render_font_size_caches_loaded_font_per_size() -> None:
    """The renderer caches loaded fonts keyed by size on its instance, so
    repeat renders at the same size don't re-read the OTF off disk. Verify
    by inspecting the cache after several renders."""
    r = ImageRenderer()
    r.render(label="A", font_size=12)
    r.render(label="B", font_size=12)  # second 12pt render — should hit cache
    r.render(label="C", font_size=20)
    # Default size is pre-populated; 12 and 20 added on demand.
    assert set(r._font_cache.keys()) == {14, 12, 20}
