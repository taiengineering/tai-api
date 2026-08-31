"""TAI Legal Intake Pipeline API v1.0.0
법령 변경 시그널 감지 + 엔진 탑재 후보 관리.

절대 금지: 자동 publish, AI 법령 해석, semantic fallback.
흐름: detect → collect → candidate → human review → publish
"""
from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional
import hashlib, logging
from datetime import datetime
from services.time import now_kst, serialize_business_datetime

router = APIRouter(prefix="/legal-intake", tags=["법령변경감시"])
logger = logging.getLogger("legal_intake")

ALLOWED_ROLES = {"ROLE_ENGINE_ADMIN", "ROLE_SUPER_ADMIN", "admin", "super_admin"}


def _check_admin(request: Request):
    role = getattr(request.state, "user_role", None)
    if role and role not in ALLOWED_ROLES:
        raise HTTPException(403, "Legal intake is admin-only.")


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/status")
def legal_intake_status():
    sb = _sb()
    events = sb.table("legal_change_event").select("id", count="exact").execute()
    candidates = sb.table("legal_intake_candidate").select("id", count="exact").execute()
    registry = sb.table("legal_source_registry").select("id", count="exact").execute()
    return {
        "status": "active",
        "engine": "Legal Intake Pipeline v1.0.0",
        "change_events": len(events.data or []),
        "intake_candidates": len(candidates.data or []),
        "source_registry": len(registry.data or []),
        "auto_publish": "BLOCKED",
        "boundary": "DETERMINISTIC_ONLY",
    }


@router.get("/change-events")
def list_change_events(
    request: Request,
    status: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    _check_admin(request)
    sb = _sb()
    q = sb.table("legal_change_event").select("*")
    if status:
        q = q.eq("status", status)
    if event_type:
        q = q.eq("event_type", event_type)
    offset = (page - 1) * page_size
    q = q.order("detected_at", desc=True).range(offset, offset + page_size - 1)
    r = q.execute()
    return {"status": "success", "data": r.data or [], "page": page}


@router.get("/candidates")
def list_candidates(
    request: Request,
    review_status: Optional[str] = Query(None),
    parse_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    _check_admin(request)
    sb = _sb()
    q = sb.table("legal_intake_candidate").select("*")
    if review_status:
        q = q.eq("review_status", review_status)
    if parse_status:
        q = q.eq("parse_status", parse_status)
    offset = (page - 1) * page_size
    q = q.order("created_at", desc=True).range(offset, offset + page_size - 1)
    r = q.execute()
    return {"status": "success", "data": r.data or [], "page": page}


@router.get("/source-registry")
def list_source_registry(
    request: Request,
    law_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    _check_admin(request)
    sb = _sb()
    q = sb.table("legal_source_registry").select("id, law_source, law_id, law_name, law_type, status, revision_id, promulgation_date, enforcement_date, collected_at")
    if law_id:
        q = q.eq("law_id", law_id)
    offset = (page - 1) * page_size
    q = q.order("collected_at", desc=True).range(offset, offset + page_size - 1)
    r = q.execute()
    return {"status": "success", "data": r.data or [], "page": page}


@router.post("/run-cron")
def run_legal_cron(request: Request):
    """\uc218\ub3d9 cron \uc2e4\ud589 (\uad00\ub9ac\uc790 \uc804\uc6a9). \uc2e4\uc81c \ubc95\uc81c\ucc98 API \ud638\ucd9c \uc804 stub."""
    _check_admin(request)
    # Phase B: 법제처 API 연동 시 여기에 collector 호출
    # 현재는 stub — 실제 API 키 + 네트워크 연결 필요
    logger.info("LEGAL_CRON_MANUAL_RUN | triggered by admin")
    return {
        "status": "success",
        "message": "Legal cron stub executed. 법제처 API 연동 후 실제 수집 시작.",
        "auto_publish": "BLOCKED",
    }


@router.post("/candidates/{candidate_id}/mark-review-required")
def mark_review_required(request: Request, candidate_id: str):
    _check_admin(request)
    sb = _sb()
    existing = sb.table("legal_intake_candidate").select("id, review_status").eq("id", candidate_id).execute()
    if not existing.data:
        raise HTTPException(404, "Candidate not found")
    sb.table("legal_intake_candidate").update({
        "review_status": "REVIEW_REQUIRED",
        "updated_at": serialize_business_datetime(now_kst()),
    }).eq("id", candidate_id).execute()
    return {"status": "success", "candidate_id": candidate_id, "review_status": "REVIEW_REQUIRED"}
