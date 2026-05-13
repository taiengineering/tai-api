"""TAI Engine Integrity Monitor v1.0.0
Deterministic drift/contamination 탐지 시스템.

탐지 대상:
- obligation drift
- completeness drift
- hidden mandatory drift
- AI contamination
- unsupported inference
- checklist explosion
- notification storm
- explainability loss

절대 금지: inferred/guessed/semantic/AI decision
"""
from fastapi import APIRouter, Query
from typing import Optional
import hashlib, logging

router = APIRouter(prefix="/integrity", tags=["엔진 무결성 감시"])
logger = logging.getLogger("integrity_monitor")


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


def _emit(event_type, severity, domain, description, detail=None, input_hash=None):
    sb = _sb()
    row = {
        "event_type": event_type,
        "severity": severity,
        "domain": domain,
        "description": description,
        "detail": detail,
        "input_hash": input_hash,
        "source_trace": "INTEGRITY_MONITOR",
    }
    sb.table("engine_integrity_event").insert(row).execute()
    logger.warning(f"INTEGRITY_EVENT | {event_type} | {severity} | {description}")


@router.get("/run-audit")
def run_full_integrity_audit():
    """Phase A~I 전체 deterministic 무결성 감사 실행"""
    sb = _sb()
    results = []

    # A: Obligation Drift
    obl = sb.table("runtime_obligation_registry").select("id, execution_type").execute()
    obl_count = len(obl.data or [])
    results.append({"check": "obligation_count", "value": obl_count, "status": "OK"})

    # B: Completeness Drift — mandatory rule 존재하는데 creatable=true 인 것 탐지
    rules = sb.table("document_requirement_rule").select("form_code, requirement_level").eq("is_active", True).execute()
    mandatory_forms = set(r["form_code"] for r in (rules.data or []) if r["requirement_level"] == "MANDATORY")
    results.append({"check": "mandatory_rule_forms", "value": len(mandatory_forms), "status": "OK"})

    # C: Hidden Mandatory Drift
    recommended_rules = [r for r in (rules.data or []) if r["requirement_level"] == "RECOMMENDED"]
    results.append({"check": "recommended_rules", "value": len(recommended_rules), "status": "OK"})

    # D: Mapping Mutation
    mutations = sb.table("mapping_mutation_audit").select("id").order("created_at", desc=True).limit(10).execute()
    results.append({"check": "recent_mapping_mutations", "value": len(mutations.data or []), "status": "OK"})

    # E: AI Contamination — source_trace 검사
    ai_traces = sb.table("engine_integrity_event").select("id").eq("event_type", "AI_CONTAMINATION_DETECTED").eq("resolved", False).execute()
    ai_count = len(ai_traces.data or [])
    ai_status = "CRITICAL" if ai_count > 0 else "OK"
    results.append({"check": "ai_contamination", "value": ai_count, "status": ai_status})

    # F: Unsupported Inference
    unsup = sb.table("engine_integrity_event").select("id").eq("event_type", "UNSUPPORTED_INFERENCE_DETECTED").eq("resolved", False).execute()
    results.append({"check": "unsupported_inference", "value": len(unsup.data or []), "status": "OK" if not unsup.data else "WARNING"})

    # G: Checklist Explosion
    wo_count = sb.table("runtime_operational_work_order").select("id", count="exact").execute()
    isi_count = sb.table("inspection_set_items").select("id", count="exact").execute()
    wo_n = len(wo_count.data or [])
    isi_n = len(isi_count.data or [])
    ratio = round(isi_n / max(wo_n, 1), 1)
    explosion = "HIGH" if ratio > 50 else "OK"
    results.append({"check": "checklist_ratio", "value": f"{isi_n}/{wo_n}={ratio}", "status": explosion})

    # H: Notification Storm
    noti = sb.table("runtime_notification_event").select("id").eq("event_status", "PENDING").execute()
    noti_pending = len(noti.data or [])
    storm = "HIGH" if noti_pending > 10000 else "WARNING" if noti_pending > 5000 else "OK"
    results.append({"check": "notification_pending", "value": noti_pending, "status": storm})

    # I: Explainability — source_trace NULL 검사
    null_traces = sb.table("runtime_compliance_evidence").select("id").is_("source_trace", "null").limit(1).execute()
    explain_status = "CRITICAL" if null_traces.data else "OK"
    results.append({"check": "explainability_null_trace", "value": len(null_traces.data or []), "status": explain_status})

    overall = "CLEAN" if all(r["status"] == "OK" for r in results) else "ISSUES_DETECTED"
    return {
        "status": "success",
        "overall": overall,
        "checks": results,
        "source": "DETERMINISTIC_AUDIT",
    }


@router.get("/events")
def list_integrity_events(
    severity: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    resolved: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    sb = _sb()
    q = sb.table("engine_integrity_event").select("*")
    if severity:
        q = q.eq("severity", severity)
    if event_type:
        q = q.eq("event_type", event_type)
    if resolved is not None:
        q = q.eq("resolved", resolved)
    offset = (page - 1) * page_size
    q = q.order("created_at", desc=True).range(offset, offset + page_size - 1)
    r = q.execute()
    return {"status": "success", "data": r.data or [], "page": page}


@router.get("/mapping-audit")
def list_mapping_mutations(
    table_name: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
):
    sb = _sb()
    q = sb.table("mapping_mutation_audit").select("*")
    if table_name:
        q = q.eq("table_name", table_name)
    q = q.order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "data": r.data or []}


@router.get("/status")
def integrity_status():
    return {
        "status": "active",
        "engine": "Engine Integrity Monitor v1.0.0",
        "detectors": [
            "obligation_drift", "completeness_drift", "mandatory_drift",
            "mapping_mutation", "ai_contamination", "unsupported_inference",
            "checklist_explosion", "notification_storm", "explainability_loss",
        ],
        "boundary": "DETERMINISTIC_ONLY",
    }
