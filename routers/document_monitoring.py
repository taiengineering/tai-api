"""TAI Document Engine Monitoring API v1.0.0
관리자 전용 문서엔진 감시.

접근: ROLE_ENGINE_ADMIN / ROLE_DOCUMENT_AUDITOR / ROLE_SUPER_ADMIN 전용.
목적: Document Governance Integrity 실시간 감시.
절대 금지: inferred requirement, guessed completeness, semantic fallback.
"""
from fastapi import APIRouter, Query, Request, HTTPException
from typing import Optional
import logging

router = APIRouter(prefix="/document-monitoring", tags=["문서엔진 감시"])
logger = logging.getLogger("document_monitoring")

ALLOWED_ROLES = {"ROLE_ENGINE_ADMIN", "ROLE_DOCUMENT_AUDITOR", "ROLE_SUPER_ADMIN", "admin", "super_admin"}


def _check_admin(request: Request):
    role = getattr(request.state, "user_role", None)
    if role and role not in ALLOWED_ROLES:
        raise HTTPException(403, "Document monitoring is admin-only.")


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/summary")
def document_monitoring_summary(request: Request):
    _check_admin(request)
    sb = _sb()

    # requirement rules
    rules = sb.table("document_requirement_rule").select("requirement_level").eq("is_active", True).execute()
    all_rules = rules.data or []
    mandatory_count = len([r for r in all_rules if r["requirement_level"] == "MANDATORY"])
    recommended_count = len([r for r in all_rules if r["requirement_level"] == "RECOMMENDED"])

    # integrity events (document-related)
    doc_types = [
        "DOCUMENT_COMPLETENESS_DRIFT", "REQUIREMENT_RULE_DRIFT",
        "HIDDEN_MANDATORY_DRIFT", "TEMPLATE_RENDER_DRIFT",
        "PDF_ARTIFACT_MISMATCH", "EXPLAINABILITY_LOSS",
        "UNSUPPORTED_DOCUMENT_INFERENCE",
        "COMPLETENESS_DRIFT_DETECTED", "MANDATORY_DRIFT_DETECTED"
    ]
    events = sb.table("engine_integrity_event").select("event_type, severity, resolved").in_("event_type", doc_types).execute()
    all_ev = events.data or []
    unresolved = [e for e in all_ev if not e["resolved"]]
    by_type = {}
    for e in unresolved:
        by_type[e["event_type"]] = by_type.get(e["event_type"], 0) + 1

    overall = "CLEAN"
    crit_types = {"DOCUMENT_COMPLETENESS_DRIFT", "COMPLETENESS_DRIFT_DETECTED", "EXPLAINABILITY_LOSS"}
    if any(by_type.get(t, 0) > 0 for t in crit_types):
        overall = "CRITICAL"
    elif len(unresolved) > 0:
        overall = "WARNING"

    return {
        "status": "success",
        "overall_status": overall,
        "mandatory_rules": mandatory_count,
        "recommended_rules": recommended_count,
        "total_rules": len(all_rules),
        "total_events": len(all_ev),
        "unresolved_events": len(unresolved),
        "by_type": by_type,
        "engine_version": "v2.0.0",
        "access": "ADMIN_ONLY",
    }


@router.get("/completeness-drift")
def get_completeness_drift(request: Request):
    _check_admin(request)
    sb = _sb()
    r = sb.table("engine_integrity_event").select("*").in_(
        "event_type", ["DOCUMENT_COMPLETENESS_DRIFT", "COMPLETENESS_DRIFT_DETECTED"]
    ).order("created_at", desc=True).limit(50).execute()
    return {"status": "success", "data": r.data or []}


@router.get("/rule-drift")
def get_rule_drift(request: Request):
    _check_admin(request)
    sb = _sb()
    r = sb.table("engine_integrity_event").select("*").eq(
        "event_type", "REQUIREMENT_RULE_DRIFT"
    ).order("created_at", desc=True).limit(50).execute()
    return {"status": "success", "data": r.data or []}


@router.get("/mandatory-drift")
def get_mandatory_drift(request: Request):
    _check_admin(request)
    sb = _sb()
    r = sb.table("engine_integrity_event").select("*").in_(
        "event_type", ["HIDDEN_MANDATORY_DRIFT", "MANDATORY_DRIFT_DETECTED"]
    ).order("created_at", desc=True).limit(50).execute()
    return {"status": "success", "data": r.data or []}


@router.get("/render-drift")
def get_render_drift(request: Request):
    _check_admin(request)
    sb = _sb()
    r = sb.table("engine_integrity_event").select("*").eq(
        "event_type", "TEMPLATE_RENDER_DRIFT"
    ).order("created_at", desc=True).limit(50).execute()
    return {"status": "success", "data": r.data or []}


@router.get("/pdf-artifact")
def get_pdf_artifact(request: Request):
    _check_admin(request)
    sb = _sb()
    r = sb.table("engine_integrity_event").select("*").eq(
        "event_type", "PDF_ARTIFACT_MISMATCH"
    ).order("created_at", desc=True).limit(50).execute()
    return {"status": "success", "data": r.data or []}


@router.get("/explainability-audit")
def get_explainability(request: Request):
    _check_admin(request)
    sb = _sb()
    r = sb.table("engine_integrity_event").select("*").eq(
        "event_type", "EXPLAINABILITY_LOSS"
    ).order("created_at", desc=True).limit(50).execute()
    return {"status": "success", "data": r.data or []}


@router.get("/unsupported-document")
def get_unsupported_document(request: Request):
    _check_admin(request)
    sb = _sb()
    r = sb.table("engine_integrity_event").select("*").eq(
        "event_type", "UNSUPPORTED_DOCUMENT_INFERENCE"
    ).order("created_at", desc=True).limit(50).execute()
    return {"status": "success", "data": r.data or []}


@router.get("/requirement-rules")
def get_requirement_rules(request: Request, form_code: Optional[str] = Query(None)):
    _check_admin(request)
    sb = _sb()
    q = sb.table("document_requirement_rule").select("*").eq("is_active", True)
    if form_code:
        q = q.eq("form_code", form_code)
    q = q.order("form_code").order("requirement_level").limit(200)
    r = q.execute()
    return {"status": "success", "data": r.data or []}


@router.get("/status")
def doc_monitoring_status():
    return {
        "status": "active",
        "engine": "Document Engine Monitoring v1.0.0",
        "access": "ADMIN_ONLY",
        "routes": [
            "/document-monitoring/summary",
            "/document-monitoring/completeness-drift",
            "/document-monitoring/rule-drift",
            "/document-monitoring/mandatory-drift",
            "/document-monitoring/render-drift",
            "/document-monitoring/pdf-artifact",
            "/document-monitoring/explainability-audit",
            "/document-monitoring/unsupported-document",
            "/document-monitoring/requirement-rules",
        ],
    }
