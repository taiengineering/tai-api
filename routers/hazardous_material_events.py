"""Hazardous material in/out event management API.

All endpoints require authenticated user + factory ownership.
Hard delete = 0. Status lifecycle: DRAFT → CONFIRMED → VOID.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _ensure_factory_own
from services.hazardous_material_event_source.store import (
    HazardousMaterialEventSourceLoadError,
    HazardousMaterialEventValidationError,
    confirm_event,
    create_event_draft,
    list_factory_events,
    update_event_draft,
    void_event,
)


def _source_unavailable(exc: HazardousMaterialEventSourceLoadError) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"code": "HAZARDOUS_MATERIAL_EVENT_SOURCE_UNAVAILABLE", "message": str(exc)},
    )


router = APIRouter(tags=["hazardous-material-events"])


class EventDraftBody(BaseModel):
    event_direction: str
    occurred_at: Optional[str] = None
    purpose: Optional[str] = None
    material_type: Optional[str] = None
    quantity: Optional[float] = None
    quantity_unit: Optional[str] = None
    material_use: Optional[str] = None
    purchase_source: Optional[str] = None
    carrier_name: Optional[str] = None
    responsible_person_name: Optional[str] = None
    vehicle_type: Optional[str] = None


class EventDraftPatch(BaseModel):
    event_direction: Optional[str] = None
    occurred_at: Optional[str] = None
    purpose: Optional[str] = None
    material_type: Optional[str] = None
    quantity: Optional[float] = None
    quantity_unit: Optional[str] = None
    material_use: Optional[str] = None
    purchase_source: Optional[str] = None
    carrier_name: Optional[str] = None
    responsible_person_name: Optional[str] = None
    vehicle_type: Optional[str] = None


@router.get("/factories/{factory_id}/hazardous-material-events")
def list_events(
    factory_id: str,
    status: Optional[str] = None,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        rows = list_factory_events(supabase, factory_id=factory_id, status=status)
    except HazardousMaterialEventSourceLoadError as exc:
        raise _source_unavailable(exc)
    return {"events": rows}


@router.post("/factories/{factory_id}/hazardous-material-events", status_code=201)
def create_draft(
    factory_id: str,
    body: EventDraftBody,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        row = create_event_draft(
            supabase,
            factory_id=factory_id,
            event_direction=body.event_direction,
            occurred_at=body.occurred_at,
            purpose=body.purpose,
            material_type=body.material_type,
            quantity=body.quantity,
            quantity_unit=body.quantity_unit,
            material_use=body.material_use,
            purchase_source=body.purchase_source,
            carrier_name=body.carrier_name,
            responsible_person_name=body.responsible_person_name,
            vehicle_type=body.vehicle_type,
        )
    except HazardousMaterialEventValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except HazardousMaterialEventSourceLoadError as exc:
        raise _source_unavailable(exc)
    return row


@router.patch("/factories/{factory_id}/hazardous-material-events/{event_id}")
def patch_draft(
    factory_id: str,
    event_id: str,
    body: EventDraftPatch,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=422, detail="No fields to update")
    try:
        row = update_event_draft(supabase, factory_id=factory_id, event_id=event_id, patch=patch)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except HazardousMaterialEventValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except HazardousMaterialEventSourceLoadError as exc:
        raise _source_unavailable(exc)
    return row


@router.post("/factories/{factory_id}/hazardous-material-events/{event_id}/confirm")
def confirm(
    factory_id: str,
    event_id: str,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        row = confirm_event(supabase, factory_id=factory_id, event_id=event_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except HazardousMaterialEventValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except HazardousMaterialEventSourceLoadError as exc:
        raise _source_unavailable(exc)
    return row


@router.post("/factories/{factory_id}/hazardous-material-events/{event_id}/void")
def void(
    factory_id: str,
    event_id: str,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        row = void_event(supabase, factory_id=factory_id, event_id=event_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except HazardousMaterialEventValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except HazardousMaterialEventSourceLoadError as exc:
        raise _source_unavailable(exc)
    return row
