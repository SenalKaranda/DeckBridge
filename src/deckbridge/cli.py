"""DeckBridge command-line interface.

Subcommands:

    deckbridge run                Start the daemon (uvicorn + FastAPI app).
    deckbridge --version          Print package version.

Subcommands ``doctor``, ``reset-password``, and ``migrate`` are stubbed to
print "not yet implemented" until the corresponding milestones land
(M2, M5, M3 respectively).
"""

from __future__ import annotations

import argparse
import sys

from deckbridge import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="deckbridge",
        description="Network-accessible smart-button bridge for the Elgato Stream Deck.",
    )
    parser.add_argument("-V", "--version", action="version", version=f"deckbridge {__version__}")

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    subparsers.add_parser("run", help="Start the DeckBridge daemon.")
    subparsers.add_parser("doctor", help="Diagnose environment (stub, future).")
    subparsers.add_parser("reset-password", help="Reset the web UI password (stub, M5).")
    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Copy data from one storage backend to another in the same data dir.",
    )
    migrate_parser.add_argument(
        "--from",
        dest="from_backend",
        choices=["sqlite", "files"],
        help="Source backend (default: current DECKBRIDGE_STORAGE_BACKEND).",
    )
    migrate_parser.add_argument(
        "--to",
        choices=["sqlite", "files"],
        required=True,
        help="Target backend.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        # Imported lazily so `deckbridge --version` doesn't pay for uvicorn.
        from deckbridge.main import run

        run()
        return 0

    if args.command == "migrate":
        return _cmd_migrate(args.from_backend, args.to)

    if args.command in {"doctor", "reset-password"}:
        print(f"deckbridge {args.command}: not yet implemented", file=sys.stderr)
        return 2

    if args.command is None:
        parser.print_help(sys.stderr)
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2  # unreachable; argparse exits on error


def _cmd_migrate(from_backend: str | None, to_backend: str) -> int:
    from deckbridge.settings import load_settings
    from deckbridge.storage import open_storage

    settings = load_settings()
    src_backend = from_backend or settings.storage_backend
    if src_backend == to_backend:
        print(
            f"Source and destination are both '{to_backend}'; nothing to do.",
            file=sys.stderr,
        )
        return 1

    src = open_storage(src_backend, settings.data_dir)
    dst = open_storage(to_backend, settings.data_dir)
    try:
        snapshot = src.export_snapshot()
        dst.import_snapshot(snapshot)
    finally:
        src.close()
        dst.close()
    print(
        f"Migrated from '{src_backend}' to '{to_backend}' under {settings.data_dir}.",
        file=sys.stderr,
    )
    print(
        f"Set DECKBRIDGE_STORAGE_BACKEND={to_backend} and restart the daemon.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
