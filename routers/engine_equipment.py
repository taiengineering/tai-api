"""
엔진 설비 마스터 관리 라우터 — v4.4.0
v4.4.0: 수리 완료 후 anchor 재설정
  - PATCH /assets/{asset_id}: is_operating + repair_date 필드 추가
    - is_operating=false: 설비만 업데이트, work_schedules 건드리지 않음
    - is_operating=true + repair_date: factory의 MANUAL ACTIVE inspection_sets 재생성
v4.3.3: assets-list 응답을 data.items 형태로 통일
v4.3.2: stats 확장 + GET /assets-list + PATCH /assets/{asset_id}
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import date
from dateutil.relativedelta import relativedelta
from db.supabase_client import get_supabase
from schemas.engine_equipment import AssetPatchBody
from services import equipment_engine_svc
from services import equipment_catalog_svc
from services.equipment_helpers import (
    CATEGORY_MAP,
    DELTA_MAP,
    REPEAT_TYPE_MAP,
    _build_schedules_for_repair,
    _enrich_asset_row,
    _now_iso,
)

router = APIRouter(prefix="/engine-equipment", tags=["엔진설비마스터"])

VERSION = "4.4.0"

# ───────────────────────────────────────────────────
# GET /engine-equipment/stats
# ───────────────────────────────────────────────────
@router.get("/stats")
async def get_equipment_stats():
    supabase = get_supabase()
    try:
        return equipment_engine_svc.run_get_equipment_stats(supabase, VERSION)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ───────────────────────────────────────────────────
# GET /engine-equipment/assets-list
# ───────────────────────────────────────────────────
@router.get("/assets-list")
async def list_assets(
    page:                int           = Query(1, ge=1),
    page_size:           int           = Query(50, ge=1, le=5000),
    search:              Optional[str] = Query(None),
    has_model:           Optional[bool] = Query(None),
    no_inspection:       Optional[bool] = Query(None),
    is_legal_target:     Optional[bool] = Query(None),
    equipment_type_code: Optional[str] = Query(None),
):
    supabase = get_supabase()
    try:
        return equipment_engine_svc.run_list_assets(
            supabase=supabase,
            page=page,
            page_size=page_size,
            search=search,
            has_model=has_model,
            no_inspection=no_inspection,
            is_legal_target=is_legal_target,
            equipment_type_code=equipment_type_code,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ───────────────────────────────────────────────────
# PATCH /engine-equipment/assets/{asset_id}  v4.4.0
# ───────────────────────────────────────────────────
@router.patch("/assets/{asset_id}")
async def patch_asset(asset_id: str, body: AssetPatchBody):
    """
    v4.4.0: is_operating + repair_date 수리완료 로직 추가.
    - is_operating=False: 설비만 업데이트, work_schedules 건드리지 않음
    - is_operating=True + repair_date: factory의 MANUAL ACTIVE inspection_sets
      SCHEDULED 일정 삭제 훈 repair_date 기준 1년치 재생성
    """
    supabase = get_supabase()
    try:
        return equipment_engine_svc.run_patch_asset(supabase=supabase, asset_id=asset_id, body=body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ───────────────────────────────────────────────────
# GET /engine-equipment/list
# ───────────────────────────────────────────────────
@router.get("/list")
async def list_equipment_master(
    search:       Optional[str]  = Query(None),
    category:     Optional[str]  = Query(None),
    top_band:     Optional[str]  = Query(None),
    needs_review: Optional[bool] = Query(None),
    page:         int = Query(1, ge=1),
    page_size:    int = Query(50, ge=1, le=200),
):
    supabase = get_supabase()
    try:
        return equipment_catalog_svc.run_list_equipment_master(
            supabase=supabase,
            search=search,
            category=category,
            top_band=top_band,
            needs_review=needs_review,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh")
async def refresh_engine_equipment():
    supabase = get_supabase()
    try:
        return equipment_catalog_svc.run_refresh_engine_equipment(supabase)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/detail/{facility_name}")
async def get_equipment_detail(facility_name: str):
    supabase = get_supabase()
    try:
        return equipment_catalog_svc.run_get_equipment_detail(supabase, facility_name)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/update/{facility_name}")
async def update_equipment_master(facility_name: str, body: dict):
    supabase = get_supabase()
    try:
        return equipment_catalog_svc.run_update_equipment_master(supabase, facility_name, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/review/approve")
async def bulk_approve_review(body: dict):
    supabase = get_supabase()
    try:
        return equipment_catalog_svc.run_bulk_approve_review(supabase, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/models")
async def list_equipment_models(
    search:        Optional[str] = Query(None),
    equipment_std: Optional[str] = Query(None),
    manufacturer:  Optional[str] = Query(None),
    source_type:   Optional[str] = Query(None),
    page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
):
    supabase = get_supabase()
    return equipment_catalog_svc.run_list_equipment_models(
        supabase=supabase,
        search=search,
        equipment_std=equipment_std,
        manufacturer=manufacturer,
        source_type=source_type,
        page=page,
        page_size=page_size,
    )


@router.get("/models/{model_id}")
async def get_model_detail(model_id: str):
    supabase = get_supabase()
    try:
        return equipment_catalog_svc.run_get_model_detail(supabase, model_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/models/{model_id}")
async def update_model(model_id: str, body: dict):
    supabase = get_supabase()
    try:
        return equipment_catalog_svc.run_update_model(supabase, model_id, body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/categories")
async def get_categories():
    return {"status": "success", "data": [{"code": k, "label": v} for k, v in CATEGORY_MAP.items()]}
