"""TAI Engine Monitoring Dashboard API v1.1.0
관리자 전용 엔진감시 대시보드.

접근: ROLE_ENGINE_ADMIN / ROLE_SYSTEM_AUDITOR / ROLE_SUPER_ADMIN 전용.
목적: deterministic drift / contamination 실시간 감시.
절대 금지: 자동 수정, AI correction, semantic fallback, public exposure.
"""
from fastapi import APIRouter, Query, Request, HTTPException
import logging

router = APIRouter(prefix="/engine-monitoring", tags=["엔진감시 대시보드"])
logger = logging.getLogger("engine_monitoring")

ALLOWED_ROLES = {"ROLE_ENGINE_ADMIN", "ROLE_SYSTEM_AUDITOR", "ROLE_SUPER_ADMIN", "admin", "super_admin"}


def _check_admin(request: Request):
    """관리자 권한 검증. Worker/일반사용자 접근 차단."""
    # JWT에서 role 추출 (현재는 헤더 기반 간이 검증)
    role = getattr(request.state, "user_role", None)
    # 개발 단계: role 미설정 시 허용 (운영 시 차단으로 전환)
    if role and role not in ALLOWED_ROLES:
        raise HTTPException(403, "Engine monitoring is admin-only. Access denied.")


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/summary")
def engine_monitoring_summary(request: Request):
    _check_admin(request)
    sb = _sb()
    events = sb.table("engine_integrity_event").select("severity, resolved").execute()
    all_ev = events.data or []
    unresolved = [e for e in all_ev if not e["resolved"]]
    by_sev = {}
    for e in unresolved:
        by_sev[e["severity"]] = by_sev.get(e["severity"], 0) + 1

    by_type = {}
    events2 = sb.table("engine_integrity_event").select("event_type, resolved").execute()
    for e in (events2.data or []):
        if not e["resolved"]:
            by_type[e["event_type"]] = by_type.get(e["event_type"], 0) + 1

    overall = "CLEAN"
    if by_sev.get("CRITICAL", 0) > 0:
        overall = "CRITICAL"
    elif by_sev.get("HIGH", 0) > 0:
        overall = "HIGH"
    elif by_sev.get("WARNING", 0) > 0:
        overall = "WARNING"

    return {
        "status": "success",
        "overall_status": overall,
        "total_events": len(all_ev),
        "unresolved_events": len(unresolved),
        "by_severity": by_sev,
        "by_type": by_type,
        "engine_version": "v5.55.0",
        "boundary": "DETERMINISTIC_ONLY",
        "access": "ADMIN_ONLY",
    }


@router.get("/drift-events")
def get_drift_events(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    _check_admin(request)
    sb = _sb()
    q = sb.table("engine_integrity_event").select("*").in_(
        "event_type", ["OBLIGATION_DRIFT_DETECTED", "COMPLETENESS_DRIFT_DETECTED", "MANDATORY_DRIFT_DETECTED"]
    ).order("created_at", desc=True)
    offset = (page - 1) * page_size
    q = q.range(offset, offset + page_size - 1)
    r = q.execute()
    return {"status": "success", "data": r.data or [], "page": page}


@router.get("/ai-contamination")
def get_ai_contamination(request: Request):
    _check_admin(request)
    sb = _sb()
    q = sb.table("engine_integrity_event").select("*").in_(
        "event_type", ["AI_CONTAMINATION_DETECTED", "UNSUPPORTED_INFERENCE_DETECTED"]
    ).order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "data": r.data or []}


@router.get("/mandatory-drift")
def get_mandatory_drift(request: Request):
    _check_admin(request)
    sb = _sb()
    q = sb.table("engine_integrity_event").select("*").eq(
        "event_type", "MANDATORY_DRIFT_DETECTED"
    ).order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "data": r.data or []}


@router.get("/checklist-explosion")
def get_checklist_explosion(request: Request):
    _check_admin(request)
    sb = _sb()
    q = sb.table("engine_integrity_event").select("*").eq(
        "event_type", "CHECKLIST_EXPLOSION_DETECTED"
    ).order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "data": r.data or []}


@router.get("/unsupported-domain")
def get_unsupported_domain(request: Request):
    _check_admin(request)
    sb = _sb()
    q = sb.table("engine_integrity_event").select("*").eq(
        "event_type", "UNSUPPORTED_INFERENCE_DETECTED"
    ).order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "data": r.data or []}


@router.get("/explainability-audit")
def get_explainability_audit(request: Request):
    _check_admin(request)
    sb = _sb()
    q = sb.table("engine_integrity_event").select("*").eq(
        "event_type", "EXPLAINABILITY_LOSS_DETECTED"
    ).order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "data": r.data or []}


@router.get("/status")
def monitoring_status():
    return {
        "status": "active",
        "engine": "Engine Monitoring Dashboard v1.1.0",
        "access": "ADMIN_ONLY",
        "allowed_roles": list(ALLOWED_ROLES),
        "routes": [
            "/engine-monitoring/summary",
            "/engine-monitoring/drift-events",
            "/engine-monitoring/ai-contamination",
            "/engine-monitoring/mandatory-drift",
            "/engine-monitoring/checklist-explosion",
            "/engine-monitoring/unsupported-domain",
            "/engine-monitoring/explainability-audit",
        ],
    }
