"""Smoke tests verifying the package imports and basic surface is intact.

These exist so that `pytest` exits 0 (not 5 = no tests collected) on a fresh
scaffold and so CI has something to validate from day one.
"""

from __future__ import annotations


def test_package_importable() -> None:
    import deckbridge

    assert hasattr(deckbridge, "__version__")
    assert isinstance(deckbridge.__version__, str)
    assert deckbridge.__version__


def test_cli_entry_point_runs_without_args() -> None:
    from deckbridge.cli import main

    rc = main([])
    assert rc == 0


def test_cli_version_flag_exits_zero() -> None:
    """argparse's `action="version"` exits via SystemExit(0)."""
    import pytest

    from deckbridge.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
