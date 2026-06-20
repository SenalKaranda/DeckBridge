"""HTTP routes for keys — slot-addressable per-page key configurations.

    GET    /api/pages/{page_id}/keys/{slot}             fetch one key
    PUT    /api/pages/{page_id}/keys/{slot}             upsert the key (full body)
    DELETE /api/pages/{page_id}/keys/{slot}             clear the slot
    POST   /api/pages/{page_id}/keys/{slot}/test-press  fire the configured
                                                        action without a
                                                        physical press

Key identity is composite ``(page_id, slot)``; the URL encodes both.

PUT and DELETE publish :class:`~deckbridge.events.KeyConfigChanged` so the
painter invalidates its cache and re-renders, and the state subscriber
re-evaluates which topics it should listen on.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from deckbridge.events.types import KeyConfigChanged
from deckbridge.http.auth import require_auth
from deckbridge.storage.schema import Key, NoOpAction, PressAction, StateSubscription

router = APIRouter(
    prefix="/api/pages",
    tags=["keys"],
    dependencies=[Depends(require_auth)],
)


# ---- request body --------------------------------------------------------


class KeyBody(BaseModel):
    """The configurable parts of a Key. ``page_id`` and ``slot`` come from the URL.

    Mirror the field set of :class:`Key` exactly (minus the URL-derived fields)
    so adding a field to the storage schema doesn't silently drop on save. The
    PUT handler forwards via ``**payload.model_dump()`` for the same reason —
    no hand-listed fields means no drift between the two models.
    """

    model_config = ConfigDict(extra="forbid")

    label: str = ""
    icon_id: str | None = None
    press: PressAction = Field(default_factory=NoOpAction)
    state: StateSubscription | None = None
    padding: int = 0
    show_icon: bool = True
    show_label: bool = True
    bg_color: str = "#000000"
    bg_image_id: str | None = None
    label_color: str = "#FFFFFF"
    icon_color: str | None = None
    font_size: int = 14


# ---- routes --------------------------------------------------------------


@router.get("/{page_id}/keys/{slot}", response_model=Key)
def get_key(page_id: str, slot: int, request: Request) -> Key:
    storage = request.app.state.storage
    if storage.get_page(page_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "page not found")
    key = storage.get_key(page_id, slot)
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "key not found")
    return key


@router.put("/{page_id}/keys/{slot}", response_model=Key)
async def put_key(page_id: str, slot: int, payload: KeyBody, request: Request) -> Key:
    storage = request.app.state.storage
    if storage.get_page(page_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "page not found")
    if not 0 <= slot <= 31:
        # Pydantic validates this on the schema too; explicit guard avoids
        # surfacing a 500 from the DB driver if a path-level int slips past.
        # Newer Starlette renamed the constant; fall back for older releases.
        code = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)
        raise HTTPException(code, "slot out of range")

    # Forward every body field through model_dump() instead of hand-listing,
    # so any new field added to KeyBody automatically reaches the Key
    # constructor without a second edit here. Pydantic re-validates on the
    # Key side (range/pattern/discriminator).
    key = Key(page_id=page_id, slot=slot, **payload.model_dump())
    storage.upsert_key(key)
    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        await bus.publish(KeyConfigChanged(page_id=page_id, slot=slot))
    return key


@router.delete("/{page_id}/keys/{slot}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_key(page_id: str, slot: int, request: Request) -> Response:
    storage = request.app.state.storage
    if storage.get_key(page_id, slot) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "key not found")
    storage.delete_key(page_id, slot)
    bus = getattr(request.app.state, "bus", None)
    if bus is not None:
        await bus.publish(KeyConfigChanged(page_id=page_id, slot=slot))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- test-press ----------------------------------------------------------


class TestPressResponse(BaseModel):
    """Returned by the test-press endpoint after the action ran (or failed)."""

    ok: bool
    deck_serial: str
    action_type: str


@router.post(
    "/{page_id}/keys/{slot}/test-press",
    response_model=TestPressResponse,
)
async def fire_test_press(
    page_id: str,
    slot: int,
    request: Request,
    deck_serial: str | None = None,
) -> TestPressResponse:
    """Fire the configured press action without a physical key press.

    Useful for the editor's "Test" button. The deck serial is taken from
    ``?deck_serial=...`` if provided; otherwise we use the first attached
    deck, or fall back to the literal ``"default"`` (matching the editor's
    pre-deck-attached flow). MQTT publishes / HTTP webhooks fire as if the
    user pressed the physical button; page-switches update the in-memory
    active page for the resolved serial and the painter re-renders.
    """
    storage = request.app.state.storage
    if storage.get_page(page_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "page not found")
    key = storage.get_key(page_id, slot)
    if key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "key not found")

    dispatcher = getattr(request.app.state, "press_dispatcher", None)
    if dispatcher is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "press dispatcher not initialized")

    # Resolve the deck serial:
    #   1. explicit query param wins
    #   2. else first attached deck (DeckManager.decks)
    #   3. else "default" (editor-without-deck flow)
    resolved = deck_serial
    if resolved is None:
        deck_manager = getattr(request.app.state, "deck_manager", None)
        if deck_manager is not None:
            attached = list(deck_manager.decks.values())
            if attached:
                resolved = attached[0].serial
    if resolved is None:
        resolved = "default"

    await dispatcher.execute(resolved, key.press)
    return TestPressResponse(ok=True, deck_serial=resolved, action_type=key.press.type)
