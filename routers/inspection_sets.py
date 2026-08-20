"""법정점검 세트 라우터 (서비스 호출 전용).

인증·회사 스코프 (Wave3, 직접MCP · 방식 A=라우터 가드):
  - 전 엔드포인트 로그인 필수(get_current_user).
  - factory 직결(list·preview·manual·anchor/bulk·generate-schedules/{factory_id}·factory/{id})
    → _ensure_factory_own.
  - set 단건(patch·anchor·generate-items·{id}·{id}/items) → _ensure_set_own(행 company_id).
  - set 배치(anchor/bulk PATCH) → _ensure_sets_own(items[].id).
  - company/{company_id} → _ensure_own_company(path 값 토큰 대조, 타사 404).
  - 전사 batch(generate-all-items 무 factory_id · generate-schedules-all) → _require_admin(ALL 전용).
  - list(GET "") 무 factory_id → 회사 스코프(§4, 방식 B): scoped_list_company 로
    비-ALL=자사 전체·ALL=전사·무회사=빈결과. svc.get_sets_list(company_id, deny_all) 가산.
  svc 패키지는 get_sets_list 에 company_id/deny_all 파라미터 ADDITIVE 가산(나머지 무수정).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import (
    _scope,
    _is_admin,
    _require_admin,
    _ensure_own_company,
    _ensure_factory_own,
    scoped_list_company,
)
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


# ── 회사 스코프 가드 (P13, 라우터 가드 방식 A) ──

def _ensure_set_own(sb, inspection_set_id, current):
    """inspection_set 소유확인(행 company_id 경유). 없으면/타사면 404."""
    r = sb.table("inspection_sets").select("id, company_id").eq("id", inspection_set_id).limit(1).execute()
    if not r.data:
        raise HTTPException(status_code=404, detail="점검 세트를 찾을 수 없습니다.")
    _ensure_own_company(r.data[0].get("company_id"), current, sb, "점검 세트를 찾을 수 없습니다.")


def _ensure_sets_own(sb, set_ids, current):
    """set id 목록 일괄 소유확인. ALL 은 통과, 비-ALL 은 하나라도 타사면 404."""
    if _is_admin(_scope(sb, current.get("role_code"))):
        return
    ids = [sid for sid in (set_ids or []) if sid]
    if not ids:
        return
    r = sb.table("inspection_sets").select("id, company_id").in_("id", ids).execute()
    cid = current.get("company_id")
    if not cid:
        raise HTTPException(status_code=404, detail="점검 세트를 찾을 수 없습니다.")
    for row in (r.data or []):
        if row.get("company_id") != cid:
            raise HTTPException(status_code=404, detail="점검 세트를 찾을 수 없습니다.")


@router.get("")
def get_inspection_sets(
    factory_id: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    anchor_confirmed: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    current: dict = Depends(get_current_user),
):
    sb = get_supabase()
    if factory_id:
        _ensure_factory_own(sb, factory_id, current)
        return _call(svc.get_sets_list, factory_id, source, anchor_confirmed, page, size)
    # 무 factory_id: 회사 스코프(§4) — 비-ALL=자사 전체, ALL=전사, 무회사=빈결과
    scoped_cid, deny_all = scoped_list_company(current, sb)
    return _call(svc.get_sets_list, factory_id, source, anchor_confirmed, page, size, scoped_cid, deny_all)


@router.post("/manual")
def create_manual_inspection_set(body: ManualInspectionSetBody, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _ensure_factory_own(sb, body.factory_id, current)
    return _call(svc.create_manual_set, body)


@router.get("/preview-schedule")
def preview_schedule(
    factory_id: str = Query(...),
    months: int = Query(3, ge=1, le=12),
    current: dict = Depends(get_current_user),
):
    sb = get_supabase()
    _ensure_factory_own(sb, factory_id, current)
    return _call(svc.get_preview_schedule, factory_id, months)


@router.post("/anchor/bulk")
def set_anchor_bulk(body: BulkAnchorBody, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _ensure_factory_own(sb, body.factory_id, current)
    return _call(svc.set_anchor_bulk, body)


@router.patch("/anchor/bulk")
def bulk_update_anchor(body: AnchorBulkPatchBody, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _ensure_sets_own(sb, [it.id for it in (body.items or [])], current)
    return _call(svc.bulk_update_anchors, body)


@router.post("/generate-all-items")
def generate_all_items(
    factory_id: Optional[str] = Query(None),
    dry_run: bool = Query(False),
    current: dict = Depends(get_current_user),
):
    sb = get_supabase()
    if factory_id:
        _ensure_factory_own(sb, factory_id, current)
    else:
        _require_admin(current, sb)   # 전 factory 대상 batch 는 ALL 전용
    return _call(svc.generate_all_items, factory_id, dry_run)


@router.post("/generate-schedules-all")
def generate_schedules_all(current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _require_admin(current, sb)       # 전사 batch 는 ALL 전용
    return _call(svc.generate_schedules_all)


@router.post("/generate-schedules/{factory_id}")
def generate_schedules_for_factory(
    factory_id: str,
    mode: str = Query("law_engine", description="'law_engine'(4조건) 또는 'anchor'(anchor_confirmed 기반)"),
    force: bool = Query(False, description="anchor 모드에서 기존 SCHEDULED 삭제 후 재생성"),
    current: dict = Depends(get_current_user),
):
    sb = get_supabase()
    _ensure_factory_own(sb, factory_id, current)
    return _call(svc.generate_schedules_for_factory, factory_id, mode, force)


@router.patch("/{inspection_set_id}")
def patch_inspection_set(inspection_set_id: str, body: InspectionSetPatchBody, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _ensure_set_own(sb, inspection_set_id, current)
    return _call(svc.patch_set, inspection_set_id, body)


@router.patch("/{inspection_set_id}/anchor")
def update_inspection_anchor(inspection_set_id: str, body: AnchorBody, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _ensure_set_own(sb, inspection_set_id, current)
    return _call(svc.update_anchor, inspection_set_id, body)


@router.post("/{inspection_set_id}/generate-items")
def generate_items(inspection_set_id: str, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _ensure_set_own(sb, inspection_set_id, current)
    return _call(svc.generate_items_for_set, inspection_set_id)


@router.get("/company/{company_id}")
def get_company_inspection_sets(company_id: str, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _ensure_own_company(company_id, current, sb, "회사를 찾을 수 없습니다.")
    return _call(svc.get_company_sets, company_id)


@router.get("/factory/{factory_id}")
def get_factory_inspection_sets(factory_id: str, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _ensure_factory_own(sb, factory_id, current)
    return _call(svc.get_factory_sets, factory_id)


# 주의: 아래 /{inspection_set_id} 보다 위에 둠 — 작업자앱 inspect.html 이 부르는 항목 조회.
@router.get("/{inspection_set_id}/items")
def get_inspection_set_items(inspection_set_id: str, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _ensure_set_own(sb, inspection_set_id, current)
    return _call(svc.get_set_items, inspection_set_id)


@router.get("/{inspection_set_id}")
def get_inspection_set(inspection_set_id: str, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _ensure_set_own(sb, inspection_set_id, current)
    return _call(svc.get_set_by_id, inspection_set_id)
