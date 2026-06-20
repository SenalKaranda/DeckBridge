"""Config export / import endpoints (M8b).

Two endpoints that round-trip the entire :class:`Snapshot` (decks, pages,
keys, icons metadata, preferences sans secrets) as a single JSON document.
Useful for backup, moving a config to a new install, or reproducing a bug
report.

    POST /api/config/export    -> returns the snapshot JSON (auth)
    POST /api/config/import    -> replaces all stored config (auth)

Note: uploaded icon BYTES are NOT included in the snapshot. The icon
metadata records (id/name/source/reference) are exported, but if you
restore on a fresh install the uploaded PNGs themselves will be missing
on disk and the painter will render blanks until the user re-uploads.
Bundled-icon references (lucide:*) round-trip cleanly. This is documented
in :doc:`docs/configuration.md`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError

from deckbridge.http.auth import require_auth
from deckbridge.storage.base import Snapshot

router = APIRouter(
    prefix="/api/config",
    tags=["config"],
    dependencies=[Depends(require_auth)],
)


@router.post("/export", response_model=Snapshot)
def export_config(request: Request) -> Snapshot:
    """Return the full storage snapshot as JSON.

    Sensitive fields (password hash, API token hash) are part of Preferences
    and ARE included in the export. Treat the returned document as a secret.
    The frontend's "Download" button hands the user a file; they're
    responsible for keeping it safe.
    """
    return request.app.state.storage.export_snapshot()


@router.post("/import", response_model=Snapshot)
def import_config(payload: Snapshot, request: Request) -> Snapshot:
    """Replace the stored config with the supplied snapshot.

    Uses Pydantic for shape validation; bad payloads return 422 from
    FastAPI's request-body machinery. After import, the storage's
    schema_version is set from the supplied value (or current default).
    """
    storage = request.app.state.storage
    try:
        storage.import_snapshot(payload)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return storage.export_snapshot()
