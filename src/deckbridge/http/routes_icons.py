"""HTTP routes for the icon library.

    GET    /api/icons               list all (bundled + uploaded)
    GET    /api/icons/{id}          metadata for one
    GET    /api/icons/{id}/raw      raw image bytes (PNG/JPEG)
    POST   /api/icons               upload a new image
    DELETE /api/icons/{id}          delete an uploaded image (404s on bundled)

Auth lands in M5; for M4 these are unauth so the editor scaffold can use
them. Don't expose the daemon to untrusted networks until then — see
README's security model section.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response

from deckbridge.icons.library import IconError, IconLibrary
from deckbridge.storage.schema import Icon

if TYPE_CHECKING:
    pass

router = APIRouter(prefix="/api/icons", tags=["icons"])


def _library(request: Request) -> IconLibrary:
    """Resolve the IconLibrary set on app.state during lifespan startup."""
    library = getattr(request.app.state, "icon_library", None)
    if library is None:
        raise HTTPException(
            status_code=500,
            detail="Icon library not initialized; check daemon startup logs.",
        )
    return library


@router.get("", response_model=list[Icon])
def list_icons(request: Request) -> list[Icon]:
    return request.app.state.storage.list_icons()


@router.get("/{icon_id}", response_model=Icon)
def get_icon(icon_id: str, request: Request) -> Icon:
    icon = request.app.state.storage.get_icon(icon_id)
    if icon is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "icon not found")
    return icon


@router.get("/{icon_id}/raw")
def get_icon_raw(icon_id: str, request: Request) -> Response:
    library = _library(request)
    raw = library.get_bytes(icon_id)
    if raw is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "icon not found")
    icon = request.app.state.storage.get_icon(icon_id)
    media_type = "image/png"
    if icon is not None and icon.reference.endswith(".jpg"):
        media_type = "image/jpeg"
    return Response(content=raw, media_type=media_type)


@router.post("", response_model=Icon, status_code=status.HTTP_201_CREATED)
async def upload_icon(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(default=""),
) -> Icon:
    library = _library(request)
    raw = await file.read()
    try:
        icon = library.upload(
            name=name or (file.filename or ""),
            content_type=file.content_type or "application/octet-stream",
            raw=raw,
        )
    except IconError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return icon


@router.delete("/{icon_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_icon(icon_id: str, request: Request) -> Response:
    library = _library(request)
    icon = request.app.state.storage.get_icon(icon_id)
    if icon is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "icon not found")
    try:
        library.delete(icon_id)
    except IconError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
