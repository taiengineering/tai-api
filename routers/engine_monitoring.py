"""TAI Engine Monitoring Dashboard API v1.0.0
관리자 전용 엔진감시 대시보드.

목적: deterministic drift / contamination 실시간 감시.
절대 금지: 자동 수정, AI correction, semantic fallback.
"""
from fastapi import APIRouter, Query
from typing import Optional
import logging

router = APIRouter(prefix="/engine-monitoring", tags=["엔진감시 대시보드"])
logger = logging.getLogger("engine_monitoring")


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/summary")
def engine_monitoring_summary():
    sb = _sb()
    # counts by severity
    events = sb.table("engine_integrity_event").select("severity, resolved").execute()
    all_ev = events.data or []
    unresolved = [e for e in all_ev if not e["resolved"]]
    by_sev = {}
    for e in unresolved:
        by_sev[e["severity"]] = by_sev.get(e["severity"], 0) + 1

    # counts by type
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
        "engine_version": "v5.54.0",
        "boundary": "DETERMINISTIC_ONLY",
    }


@router.get("/drift-events")
def get_drift_events(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    sb = _sb()
    q = sb.table("engine_integrity_event").select("*").in_(
        "event_type", ["OBLIGATION_DRIFT_DETECTED", "COMPLETENESS_DRIFT_DETECTED", "MANDATORY_DRIFT_DETECTED"]
    ).order("created_at", desc=True)
    offset = (page - 1) * page_size
    q = q.range(offset, offset + page_size - 1)
    r = q.execute()
    return {"status": "success", "data": r.data or [], "page": page}


@router.get("/ai-contamination")
def get_ai_contamination(page: int = Query(1, ge=1)):
    sb = _sb()
    q = sb.table("engine_integrity_event").select("*").in_(
        "event_type", ["AI_CONTAMINATION_DETECTED", "UNSUPPORTED_INFERENCE_DETECTED"]
    ).order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "data": r.data or []}


@router.get("/mandatory-drift")
def get_mandatory_drift():
    sb = _sb()
    q = sb.table("engine_integrity_event").select("*").eq(
        "event_type", "MANDATORY_DRIFT_DETECTED"
    ).order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "data": r.data or []}


@router.get("/checklist-explosion")
def get_checklist_explosion():
    sb = _sb()
    q = sb.table("engine_integrity_event").select("*").eq(
        "event_type", "CHECKLIST_EXPLOSION_DETECTED"
    ).order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "data": r.data or []}


@router.get("/unsupported-domain")
def get_unsupported_domain():
    sb = _sb()
    q = sb.table("engine_integrity_event").select("*").eq(
        "event_type", "UNSUPPORTED_INFERENCE_DETECTED"
    ).order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "data": r.data or []}


@router.get("/explainability-audit")
def get_explainability_audit():
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
        "engine": "Engine Monitoring Dashboard v1.0.0",
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
