"""Font loader for the bundled Inter font.

Inter ships with the package as two static OTFs (Regular + Bold) — see
``scripts/build_bundled_assets.py`` for the build pipeline that produced
them. ``importlib.resources`` is used so loading works whether the package
is installed editable, in a wheel, or zipped.

Falls back to Pillow's bitmap default font in environments where the OTF
can't be located (defensive — should never happen in a normal install).
"""

from __future__ import annotations

from importlib.resources import as_file, files
from typing import Literal

from PIL import ImageFont

InterWeight = Literal["regular", "bold"]

_FONT_FILES: dict[InterWeight, str] = {
    "regular": "Inter-Regular.otf",
    "bold": "Inter-Bold.otf",
}

PillowFont = ImageFont.FreeTypeFont | ImageFont.ImageFont


def load_inter(weight: InterWeight = "regular", size: int = 14) -> PillowFont:
    """Return Inter at the requested weight and pixel size.

    Args:
        weight: ``"regular"`` (the editor default) or ``"bold"``.
        size: Pixel size to rasterize at. 14 is a sensible default for
            72x72 key labels.
    """
    filename = _FONT_FILES[weight]
    try:
        resource = files("deckbridge.fonts") / filename
        with as_file(resource) as path:
            if path.is_file():
                return ImageFont.truetype(str(path), size=size)
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        pass
    return ImageFont.load_default()
