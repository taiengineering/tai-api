"""Admin QA Control API — WO-QA-CONTROL-PHASE2B-001 PATCH-1.

/admin/qa/summary                       GET  — 전체 현황 요약
/admin/qa/items                         GET  — QA 항목 목록 (schedule + effective_status 포함)
/admin/qa/items/{qa_item_id}            PATCH — enabled 수정만 허용
/admin/qa/items/{qa_item_id}/schedule   PATCH — 스케줄 수정 (next_run_at 서버 강제 NULL)
/admin/qa/runs                          GET  — 실행 목록 (target_count/result_count/effective_counts 포함)
/admin/qa/runs/{run_id}                 GET  — 실행 상세 (targets 풍부, FLAKY 파생)
/admin/qa/runs                          POST — MANUAL 실행 생성 (client=qa_item_ids only)

인증: get_current_user + _require_admin (ALL scope).
GitHub dispatch = 0. Slack = 0. DB schema mutation = 0.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _require_admin
from services import qa_control_svc as svc

router = APIRouter(prefix="/admin/qa", tags=["admin-qa"])


# ── Request models ─────────────────────────────────────────────────────────────

class ItemPatch(BaseModel):
    """enabled 필드만 허용. name/description/expected_summary 수정 불가 (drift 방지)."""
    enabled: Optional[bool] = None


class SchedulePatch(BaseModel):
    """next_run_at은 서버가 항상 NULL로 강제 (Phase 2-E scheduler authority).
    client에서 next_run_at을 보내도 무시된다."""
    enabled:         Optional[bool] = None
    frequency_type:  Optional[str]  = None
    frequency_value: Optional[int]  = None
    anchor_time:     Optional[str]  = None   # "HH:MM:SS"
    day_of_week:     Optional[int]  = None
    timezone:        Optional[str]  = None


class CreateRunRequest(BaseModel):
    """MANUAL run 생성. trigger_type/requested_by/ordinals는 서버가 고정."""
    qa_item_ids: List[str]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/summary")
def get_summary(current: dict = Depends(get_current_user)):
    """QA 전체 현황 — total/enabled/status_counts(FLAKY 포함)/sites."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    return {"status": "success", "data": svc.get_summary(supabase)}


@router.get("/items")
def list_items(
    site_code:        Optional[str]  = Query(None),
    priority:         Optional[str]  = Query(None),
    enabled:          Optional[bool] = Query(None),
    category:         Optional[str]  = Query(None),
    effective_status: Optional[str]  = Query(None),
    page:             int            = Query(1, ge=1),
    page_size:        int            = Query(50, ge=1, le=200),
    current:          dict           = Depends(get_current_user),
):
    """QA 항목 목록. schedule + effective_status + last_run_* 포함. N+1 없음."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    return {
        "status": "success",
        "data": svc.list_items(
            supabase, site_code, priority, enabled, category, effective_status, page, page_size
        ),
    }


@router.patch("/items/{qa_item_id}")
def update_item(
    qa_item_id: str,
    body:       ItemPatch,
    current:    dict = Depends(get_current_user),
):
    """QA 항목 enabled 수정 전용."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    return {
        "status": "success",
        "data": svc.update_item(supabase, qa_item_id, body.enabled),
    }


@router.patch("/items/{qa_item_id}/schedule")
def update_schedule(
    qa_item_id: str,
    body:       SchedulePatch,
    current:    dict = Depends(get_current_user),
):
    """QA 스케줄 수정. semantic CHECK API 선검증. next_run_at 서버 강제 NULL."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    return {
        "status": "success",
        "data": svc.update_schedule(supabase, qa_item_id, body.model_dump(exclude_unset=True)),
    }


@router.get("/runs")
def list_runs(
    run_status:   Optional[str] = Query(None),
    trigger_type: Optional[str] = Query(None),
    from_date:    Optional[str] = Query(None),
    to_date:      Optional[str] = Query(None),
    page:         int           = Query(1, ge=1),
    page_size:    int           = Query(20, ge=1, le=100),
    current:      dict          = Depends(get_current_user),
):
    """QA 실행 목록. target_count/result_count/effective_counts 포함."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    return {
        "status": "success",
        "data": svc.list_runs(supabase, run_status, trigger_type, from_date, to_date, page, page_size),
    }


@router.get("/runs/{run_id}")
def get_run(
    run_id:  str,
    current: dict = Depends(get_current_user),
):
    """QA 실행 상세 — targets(scenario_id/name 포함) + results + FLAKY 파생."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    return {"status": "success", "data": svc.get_run(supabase, run_id)}


@router.post("/runs", status_code=201)
def create_run(
    body:    CreateRunRequest,
    current: dict = Depends(get_current_user),
):
    """MANUAL QA 실행 생성 (QUEUED). trigger_type/requested_by/ordinals 서버 고정."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    return {
        "status": "success",
        "data": svc.create_run(supabase, current["id"], body.qa_item_ids),
    }
