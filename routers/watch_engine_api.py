# routers/watch_engine_api.py — Watch Engine Cockpit API v1.1
"""
Watch Engine Admin API + Founder Cockpit Backend.
5개 섹션: health summary, active issues, synthetic heartbeat, scheduler, top failing flows.
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watch-engine", tags=["감시엔진"])


# ═══════════════════════════════════════════════════════════
# SECTION 1: System Health Summary
# ═══════════════════════════════════════════════════════════

@router.get("/cockpit/health")
def get_health_summary():
    """10초 판단용: 전체 시스템 상태 한눈에."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        # Active integrity issues
        active = sb.table("engine_integrity_event") \
            .select("severity", count="exact") \
            .eq("resolved", False) \
            .not_.is_("trace_id", "null") \
            .execute()
        active_count = active.count or 0

        # Critical count
        critical = sb.table("engine_integrity_event") \
            .select("id", count="exact") \
            .eq("resolved", False) \
            .eq("severity", "CRITICAL") \
            .not_.is_("trace_id", "null") \
            .execute()
        critical_count = critical.count or 0

        # Last synthetic results
        synth_jobs = ["SYNTHETIC_LOGIN", "SYNTHETIC_PROCESS_REG"]
        synth_status = {}
        for jc in synth_jobs:
            last = sb.table("cron_job_log") \
                .select("status,finished_at,result_detail") \
                .eq("job_code", jc) \
                .order("started_at", desc=True) \
                .limit(1).execute()
            if last.data:
                synth_status[jc] = {
                    "status": last.data[0].get("status"),
                    "finished_at": last.data[0].get("finished_at"),
                }
            else:
                synth_status[jc] = {"status": "NEVER_RUN", "finished_at": None}

        # Last evaluator
        eval_last = sb.table("cron_job_log") \
            .select("status,finished_at") \
            .eq("job_code", "INTEGRITY_EVALUATE") \
            .order("started_at", desc=True) \
            .limit(1).execute()
        eval_status = eval_last.data[0] if eval_last.data else {"status": "NEVER_RUN"}

        # Overall health
        if critical_count > 0:
            overall = "critical"
        elif active_count > 0:
            overall = "warning"
        else:
            overall = "healthy"

        return {
            "status": "success",
            "data": {
                "overall_health": overall,
                "active_issues": active_count,
                "critical_issues": critical_count,
                "synthetic": synth_status,
                "evaluator": eval_status,
                "engine_version": "v1.1",
            }
        }
    except Exception as e:
        logger.error("Cockpit health failed: %s", e)
        return {"status": "error", "message": str(e)}


# ═══════════════════════════════════════════════════════════
# SECTION 2: Active Integrity Issues
# ═══════════════════════════════════════════════════════════

@router.get("/cockpit/issues")
def get_active_issues(severity: str = None, limit: int = 20):
    """현재 위험한 것 목록."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        q = sb.table("engine_integrity_event") \
            .select("id,event_type,severity,integrity_status,health_status,flow_key,step_key,trace_id,description,created_at,resolved") \
            .eq("resolved", False) \
            .not_.is_("trace_id", "null") \
            .order("created_at", desc=True) \
            .limit(limit)

        if severity:
            q = q.eq("severity", severity)

        resp = q.execute()

        return {
            "status": "success",
            "data": resp.data or [],
            "total": len(resp.data or []),
        }
    except Exception as e:
        logger.error("Cockpit issues failed: %s", e)
        return {"status": "error", "message": str(e)}


# ═══════════════════════════════════════════════════════════
# SECTION 3: Synthetic Heartbeat
# ═══════════════════════════════════════════════════════════

@router.get("/cockpit/synthetic")
def get_synthetic_heartbeat():
    """업무 흐름 alive 확인."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        scenarios = ["SYNTHETIC_LOGIN", "SYNTHETIC_PROCESS_REG"]
        results = []

        for jc in scenarios:
            # Last 5 runs
            runs = sb.table("cron_job_log") \
                .select("status,started_at,finished_at,duration_seconds,result_detail,result_summary") \
                .eq("job_code", jc) \
                .order("started_at", desc=True) \
                .limit(5).execute()

            last_success = None
            last_failure = None
            for r in (runs.data or []):
                if r["status"] == "SUCCESS" and not last_success:
                    last_success = r["finished_at"]
                if r["status"] in ("FAILED", "WARNING") and not last_failure:
                    last_failure = r["finished_at"]

            results.append({
                "job_code": jc,
                "scenario_name": jc.replace("SYNTHETIC_", "").lower(),
                "last_success": last_success,
                "last_failure": last_failure,
                "last_run": runs.data[0] if runs.data else None,
                "recent_runs": runs.data or [],
            })

        return {"status": "success", "data": results}
    except Exception as e:
        logger.error("Cockpit synthetic failed: %s", e)
        return {"status": "error", "message": str(e)}


