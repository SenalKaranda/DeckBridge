"""HTTP routes for pages — the per-deck collections of keys.

    GET    /api/pages                     list all (optional ?deck_serial= filter)
    POST   /api/pages                     create (server generates the UUID)
    GET    /api/pages/{id}                fetch one
    PATCH  /api/pages/{id}                partial update (name, order, deck_serial)
    DELETE /api/pages/{id}                delete + cascade keys
    GET    /api/pages/{id}/keys           list every key on a page (sorted by slot)

All routes require authentication (session middleware). Keys CRUD lives in
``routes_keys.py`` to keep request shapes focused.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from deckbridge.events.types import KeyConfigChanged, PageConfigChanged
from deckbridge.http.auth import require_auth
from deckbridge.storage.schema import Key, Page

router = APIRouter(
    prefix="/api/pages",
    tags=["pages"],
    dependencies=[Depends(require_auth)],
)


# ---- request models ------------------------------------------------------


class CreatePageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deck_serial: str = Field(min_length=1)
    name: str = ""
    order: int = 0


class PatchPageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    order: int | None = None
    deck_serial: str | None = None


# ---- routes --------------------------------------------------------------


@router.get("", response_model=list[Page])
def list_pages(request: Request, deck_serial: str | None = None) -> list[Page]:
    return request.app.state.storage.list_pages(deck_serial=deck_serial)


@router.post("", response_model=Page, status_code=status.HTTP_201_CREATED)
async def create_page(payload: CreatePageRequest, request: Request) -> Page:
    page = Page(
        id=str(uuid.uuid4()),
        deck_serial=payload.deck_serial,
        name=payload.name,
        order=payload.order,
    )
    request.app.state.storage.upsert_page(page)
    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        # Wakes up the dispatcher so an attached deck without an active
        # page (the typical "deck plugged in before any pages exist"
        # case) picks up this newly-created page and the painter
        # immediately renders it.
        await bus.publish(PageConfigChanged(page_id=page.id, deck_serial=page.deck_serial))
    return page


@router.get("/{page_id}", response_model=Page)
def get_page(page_id: str, request: Request) -> Page:
    page = request.app.state.storage.get_page(page_id)
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "page not found")
    return page


@router.patch("/{page_id}", response_model=Page)
async def patch_page(page_id: str, payload: PatchPageRequest, request: Request) -> Page:
    storage = request.app.state.storage
    existing = storage.get_page(page_id)
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "page not found")

    update_dict = payload.model_dump(exclude_unset=True)
    if not update_dict:
        return existing  # nothing to change

    updated = existing.model_copy(update=update_dict)
    storage.upsert_page(updated)
    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        await bus.publish(PageConfigChanged(page_id=updated.id, deck_serial=updated.deck_serial))
    return updated


@router.delete("/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_page(page_id: str, request: Request) -> Response:
    storage = request.app.state.storage
    existing = storage.get_page(page_id)
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "page not found")
    deleted_deck_serial = existing.deck_serial

    # Capture which slots actually had keys before the cascade so we can fire
    # KeyConfigChanged for exactly those — keeps the painter from re-rendering
    # 30 empty slots after every page delete.
    affected_slots = [k.slot for k in storage.list_keys(page_id)]

    storage.delete_page(page_id)

    # Clear active-page entries pointing at the deleted page so the painter
    # stops trying to render keys that no longer exist.
    active_pages = getattr(request.app.state, "active_pages", None)
    if active_pages is not None:
        for serial, active_id in list(active_pages.all().items()):
            if active_id == page_id:
                active_pages.clear(serial)

    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        for slot in affected_slots:
            await bus.publish(KeyConfigChanged(page_id=page_id, slot=slot))
        # PageConfigChanged so the dispatcher picks a new active page for
        # any deck whose active page was the one we just deleted (the
        # active_pages.clear above leaves it in the "no active page" state).
        await bus.publish(PageConfigChanged(page_id=page_id, deck_serial=deleted_deck_serial))

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{page_id}/keys", response_model=list[Key])
def list_keys_for_page(page_id: str, request: Request) -> list[Key]:
    storage = request.app.state.storage
    if storage.get_page(page_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "page not found")
    return storage.list_keys(page_id)
