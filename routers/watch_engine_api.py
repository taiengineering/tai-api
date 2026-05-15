# routers/watch_engine_api.py — Watch Engine 엔드포인트
"""
Watch Engine Admin API.

NOTE: Scheduler는 v1.1부터 direct call 사용 (HTTP self-call 제거).
      이 엔드포인트는 admin/수동 테스트 전용으로 유지.
"""

import logging
import time
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watch-engine", tags=["감시엔진"])


@router.post("/evaluate")
def run_integrity_evaluation():
    """Integrity Evaluator 수동 실행 (admin 전용).

    NOTE: 정기 실행은 scheduler.py에서 direct call로 처리.
    이 엔드포인트는 수동 디버깅/테스트 용도.
    """
    t0 = time.time()
    try:
        from watch_engine.integrity.evaluator import evaluate_recent_events

        result = evaluate_recent_events(last_minutes=10)
        elapsed_ms = int((time.time() - t0) * 1000)

        return {
            "status": "success",
            "message": "Integrity evaluation completed (manual)",
            "data": {
                "evaluated_traces": result.get("evaluated_traces", 0),
                "issues_found": result.get("issues_found", 0),
                "suppressed": result.get("suppressed", 0),
                "errors": result.get("errors", 0),
                "duration_ms": elapsed_ms,
            },
        }

    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.error("Watch Engine evaluation failed: %s", e)
        return {
            "status": "error",
            "message": f"Evaluation failed: {str(e)}",
            "data": {
                "evaluated_traces": 0,
                "issues_found": 0,
                "suppressed": 0,
                "errors": 1,
                "duration_ms": elapsed_ms,
            },
        }


@router.get("/status")
def get_watch_engine_status():
    """Watch Engine 현재 상태 요약."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        active = sb.table("engine_integrity_event") \
            .select("id", count="exact") \
            .eq("resolved", False) \
            .not_.is_("trace_id", "null") \
            .execute()

        from datetime import datetime, timezone, timedelta
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        recent = sb.table("business_event") \
            .select("id", count="exact") \
            .gte("created_at", since) \
            .execute()

        # Last evaluator run
        last_run = sb.table("cron_job_log") \
            .select("status,finished_at,result_detail") \
            .eq("job_code", "INTEGRITY_EVALUATE") \
            .order("started_at", desc=True) \
            .limit(1).execute()
        last = last_run.data[0] if last_run.data else None

        return {
            "status": "success",
            "data": {
                "active_integrity_issues": active.count,
                "business_events_24h": recent.count,
                "engine_version": "v1.1",
                "scheduler_mode": "direct",
                "last_evaluation": {
                    "status": last.get("status") if last else None,
                    "finished_at": last.get("finished_at") if last else None,
                    "detail": last.get("result_detail") if last else None,
                } if last else None,
            },
        }

    except Exception as e:
        logger.error("Watch Engine status failed: %s", e)
        return {"status": "error", "message": str(e)}
