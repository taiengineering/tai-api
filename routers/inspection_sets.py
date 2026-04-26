"""법정점검 세트 라우터 (서비스 호출 전용)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from schemas.inspection_sets import (
    AnchorBody,
    AnchorBulkPatchBody,
    BulkAnchorBody,
    InspectionSetPatchBody,
    ManualInspectionSetBody,
)
from services import inspection_sets_svc as svc

router = APIRouter(prefix="/inspection-sets", tags=["inspection_sets"])


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except svc.InspectionSetsSvcError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e


@router.get("")
def get_inspection_sets(
    factory_id: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    anchor_confirmed: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
):
    return _call(svc.get_sets_list, factory_id, source, anchor_confirmed, page, size)


@router.post("/manual")
def create_manual_inspection_set(body: ManualInspectionSetBody):
    return _call(svc.create_manual_set, body)


@router.get("/preview-schedule")
def preview_schedule(factory_id: str = Query(...), months: int = Query(3, ge=1, le=12)):
    return _call(svc.get_preview_schedule, factory_id, months)


@router.post("/anchor/bulk")
def set_anchor_bulk(body: BulkAnchorBody):
    return _call(svc.set_anchor_bulk, body)


@router.patch("/anchor/bulk")
def bulk_update_anchor(body: AnchorBulkPatchBody):
    return _call(svc.bulk_update_anchors, body)


@router.post("/generate-all-items")
def generate_all_items(factory_id: Optional[str] = Query(None), dry_run: bool = Query(False)):
    return _call(svc.generate_all_items, factory_id, dry_run)


@router.post("/generate-schedules-all")
def generate_schedules_all():
    return _call(svc.generate_schedules_all)


@router.post("/generate-schedules/{factory_id}")
def generate_schedules_for_factory(
    factory_id: str,
    mode: str = Query("law_engine", description="'law_engine'(4조건) 또는 'anchor'(anchor_confirmed 기반)"),
    force: bool = Query(False, description="anchor 모드에서 기존 SCHEDULED 삭제 후 재생성"),
):
    return _call(svc.generate_schedules_for_factory, factory_id, mode, force)


@router.patch("/{inspection_set_id}")
def patch_inspection_set(inspection_set_id: str, body: InspectionSetPatchBody):
    return _call(svc.patch_set, inspection_set_id, body)


@router.patch("/{inspection_set_id}/anchor")
def update_inspection_anchor(inspection_set_id: str, body: AnchorBody):
    return _call(svc.update_anchor, inspection_set_id, body)


@router.post("/{inspection_set_id}/generate-items")
def generate_items(inspection_set_id: str):
    return _call(svc.generate_items_for_set, inspection_set_id)


@router.get("/company/{company_id}")
def get_company_inspection_sets(company_id: str):
    return _call(svc.get_company_sets, company_id)


@router.get("/factory/{factory_id}")
def get_factory_inspection_sets(factory_id: str):
    return _call(svc.get_factory_sets, factory_id)


@router.get("/{inspection_set_id}")
def get_inspection_set(inspection_set_id: str):
    return _call(svc.get_set_by_id, inspection_set_id)
