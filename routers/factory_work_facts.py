"""Common Work Source CRUD.

One shared API. Family-specific endpoints are forbidden.
Client may not store canonical LEG booleans.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _ensure_factory_own
from services.work_source.merge import WorkSourceMergeConflict, merge_or_raise
from services.work_source.registry import registry_public
from services.work_source.store import (
    WorkSourceLoadError,
    WorkSourceValidationError,
    create_work_fact,
    deactivate_work_fact,
    list_work_facts,
    update_work_fact,
)


def _unavailable(exc: WorkSourceLoadError) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"code": "WORK_SOURCE_UNAVAILABLE", "message": str(exc)},
    )


router = APIRouter(tags=["factory-work-facts"])


class WorkFactBody(BaseModel):
    work_type: str
    work_subtype: Optional[str] = None
    equipment_ref: Optional[str] = None
    material_ref: Optional[str] = None
    location_ref: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class WorkFactPatch(BaseModel):
    work_type: Optional[str] = None
    work_subtype: Optional[str] = None
    equipment_ref: Optional[str] = None
    material_ref: Optional[str] = None
    location_ref: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    active: Optional[bool] = None


def _payload(body: BaseModel) -> Dict[str, Any]:
    return body.model_dump(exclude_unset=True)


@router.get("/work-source/registry")
def get_work_source_registry(current: dict = Depends(get_current_user)):
    return {"status": "success", "data": registry_public()}


@router.get("/factories/{factory_id}/work-facts")
def get_factory_work_facts(
    factory_id: str,
    include_inactive: bool = False,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        items = list_work_facts(supabase, factory_id, include_inactive=include_inactive)
    except WorkSourceLoadError as exc:
        raise _unavailable(exc) from exc
    return {"status": "success", "data": {"items": items, "total": len(items)}}


@router.post("/factories/{factory_id}/work-facts")
def post_factory_work_fact(
    factory_id: str,
    body: WorkFactBody,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        row = create_work_fact(supabase, factory_id, _payload(body))
    except WorkSourceValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "success", "data": row}


@router.patch("/factories/{factory_id}/work-facts/{fact_id}")
def patch_factory_work_fact(
    factory_id: str,
    fact_id: str,
    body: WorkFactPatch,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        row = update_work_fact(supabase, factory_id, fact_id, _payload(body))
    except WorkSourceValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="작업 사실을 찾을 수 없습니다.")
    return {"status": "success", "data": row}


@router.post("/factories/{factory_id}/work-facts/{fact_id}/deactivate")
def deactivate_factory_work_fact(
    factory_id: str,
    fact_id: str,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        row = deactivate_work_fact(supabase, factory_id, fact_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="작업 사실을 찾을 수 없습니다.")
    return {"status": "success", "data": row}


@router.get("/factories/{factory_id}/work-facts/projection")
def get_factory_work_projection(
    factory_id: str,
    current: dict = Depends(get_current_user),
):
    """Projector output for operators. Not a client write path for LEG booleans."""
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        items = list_work_facts(supabase, factory_id, include_inactive=False)
    except WorkSourceLoadError as exc:
        raise _unavailable(exc) from exc
    try:
        facts = merge_or_raise({}, items)
    except WorkSourceMergeConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "WORK_SOURCE_CONFLICT", "conflicts": exc.conflicts},
        ) from exc
    return {"status": "success", "data": {"facts": facts, "source_count": len(items)}}
