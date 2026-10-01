"""Admin QA Control API — WO-QA-CONTROL-PHASE2B-001.

/admin/qa/summary                       GET  — 전체 현황 요약
/admin/qa/items                         GET  — QA 항목 목록 (schedule 포함)
/admin/qa/items/{qa_item_id}            PATCH — QA 항목 수정
/admin/qa/items/{qa_item_id}/schedule   PATCH — 스케줄 수정
/admin/qa/runs                          GET  — 실행 목록
/admin/qa/runs/{run_id}                 GET  — 실행 상세 (targets + results + FLAKY 파생)
/admin/qa/runs                          POST — 실행 생성 (QUEUED)

인증: get_current_user + _require_admin(ALL scope).
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
    name:             Optional[str]  = None
    description:      Optional[str]  = None
    expected_summary: Optional[str]  = None
    enabled:          Optional[bool] = None


class SchedulePatch(BaseModel):
    enabled:         Optional[bool] = None
    frequency_type:  Optional[str]  = None
    frequency_value: Optional[int]  = None
    anchor_time:     Optional[str]  = None   # "HH:MM:SS"
    day_of_week:     Optional[int]  = None
    timezone:        Optional[str]  = None
    next_run_at:     Optional[str]  = None   # ISO datetime string


class CreateRunRequest(BaseModel):
    trigger_type: str
    requested_by: Optional[str]              = None
    qa_item_ids:  List[str]
    ordinals:     Optional[List[Optional[int]]] = None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/summary")
def get_summary(current: dict = Depends(get_current_user)):
    """QA 전체 현황 요약 — items 수 / active schedules / runs by status."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    return {"status": "success", "data": svc.get_summary(supabase)}


@router.get("/items")
def list_items(
    site_code:  Optional[str]  = Query(None),
    priority:   Optional[str]  = Query(None),
    enabled:    Optional[bool] = Query(None),
    page:       int            = Query(1, ge=1),
    page_size:  int            = Query(50, ge=1, le=200),
    current:    dict           = Depends(get_current_user),
):
    """QA 항목 목록. schedule 포함. N+1 없음."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    return {
        "status": "success",
        "data": svc.list_items(supabase, site_code, priority, enabled, page, page_size),
    }


@router.patch("/items/{qa_item_id}")
def update_item(
    qa_item_id: str,
    body:       ItemPatch,
    current:    dict = Depends(get_current_user),
):
    """QA 항목 수정 (name / description / expected_summary / enabled)."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    return {
        "status": "success",
        "data": svc.update_item(supabase, qa_item_id, body.model_dump(exclude_unset=True)),
    }


@router.patch("/items/{qa_item_id}/schedule")
def update_schedule(
    qa_item_id: str,
    body:       SchedulePatch,
    current:    dict = Depends(get_current_user),
):
    """QA 항목 스케줄 수정. DB semantic CHECK 위반 시 DB에서 400 반환."""
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
    page:         int           = Query(1, ge=1),
    page_size:    int           = Query(20, ge=1, le=100),
    current:      dict          = Depends(get_current_user),
):
    """QA 실행 목록. run_status / trigger_type 필터."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    return {
        "status": "success",
        "data": svc.list_runs(supabase, run_status, trigger_type, page, page_size),
    }


@router.get("/runs/{run_id}")
def get_run(
    run_id:  str,
    current: dict = Depends(get_current_user),
):
    """QA 실행 상세 — targets + results 포함. FLAKY 파생 표시."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    return {"status": "success", "data": svc.get_run(supabase, run_id)}


@router.post("/runs", status_code=201)
def create_run(
    body:    CreateRunRequest,
    current: dict = Depends(get_current_user),
):
    """QA 실행 생성 (QUEUED). GitHub dispatch = 0."""
    supabase = get_supabase()
    _require_admin(current, supabase)
    return {
        "status": "success",
        "data": svc.create_run(
            supabase,
            body.trigger_type,
            body.requested_by,
            body.qa_item_ids,
            body.ordinals,
        ),
    }
