"""Versioned schema migrations.

Each migration is a function that takes the snapshot at version ``N`` and
returns a snapshot at version ``N + 1``. Migrations apply in order, both for
SQLite and file backends — the storage layer's :meth:`Storage.export_snapshot`
and :meth:`Storage.import_snapshot` make the runner backend-agnostic.

Version 0 means "fresh / uninitialized". Version 1 is the initial v1 schema
and needs no migration on top of an empty store. Future schema changes append
a function to :data:`MIGRATIONS` and bump
:data:`~deckbridge.storage.schema.CURRENT_SCHEMA_VERSION`.
"""

from __future__ import annotations

from collections.abc import Callable

from deckbridge.logging_ import get_logger
from deckbridge.storage.base import Snapshot, Storage
from deckbridge.storage.schema import CURRENT_SCHEMA_VERSION

log = get_logger(__name__)


# Each entry maps a starting version to the function that migrates to the
# next version. The runner picks the chain starting at the persisted version.
#
# Example for a future change:
#     def _migrate_v1_to_v2(snap: Snapshot) -> Snapshot:
#         # transform fields...
#         return snap.model_copy(update={"schema_version": 2})
#
#     MIGRATIONS = {1: _migrate_v1_to_v2}

MIGRATIONS: dict[int, Callable[[Snapshot], Snapshot]] = {}


def run_migrations(storage: Storage) -> None:
    """Apply pending migrations in order, then stamp the new version.

    For brand-new stores (``schema_version == 0``) this just stamps the
    current version with no data transformations. For existing stores at an
    older version, it walks ``MIGRATIONS`` from current → target.
    """
    current = storage.schema_version()

    if current == CURRENT_SCHEMA_VERSION:
        return

    if current == 0:
        # Fresh store — just stamp the version.
        log.info("storage_initialized", version=CURRENT_SCHEMA_VERSION)
        storage.set_schema_version(CURRENT_SCHEMA_VERSION)
        return

    if current > CURRENT_SCHEMA_VERSION:
        raise RuntimeError(
            f"Storage is at schema version {current}, but this build of "
            f"DeckBridge only knows up to version {CURRENT_SCHEMA_VERSION}. "
            "Refusing to start to avoid corrupting your data."
        )

    snapshot = storage.export_snapshot()
    while current < CURRENT_SCHEMA_VERSION:
        migrate = MIGRATIONS.get(current)
        if migrate is None:
            raise RuntimeError(
                f"Missing migration step from schema version {current} to "
                f"{current + 1}. This is a bug — every gap in MIGRATIONS "
                "must be filled before bumping CURRENT_SCHEMA_VERSION."
            )
        log.info("storage_migrating", from_version=current, to_version=current + 1)
        snapshot = migrate(snapshot)
        current += 1

    storage.import_snapshot(snapshot)
    storage.set_schema_version(CURRENT_SCHEMA_VERSION)
    log.info("storage_migrations_complete", final_version=CURRENT_SCHEMA_VERSION)
