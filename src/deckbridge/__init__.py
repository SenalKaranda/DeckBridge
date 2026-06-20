"""DeckBridge — network-accessible smart-button bridge for the Elgato Stream Deck."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("deckbridge")
except PackageNotFoundError:  # not installed (e.g. running from source without `pip install -e`)
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