# ═══════════════════════════════════════════════════════════
# SECTION 4: Scheduler Status
# ═══════════════════════════════════════════════════════════

@router.get("/cockpit/scheduler")
def get_scheduler_status():
    """Watch Engine scheduler job 상태."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        watch_jobs = ["INTEGRITY_EVALUATE", "SYNTHETIC_LOGIN", "SYNTHETIC_PROCESS_REG", "SYNTHETIC_CLEANUP"]
        results = []

        for jc in watch_jobs:
            # Job config
            job = sb.table("cron_job_master") \
                .select("job_code,job_name,cron_expression,is_active,endpoint_url") \
                .eq("job_code", jc).limit(1).execute()

            # Last run
            last = sb.table("cron_job_log") \
                .select("status,started_at,finished_at,duration_seconds,error_message,result_detail") \
                .eq("job_code", jc) \
                .order("started_at", desc=True) \
                .limit(1).execute()

            results.append({
                "job": job.data[0] if job.data else {"job_code": jc},
                "last_run": last.data[0] if last.data else None,
            })

        return {"status": "success", "data": results}
    except Exception as e:
        logger.error("Cockpit scheduler failed: %s", e)
        return {"status": "error", "message": str(e)}


# ═══════════════════════════════════════════════════════════
# SECTION 5: Top Failing Flows
# ═══════════════════════════════════════════════════════════

@router.get("/cockpit/top-failures")
def get_top_failing_flows(days: int = 7):
    """어디가 가장 위험한가."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # Get all active issues grouped by flow
        issues = sb.table("engine_integrity_event") \
            .select("flow_key,event_type,severity,created_at") \
            .eq("resolved", False) \
            .not_.is_("trace_id", "null") \
            .gte("created_at", since) \
            .order("created_at", desc=True) \
            .execute()

        # Aggregate
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

        # Sort by issue count
        ranked = sorted(flow_stats.values(), key=lambda x: x["issue_count"], reverse=True)

        # Format top_issue_type
        for r in ranked:
            if r["types"]:
                r["top_issue_type"] = max(r["types"], key=r["types"].get)
                r["top_issue_count"] = r["types"][r["top_issue_type"]]
            del r["types"]

        return {"status": "success", "data": ranked[:10]}
    except Exception as e:
        logger.error("Cockpit top-failures failed: %s", e)
        return {"status": "error", "message": str(e)}


# ═══════════════════════════════════════════════════════════
# Manual Evaluate (admin only)
# ═══════════════════════════════════════════════════════════

@router.post("/evaluate")
def run_integrity_evaluation():
    """Integrity Evaluator 수동 실행 (admin 전용)."""
    t0 = time.time()
    try:
        from watch_engine.integrity.evaluator import evaluate_recent_events
        result = evaluate_recent_events(last_minutes=10)
        elapsed_ms = int((time.time() - t0) * 1000)
        return {
            "status": "success",
            "message": "Integrity evaluation completed (manual)",
            "data": {**result, "duration_ms": elapsed_ms},
        }
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.error("Watch Engine evaluation failed: %s", e)
        return {"status": "error", "message": str(e), "data": {"errors": 1, "duration_ms": elapsed_ms}}
