#!/usr/bin/env python3
"""Build bundled assets (Lucide icons + Inter font) into the source tree.

Run once at scaffold time. Re-run when the LUCIDE_ICONS list changes or to
refresh the Inter font.

Output paths (committed to the repo):
    src/deckbridge/icons/bundled/<name>.png        (72x72 RGBA, white on transparent)
    src/deckbridge/icons/LICENSE-Lucide.md         (Lucide ISC license)
    src/deckbridge/fonts/Inter-Regular.otf
    src/deckbridge/fonts/Inter-Bold.otf
    src/deckbridge/fonts/LICENSE-Inter.txt         (Inter OFL license)

Requires the dev extras (`pip install -e ".[dev]"`) for svglib + reportlab.
End users do NOT need to run this script — the artifacts are in the wheel.
"""

from __future__ import annotations

import io
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

LUCIDE_ICONS: list[str] = [
    # Lights / climate
    "lightbulb",
    "lightbulb-off",
    "lamp",
    "sun",
    "moon",
    "thermometer",
    "snowflake",
    "flame",
    "droplets",
    "fan",
    # Power / connectivity
    "power",
    "battery",
    "battery-low",
    "battery-charging",
    "plug",
    "plug-zap",
    "wifi",
    "wifi-off",
    # Security (Lucide renamed unlock -> lock-open, alert-* -> triangle-alert / circle-alert)
    "lock",
    "lock-open",
    "shield",
    "shield-check",
    "door-open",
    "door-closed",
    # Audio
    "volume-1",
    "volume-2",
    "volume-x",
    "mic",
    "mic-off",
    "headphones",
    "speaker",
    "music",
    "bluetooth",
    "repeat",
    # Media playback (Lucide renamed stop-circle -> circle-stop)
    "play",
    "pause",
    "circle-stop",
    "skip-forward",
    "skip-back",
    "fast-forward",
    "rewind",
    "shuffle",
    # Video / camera
    "video",
    "video-off",
    "camera",
    "camera-off",
    "monitor",
    # Notifications / status
    "bell",
    "bell-off",
    "triangle-alert",
    "circle-alert",
    "info",
    "check",
    "x",
    "circle-check",
    "circle-x",
    "star",
    # Navigation (Lucide renamed filter -> funnel)
    "house",
    "settings",
    "menu",
    "search",
    "funnel",
    "sliders-horizontal",
    "plus",
    "minus",
    "arrow-up",
    "arrow-down",
    "arrow-left",
    "arrow-right",
    # Time / scheduling
    "clock",
    "calendar",
    "timer",
    "hourglass",
    # Files / data / sharing
    "folder",
    "file",
    "image",
    "download",
    "upload",
    "link",
    # Communication / people
    "user",
    "users",
    "message-circle",
    "mail",
    "phone",
    "phone-off",
]
"""Curated v1 set. ~85 icons covering smart-home, AV, and common UI use cases.

Note: ``house`` is the modern Lucide name for what used to be ``home``; using
the canonical current name. The IconLibrary computes user-facing names from
the filename, so this still appears as 'House' in the UI.
"""

LUCIDE_RAW = "https://raw.githubusercontent.com/lucide-icons/lucide/main/icons/{name}.svg"
LUCIDE_LICENSE_URL = "https://raw.githubusercontent.com/lucide-icons/lucide/main/LICENSE"

# Inter restructured into release zips; individual font URLs (rsms.me, master
# branch raw, jsdelivr) all 404. We pull the official release zip and extract
# the two OTFs we need.
INTER_RELEASE_ZIP_URL = "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip"
INTER_LICENSE_URL = "https://raw.githubusercontent.com/rsms/inter/master/LICENSE.txt"

ROOT = Path(__file__).resolve().parent.parent
ICONS_DIR = ROOT / "src" / "deckbridge" / "icons" / "bundled"
ICONS_LICENSE_PATH = ROOT / "src" / "deckbridge" / "icons" / "LICENSE-Lucide.md"
FONTS_DIR = ROOT / "src" / "deckbridge" / "fonts"

USER_AGENT = "DeckBridge-build-script/1.1.0 (+https://git.senal.dev/Senal/DeckBridge)"
TARGET_PIXELS = 72


