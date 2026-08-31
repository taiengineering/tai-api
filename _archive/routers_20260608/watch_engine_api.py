# routers/watch_engine_api.py — Watch Engine Cockpit API v1.2
"""
Watch Engine Admin API + Founder Cockpit Backend.
v1.2: Issue Workflow (ACK / RESOLVE / IGNORE / NOTE)
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from services.time import now_kst, serialize_external_utc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watch-engine", tags=["감시엔진"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# ═══ SECTION 1: Health Summary ═══

@router.get("/cockpit/health")
def get_health_summary():
    try:
        sb = _sb()
        active = sb.table("engine_integrity_event").select("id", count="exact") \
            .eq("resolved", False).eq("ignored", False).not_.is_("trace_id", "null").execute()
        critical = sb.table("engine_integrity_event").select("id", count="exact") \
            .eq("resolved", False).eq("ignored", False).eq("severity", "CRITICAL").not_.is_("trace_id", "null").execute()

        synth_jobs = ["SYNTHETIC_LOGIN", "SYNTHETIC_PROCESS_REG"]
        synth_status = {}
        for jc in synth_jobs:
            last = sb.table("cron_job_log").select("status,finished_at") \
                .eq("job_code", jc).order("started_at", desc=True).limit(1).execute()
            synth_status[jc] = last.data[0] if last.data else {"status": "NEVER_RUN", "finished_at": None}

        eval_last = sb.table("cron_job_log").select("status,finished_at") \
            .eq("job_code", "INTEGRITY_EVALUATE").order("started_at", desc=True).limit(1).execute()

        ac = active.count or 0
        cc = critical.count or 0
        overall = "critical" if cc > 0 else ("warning" if ac > 0 else "healthy")

        return {"status": "success", "data": {
            "overall_health": overall, "active_issues": ac, "critical_issues": cc,
            "synthetic": synth_status,
            "evaluator": eval_last.data[0] if eval_last.data else {"status": "NEVER_RUN"},
            "engine_version": "v1.2",
        }}
    except Exception as e:
        logger.error("Cockpit health: %s", e)
        return {"status": "error", "message": str(e)}


# ═══ SECTION 2: Issues (with status filter) ═══

@router.get("/cockpit/issues")
def get_active_issues(severity: str = None, show: str = "active", limit: int = 20):
    """show: active(기본) | acknowledged | resolved | ignored | all"""
    try:
        sb = _sb()
        q = sb.table("engine_integrity_event") \
            .select("id,event_type,severity,integrity_status,health_status,flow_key,step_key,trace_id,description,created_at,resolved,acknowledged,ignored,operator_note") \
            .not_.is_("trace_id", "null").order("created_at", desc=True).limit(limit)

        if show == "active":
            q = q.eq("resolved", False).eq("ignored", False)
        elif show == "acknowledged":
            q = q.eq("acknowledged", True).eq("resolved", False)
        elif show == "resolved":
            q = q.eq("resolved", True)
        elif show == "ignored":
            q = q.eq("ignored", True)

        if severity:
            q = q.eq("severity", severity)

        resp = q.execute()
        return {"status": "success", "data": resp.data or [], "total": len(resp.data or [])}
    except Exception as e:
        logger.error("Cockpit issues: %s", e)
        return {"status": "error", "message": str(e)}


# ═══ SECTION 3: Synthetic Heartbeat ═══

@router.get("/cockpit/synthetic")
def get_synthetic_heartbeat():
    try:
        sb = _sb()
        results = []
        for jc in ["SYNTHETIC_LOGIN", "SYNTHETIC_PROCESS_REG"]:
            runs = sb.table("cron_job_log").select("status,started_at,finished_at,duration_seconds,result_detail,result_summary") \
                .eq("job_code", jc).order("started_at", desc=True).limit(5).execute()
            last_success = next((r["finished_at"] for r in (runs.data or []) if r["status"] == "SUCCESS"), None)
            last_failure = next((r["finished_at"] for r in (runs.data or []) if r["status"] in ("FAILED", "WARNING")), None)
            results.append({"job_code": jc, "scenario_name": jc.replace("SYNTHETIC_", "").lower(),
                            "last_success": last_success, "last_failure": last_failure,
                            "last_run": runs.data[0] if runs.data else None, "recent_runs": runs.data or []})
        return {"status": "success", "data": results}
    except Exception as e:
        logger.error("Cockpit synthetic: %s", e)
        return {"status": "error", "message": str(e)}


# ═══ SECTION 4: Scheduler ═══

@router.get("/cockpit/scheduler")
def get_scheduler_status():
    try:
        sb = _sb()
        results = []
        for jc in ["INTEGRITY_EVALUATE", "SYNTHETIC_LOGIN", "SYNTHETIC_PROCESS_REG", "SYNTHETIC_CLEANUP"]:
            job = sb.table("cron_job_master").select("job_code,job_name,cron_expression,is_active,endpoint_url") \
                .eq("job_code", jc).limit(1).execute()
            last = sb.table("cron_job_log").select("status,started_at,finished_at,duration_seconds,error_message,result_detail") \
                .eq("job_code", jc).order("started_at", desc=True).limit(1).execute()
            results.append({"job": job.data[0] if job.data else {"job_code": jc}, "last_run": last.data[0] if last.data else None})
        return {"status": "success", "data": results}
    except Exception as e:
        logger.error("Cockpit scheduler: %s", e)
        return {"status": "error", "message": str(e)}


# ═══ SECTION 5: Top Failures ═══

@router.get("/cockpit/top-failures")
def get_top_failing_flows(days: int = 7):
    try:
        sb = _sb()
        since = (now_kst() - timedelta(days=days)).isoformat()
        issues = sb.table("engine_integrity_event") \
            .select("flow_key,event_type,severity,created_at") \
            .eq("resolved", False).eq("ignored", False).not_.is_("trace_id", "null") \
            .gte("created_at", since).order("created_at", desc=True).execute()

        flow_stats = {}
        for i in (issues.data or []):
            fk = i.get("flow_key", "unknown")
            if fk not in flow_stats:
                flow_stats[fk] = {"flow_key": fk, "issue_count": 0, "types": {}, "last_detected": None}
            flow_stats[fk]["issue_count"] += 1
            et = i.get("event_type", "unknown")
            flow_stats[fk]["types"][et] = flow_stats[fk]["types"].get(et, 0) + 1
            if not flow_stats[fk]["last_detected"]:
                flow_stats[fk]["last_detected"] = i.get("created_at")

        ranked = sorted(flow_stats.values(), key=lambda x: x["issue_count"], reverse=True)
        for r in ranked:
            if r["types"]:
                r["top_issue_type"] = max(r["types"], key=r["types"].get)
                r["top_issue_count"] = r["types"][r["top_issue_type"]]
            del r["types"]
        return {"status": "success", "data": ranked[:10]}
    except Exception as e:
        logger.error("Cockpit top-failures: %s", e)
        return {"status": "error", "message": str(e)}


# ═══ ISSUE WORKFLOW ═══

class NoteBody(BaseModel):
    note: str
    operator: str = "founder"

class IgnoreBody(BaseModel):
    reason: str = ""
    operator: str = "founder"

class AckBody(BaseModel):
    operator: str = "founder"

class ResolveBody(BaseModel):
    operator: str = "founder"
    note: Optional[str] = None


@router.post("/issues/{issue_id}/ack")
def acknowledge_issue(issue_id: str, body: AckBody):
    try:
        sb = _sb()
        sb.table("engine_integrity_event").update({
            "acknowledged": True,
            "acknowledged_at": serialize_external_utc(now_kst()),
            "acknowledged_by": body.operator,
        }).eq("id", issue_id).execute()
        return {"status": "success", "message": "확인 처리됨"}
    except Exception as e:
        logger.error("ACK failed: %s", e)
        return {"status": "error", "message": str(e)}


@router.post("/issues/{issue_id}/resolve")
def resolve_issue(issue_id: str, body: ResolveBody):
    try:
        sb = _sb()
        update = {
            "resolved": True,
            "resolved_at": serialize_external_utc(now_kst()),
        }
        if body.note:
            update["operator_note"] = body.note
        sb.table("engine_integrity_event").update(update).eq("id", issue_id).execute()
        return {"status": "success", "message": "해결 처리됨"}
    except Exception as e:
        logger.error("RESOLVE failed: %s", e)
        return {"status": "error", "message": str(e)}


@router.post("/issues/{issue_id}/ignore")
def ignore_issue(issue_id: str, body: IgnoreBody):
    try:
        sb = _sb()
        sb.table("engine_integrity_event").update({
            "ignored": True,
            "ignored_reason": body.reason or "운영자 무시 처리",
        }).eq("id", issue_id).execute()
        return {"status": "success", "message": "무시 처리됨"}
    except Exception as e:
        logger.error("IGNORE failed: %s", e)
        return {"status": "error", "message": str(e)}


@router.post("/issues/{issue_id}/note")
def add_note(issue_id: str, body: NoteBody):
    try:
        sb = _sb()
        sb.table("engine_integrity_event").update({
            "operator_note": body.note,
        }).eq("id", issue_id).execute()
        return {"status": "success", "message": "메모 저장됨"}
    except Exception as e:
        logger.error("NOTE failed: %s", e)
        return {"status": "error", "message": str(e)}


# ═══ Manual Evaluate ═══

@router.post("/evaluate")
def run_integrity_evaluation():
    t0 = time.time()
    try:
        from watch_engine.integrity.evaluator import evaluate_recent_events
        result = evaluate_recent_events(last_minutes=10)
        return {"status": "success", "message": "평가 완료", "data": {**result, "duration_ms": int((time.time() - t0) * 1000)}}
    except Exception as e:
        logger.error("Evaluation failed: %s", e)
        return {"status": "error", "message": str(e), "data": {"errors": 1, "duration_ms": int((time.time() - t0) * 1000)}}
