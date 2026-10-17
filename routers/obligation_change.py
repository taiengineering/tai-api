"""routers/obligation_change.py

WP01-D: 의무 변경관리 엔드포인트 (관리자 + 회사 소유 공장 게이트).

POST /obligation-change/change-summary   — ADDED/RETAINED/REMOVAL_CANDIDATE 현황 (READ-ONLY)
POST /obligation-change/preview-impact   — 제외 영향 일정 미리보기 (READ-ONLY, 관리자)
POST /obligation-change/process-scope-a  — 이번 회차 단건 제외 (관리자)
POST /obligation-change/process-scope-b  — 지정일 이후 반복 중단 (관리자)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from schemas.obligation_change import (
    ObligationChangeSummaryRequest,
    RemovalPreviewRequest,
    ScopeARemovalRequest,
    ScopeBRemovalRequest,
)
from services.company_scope import _scope as _get_scope
from services.wp01_obligation_change.change_tracker import (
    _is_current_removal_candidate,
    compute_change_summary,
)
from services.wp01_obligation_change.removal_processor import (
    preview_removal_impact,
    process_scope_a,
    process_scope_b,
)

router = APIRouter(prefix="/obligation-change", tags=["의무 변경관리"])
log = logging.getLogger("obligation_change")


def _require_company_admin(current: dict, supabase) -> None:
    """ALL(플랫폼 총관) 또는 COMPANY(고객사 관리자) 스코프 허용."""
    scope = _get_scope(supabase, current.get("role_code"))
    if scope not in ("ALL", "COMPANY"):
        raise HTTPException(403, "관리자 권한이 필요합니다")


def _require_company_factory(supabase, factory_id: str, current: dict) -> None:
    """현재 사용자의 회사가 해당 공장을 소유하는지 확인."""
    company_id = current.get("company_id")
    if not company_id:
        raise HTTPException(403, "회사 정보가 없습니다")
    res = (
        supabase.table("factories")
        .select("id")
        .eq("id", factory_id)
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(404, "해당 공장을 찾을 수 없습니다")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/change-summary")
def get_change_summary(
    body: ObligationChangeSummaryRequest,
    current: dict = Depends(get_current_user),
):
    """ADDED/RETAINED/REMOVAL_CANDIDATE 현황 조회 (READ-ONLY).

    진단 실행 직후 결과 화면에서 호출.
    회사 소유 공장 게이트 적용.
    """
    supabase = get_supabase()
    _require_company_factory(supabase, body.factory_id, current)
    try:
        result = compute_change_summary(
            supabase, body.factory_id, body.diagnosis_id, body.site_id
        )
        return {"status": "success", "data": result}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/preview-impact")
def get_removal_preview(
    body: RemovalPreviewRequest,
    current: dict = Depends(get_current_user),
):
    """제외 처리 전 영향 일정 미리보기 (READ-ONLY, 관리자 전용)."""
    supabase = get_supabase()
    _require_company_admin(current, supabase)
    _require_company_factory(supabase, body.factory_id, current)
    # FIX-04: 후보 재검증 — 최신 C10 기준 제외 후보가 아니면 차단
    if not _is_current_removal_candidate(supabase, body.factory_id, body.inspection_set_id):
        raise HTTPException(409, "해당 의무는 현재 제외 후보가 아닙니다")
    result = preview_removal_impact(
        supabase, body.factory_id, body.inspection_set_id, body.application_date
    )
    return {"status": "success", "data": result}


@router.post("/process-scope-a")
def process_scope_a_removal(
    body: ScopeARemovalRequest,
    current: dict = Depends(get_current_user),
):
    """Scope A: 이번 회차만 제외 (관리자 전용)."""
    supabase = get_supabase()
    _require_company_admin(current, supabase)
    _require_company_factory(supabase, body.factory_id, current)

    # FIX-03: inspection_set_id 검증 강화 — 누락·미연결·비후보 전부 차단
    ws_res = (
        supabase.table("work_schedules")
        .select("inspection_set_id")
        .eq("id", body.work_schedule_id)
        .eq("factory_id", body.factory_id)
        .limit(1)
        .execute()
    )
    if not ws_res.data:
        raise HTTPException(404, "해당 일정을 찾을 수 없습니다")
    iset_id = ws_res.data[0].get("inspection_set_id")
    if not iset_id:
        raise HTTPException(409, "해당 일정에 점검 세트가 연결되지 않았습니다")
    if not _is_current_removal_candidate(supabase, body.factory_id, iset_id):
        raise HTTPException(409, "해당 의무는 현재 제외 후보가 아닙니다")

    log.info(
        "[OBLIGATION_CHANGE] scope_a factory=%s schedule=%s reason=%s user=%s",
        body.factory_id,
        body.work_schedule_id,
        body.reason,
        current.get("id"),
    )
    result = process_scope_a(
        supabase, body.factory_id, body.work_schedule_id, body.reason
    )
    return {"status": "success", "data": result}


@router.post("/process-scope-b")
def process_scope_b_removal(
    body: ScopeBRemovalRequest,
    current: dict = Depends(get_current_user),
):
    """Scope B: 지정일 이후 반복 중단 (관리자 전용)."""
    supabase = get_supabase()
    _require_company_admin(current, supabase)
    _require_company_factory(supabase, body.factory_id, current)

    if not _is_current_removal_candidate(supabase, body.factory_id, body.inspection_set_id):
        raise HTTPException(409, "해당 의무는 현재 제외 후보가 아닙니다")

    log.info(
        "[OBLIGATION_CHANGE] scope_b factory=%s set=%s date=%s reason=%s user=%s",
        body.factory_id,
        body.inspection_set_id,
        body.application_date,
        body.reason,
        current.get("id"),
    )
    try:
        result = process_scope_b(
            supabase,
            body.factory_id,
            body.inspection_set_id,
            body.application_date,
            body.reason,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    # P4-02: inspection_sets UPDATE 실패 → partial_success (재시도 금지, 관리자 확인 필요)
    if not result.get("is_set_updated", True):
        return {
            "status": "partial_success",
            "data": result,
            "message": (
                f"일정 {result.get('schedules_cancelled', 0)}건이 취소됐으나 "
                "의무 세트 상태 갱신에 실패했습니다. 관리자 확인이 필요합니다."
            ),
        }
    return {"status": "success", "data": result}