def fetch(url: str) -> bytes:
    print(f"  fetch {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()


def render_svg_to_png(svg_text: str, size: int = TARGET_PIXELS) -> bytes:
    """Render Lucide SVG to a 72x72 RGBA PNG with white strokes on transparent bg.

    Strategy: replace ``currentColor`` references with white, render on a black
    background (so we keep clean anti-aliasing), then post-process the result
    to convert luminance to alpha — black pixels become transparent, white
    pixels stay opaque white, anti-aliased grays interpolate alpha.
    """
    from PIL import Image
    from reportlab.graphics import renderPM
    from svglib.svglib import svg2rlg

    patched = svg_text.replace('stroke="currentColor"', 'stroke="#ffffff"').replace(
        'fill="currentColor"', 'fill="#ffffff"'
    )

    drawing = svg2rlg(io.BytesIO(patched.encode("utf-8")))
    if drawing is None:
        raise RuntimeError("svglib returned no drawing")

    # Lucide SVGs are 24x24 viewBox; scale uniformly to size.
    factor = size / drawing.width
    drawing.width = size
    drawing.height = size
    drawing.scale(factor, factor)

    raw_png = renderPM.drawToString(drawing, fmt="PNG", bg=0x000000)

    # Convert luminance to alpha so the background is transparent.
    img = Image.open(io.BytesIO(raw_png)).convert("RGBA")
    pixels = img.load()
    if pixels is None:
        raise RuntimeError("PIL returned no pixel access object")
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, _ = pixels[x, y]
            luminance = (r + g + b) // 3
            pixels[x, y] = (255, 255, 255, luminance)

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def build_icons() -> tuple[int, int]:
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    failed = 0
    for name in LUCIDE_ICONS:
        out = ICONS_DIR / f"{name}.png"
        try:
            svg = fetch(LUCIDE_RAW.format(name=name)).decode("utf-8")
        except urllib.error.HTTPError as exc:
            print(f"  WARN: {name} not found ({exc.code}); skipping")
            failed += 1
            continue
        png = render_svg_to_png(svg)
        out.write_bytes(png)
        print(f"    wrote {out.relative_to(ROOT)} ({len(png)} bytes)")
        ok += 1
    return ok, failed


def fetch_lucide_license() -> None:
    print("Fetching Lucide LICENSE...")
    data = fetch(LUCIDE_LICENSE_URL)
    ICONS_LICENSE_PATH.write_bytes(data)
    print(f"    wrote {ICONS_LICENSE_PATH.relative_to(ROOT)}")


def build_fonts() -> None:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    print("  downloading Inter release zip (this may take a moment)...")
    zip_bytes = fetch(INTER_RELEASE_ZIP_URL)
    print(f"    got zip ({len(zip_bytes)} bytes); extracting Regular + Bold OTFs")

    wanted = {"Inter-Regular.otf", "Inter-Bold.otf"}
    extracted: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            base = info.filename.rsplit("/", 1)[-1]
            if base in wanted and base not in extracted:
                out = FONTS_DIR / base
                out.write_bytes(zf.read(info))
                extracted.add(base)
                print(f"    wrote {out.relative_to(ROOT)} ({info.file_size} bytes)")

    missing = wanted - extracted
    if missing:
        raise RuntimeError(
            f"Could not find {sorted(missing)} inside {INTER_RELEASE_ZIP_URL}. "
            "The release zip layout may have changed; inspect zf.namelist() to "
            "find the new paths."
        )

    license_data = fetch(INTER_LICENSE_URL)
    license_out = FONTS_DIR / "LICENSE-Inter.txt"
    license_out.write_bytes(license_data)
    print(f"    wrote {license_out.relative_to(ROOT)}")


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    do_icons = not args or "icons" in args
    do_fonts = not args or "fonts" in args

    if do_icons:
        print("=== Building Lucide bundled icons ===")
        ok, failed = build_icons()
        print(f"  -> {ok} icons rendered, {failed} skipped")
        fetch_lucide_license()

    if do_fonts:
        print("=== Building Inter font ===")
        build_fonts()

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
