"""
엔진 설비 마스터 관리 라우터 — v4.5.0
v4.5.0: SEC-03 인증·인가 보강 (WO-TAI-SEC03-ENGINE-EQUIPMENT-AUTH-P0-IMPLEMENT-001)
  - EE-01~EE-11 전 엔드포인트 Depends(get_current_user) 추가
  - EE-12 /categories 공개 유지
  - EE-01/05/07/08/11: ALL 전용 (_require_admin)
  - EE-02: 회사·사업장 범위 제한
  - EE-03: EQUIPMENT_UPDATE + 자산 소유권 검증
v4.4.0: 수리 완료 후 anchor 재설정
  - PATCH /assets/{asset_id}: is_operating + repair_date 필드 추가
    - is_operating=false: 설비만 업데이트, work_schedules 건드리지 않음
    - is_operating=true + repair_date: factory의 MANUAL ACTIVE inspection_sets 재생성
v4.3.3: assets-list 응답을 data.items 형태로 통일
v4.3.2: stats 확장 + GET /assets-list + PATCH /assets/{asset_id}
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import date
from dateutil.relativedelta import relativedelta
from db.supabase_client import get_supabase
from routers.auth import get_current_user
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

VERSION = "4.5.0"

# ───────────────────────────────────────────────────
# GET /engine-equipment/stats  — ALL 전용
# ───────────────────────────────────────────────────
@router.get("/stats")
async def get_equipment_stats(current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    try:
        return equipment_engine_svc.run_get_equipment_stats(supabase, VERSION, current)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ───────────────────────────────────────────────────
# GET /engine-equipment/assets-list  — 회사·사업장 범위 제한
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
    current:             dict          = Depends(get_current_user),
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
            current=current,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ───────────────────────────────────────────────────
# PATCH /engine-equipment/assets/{asset_id}  v4.5.0
# ───────────────────────────────────────────────────
@router.patch("/assets/{asset_id}")
async def patch_asset(
    asset_id: str,
    body: AssetPatchBody,
    current: dict = Depends(get_current_user),
):
    """
    v4.5.0: EQUIPMENT_UPDATE 작업권한 + 자산 소유권 검증 추가.
    v4.4.0: is_operating + repair_date 수리완료 로직.
    - is_operating=False: 설비만 업데이트, work_schedules 건드리지 않음
    - is_operating=True + repair_date: factory의 MANUAL ACTIVE inspection_sets
      SCHEDULED 일정 삭제 후 repair_date 기준 1년치 재생성
    """
    supabase = get_supabase()
    try:
        return equipment_engine_svc.run_patch_asset(
            supabase=supabase, asset_id=asset_id, body=body, current=current
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ───────────────────────────────────────────────────
# GET /engine-equipment/list  — 인증 필수
# ───────────────────────────────────────────────────
@router.get("/list")
async def list_equipment_master(
    search:       Optional[str]  = Query(None),
    category:     Optional[str]  = Query(None),
    top_band:     Optional[str]  = Query(None),
    needs_review: Optional[bool] = Query(None),
    page:         int = Query(1, ge=1),
    page_size:    int = Query(50, ge=1, le=200),
    current:      dict = Depends(get_current_user),
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


# ───────────────────────────────────────────────────
# POST /engine-equipment/refresh  — ALL 전용
# ───────────────────────────────────────────────────
@router.post("/refresh")
async def refresh_engine_equipment(current: dict = Depends(get_current_user)):
    supabase = get_supabase()
    try:
        return equipment_catalog_svc.run_refresh_engine_equipment(supabase, current)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ───────────────────────────────────────────────────
# GET /engine-equipment/detail/{facility_name}  — 인증 필수
# ───────────────────────────────────────────────────
@router.get("/detail/{facility_name}")
async def get_equipment_detail(
    facility_name: str,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    try:
        return equipment_catalog_svc.run_get_equipment_detail(supabase, facility_name)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ───────────────────────────────────────────────────
# PATCH /engine-equipment/update/{facility_name}  — ALL 전용
# ───────────────────────────────────────────────────
@router.patch("/update/{facility_name}")
async def update_equipment_master(
    facility_name: str,
    body: dict,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    try:
        return equipment_catalog_svc.run_update_equipment_master(
            supabase, facility_name, body, current
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ───────────────────────────────────────────────────
# POST /engine-equipment/review/approve  — ALL 전용
# ───────────────────────────────────────────────────
@router.post("/review/approve")
async def bulk_approve_review(
    body: dict,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    try:
        return equipment_catalog_svc.run_bulk_approve_review(supabase, body, current)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ───────────────────────────────────────────────────
# GET /engine-equipment/models  — 인증 필수
# ───────────────────────────────────────────────────
@router.get("/models")
async def list_equipment_models(
    search:        Optional[str] = Query(None),
    equipment_std: Optional[str] = Query(None),
    manufacturer:  Optional[str] = Query(None),
    source_type:   Optional[str] = Query(None),
    page:          int = Query(1, ge=1),
    page_size:     int = Query(30, ge=1, le=100),
    current:       dict = Depends(get_current_user),
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


# ───────────────────────────────────────────────────
# GET /engine-equipment/models/{model_id}  — 인증 필수
# ───────────────────────────────────────────────────
@router.get("/models/{model_id}")
async def get_model_detail(
    model_id: str,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    try:
        return equipment_catalog_svc.run_get_model_detail(supabase, model_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ───────────────────────────────────────────────────
# PATCH /engine-equipment/models/{model_id}  — ALL 전용
# ───────────────────────────────────────────────────
@router.patch("/models/{model_id}")
async def update_model(
    model_id: str,
    body: dict,
    current: dict = Depends(get_current_user),
):
    supabase = get_supabase()
    try:
        return equipment_catalog_svc.run_update_model(supabase, model_id, body, current)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ───────────────────────────────────────────────────
# GET /engine-equipment/categories  — 공개 (정적 데이터)
# ───────────────────────────────────────────────────
@router.get("/categories")
async def get_categories():
    return {"status": "success", "data": [{"code": k, "label": v} for k, v in CATEGORY_MAP.items()]}
