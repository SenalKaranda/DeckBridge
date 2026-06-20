"""Serve the built SvelteKit SPA from the FastAPI app.

The SPA lives at :mod:`deckbridge.web_dist` (populated by ``npm run build``
in the ``web/`` directory). For SPA-style routing, any unmatched non-API
path returns ``index.html`` so client-side routing handles the route.

In development, the frontend is normally served by ``vite dev`` on its own
port and ``npm run dev`` proxies ``/api/*`` back to this daemon. In that
mode the SPA mount here is unused but harmless.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

import deckbridge
from deckbridge.logging_ import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.responses import Response
    from starlette.types import Scope

log = get_logger(__name__)


class SPAStaticFiles(StaticFiles):
    """StaticFiles that falls back to ``index.html`` on 404.

    This is the canonical pattern for hosting an SPA: the server returns the
    built ``index.html`` for any unknown path, and the client-side router
    decides what to render based on ``window.location``.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


def _resolve_web_dist() -> Path | None:
    """Locate the built SPA on disk, or return None if it has not been built.

    Uses the package's own ``__file__`` to find the filesystem location. This
    works for both editable installs (``src/deckbridge/web_dist``) and wheel
    installs (``site-packages/deckbridge/web_dist``). Avoids
    :func:`importlib.resources.as_file`, which on zipped installs yields a
    temp directory that is cleaned up on context exit — useless for a
    long-lived static-file mount.
    """
    if deckbridge.__file__ is None:
        return None
    web_dist = Path(deckbridge.__file__).parent / "web_dist"
    if not web_dist.is_dir():
        return None
    if not (web_dist / "index.html").is_file():
        return None
    return web_dist


def mount_spa(app: FastAPI) -> None:
    """Mount the built SPA at ``/`` if its assets are present.

    Idempotent: if the SPA hasn't been built yet (greenfield dev install),
    log a warning and skip — the API still works for tests and curl.
    """
    web_dist = _resolve_web_dist()
    if web_dist is None:
        log.warning(
            "spa_not_mounted",
            reason="no_index_html",
            hint="run `npm run build` in web/ to populate src/deckbridge/web_dist",
        )
        return
    app.mount(
        "/",
        SPAStaticFiles(directory=str(web_dist), html=True),
        name="spa",
    )
    log.info("spa_mounted", path=str(web_dist))
