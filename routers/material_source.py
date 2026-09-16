"""Common Material Source API.

One shared API. Family-specific material endpoints are forbidden.
Classification is read-only from the authoritative master catalog.
This router is not wired into LEG diagnosis.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _ensure_factory_own
from services.material_source.projector import project_factory_material_rows
from services.material_source.registry import registry_public
from services.material_source.store import (
    MaterialSourceLoadError,
    MaterialSourceValidationError,
    catalog_index,
    create_factory_material,
    deactivate_factory_material,
    list_factory_materials,
    lookup_master_exact,
    master_with_classifications,
    update_factory_material,
)


def _unavailable(exc: MaterialSourceLoadError) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"code": "MATERIAL_SOURCE_UNAVAILABLE", "message": str(exc)},
    )


router = APIRouter(tags=["material-source"])


class FactoryMaterialBody(BaseModel):
    material_name: str
    material_category_code: Optional[str] = None
    handling_mode_codes: Optional[List[str]] = None
    material_master_key: Optional[str] = None
    is_active: bool = True


class FactoryMaterialPatch(BaseModel):
    material_name: Optional[str] = None
    material_category_code: Optional[str] = None
    handling_mode_codes: Optional[List[str]] = None
    material_master_key: Optional[str] = None
    is_active: Optional[bool] = None


def _payload(body: BaseModel) -> Dict[str, Any]:
    return body.model_dump(exclude_unset=True)


@router.get("/material-source/registry")
def get_material_source_registry(current: dict = Depends(get_current_user)):
    return {"status": "success", "data": registry_public()}


@router.get("/material-source/materials")
def get_material_source_materials(
    q: Optional[str] = None,
    current: dict = Depends(get_current_user),
):
    """Exact / deterministic master lookup. Empty q returns the full catalog."""
    rows = lookup_master_exact(q or "")
    return {
        "status": "success",
        "data": {
            "items": [master_with_classifications(row) for row in rows],
            "total": len(rows),
            "catalog_hash": catalog_index()["CATALOG_HASH"],
        },
    }


@router.get("/factories/{factory_id}/materials")
def get_factory_materials(
    factory_id: str,
    include_inactive: bool = False,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        items = list_factory_materials(
            supabase, factory_id, include_inactive=include_inactive
        )
    except MaterialSourceLoadError as exc:
        raise _unavailable(exc) from exc
    return {"status": "success", "data": {"items": items, "total": len(items)}}


@router.post("/factories/{factory_id}/materials")
def post_factory_material(
    factory_id: str,
    body: FactoryMaterialBody,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        row = create_factory_material(supabase, factory_id, _payload(body))
    except MaterialSourceValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "success", "data": row}


@router.patch("/factories/{factory_id}/materials/{material_id}")
def patch_factory_material(
    factory_id: str,
    material_id: str,
    body: FactoryMaterialPatch,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        row = update_factory_material(
            supabase, factory_id, material_id, _payload(body)
        )
    except MaterialSourceValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="사업장 물질을 찾을 수 없습니다.")
    return {"status": "success", "data": row}


@router.post("/factories/{factory_id}/materials/{material_id}/deactivate")
def deactivate_factory_material_route(
    factory_id: str,
    material_id: str,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        row = deactivate_factory_material(supabase, factory_id, material_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="사업장 물질을 찾을 수 없습니다.")
    return {"status": "success", "data": row}


@router.get("/factories/{factory_id}/materials/projection")
def get_factory_material_projection(
    factory_id: str,
    current: dict = Depends(get_current_user),
):
    """Source classification contract. Not a LEG boolean write path."""
    supabase = get_supabase()
    _ensure_factory_own(supabase, factory_id, current)
    try:
        items = list_factory_materials(supabase, factory_id, include_inactive=False)
    except MaterialSourceLoadError as exc:
        raise _unavailable(exc) from exc
    projected = project_factory_material_rows(items)
    return {
        "status": "success",
        "data": {
            "material_classifications": projected["material_classifications"],
            "source_count": len(items),
        },
    }
