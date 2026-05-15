# routers/watch_engine_api.py — Watch Engine 엔드포인트
"""
Integrity Evaluator scheduler 연결용 API.
scheduler.py가 이 엔드포인트를 주기적으로 호출.
"""

import logging
import time
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watch-engine", tags=["감시엔진"])


@router.post("/evaluate")
def run_integrity_evaluation():
    """Integrity Evaluator 실행.

    scheduler 또는 수동 호출 가능.
    실패해도 서비스 영향 없음 (fail-safe).
    """
    t0 = time.time()
    try:
        from watch_engine.integrity.evaluator import evaluate_recent_events

        result = evaluate_recent_events(last_minutes=10)
        elapsed_ms = int((time.time() - t0) * 1000)

        return {
            "status": "success",
            "message": "Integrity evaluation completed",
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

        # 최근 integrity events
        active = sb.table("engine_integrity_event") \
            .select("id", count="exact") \
            .eq("resolved", False) \
            .not_.is_("trace_id", "null") \
            .execute()

        # 최근 business events (24h)
        from datetime import datetime, timezone, timedelta
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        recent = sb.table("business_event") \
            .select("id", count="exact") \
            .gte("created_at", since) \
            .execute()

        return {
            "status": "success",
            "data": {
                "active_integrity_issues": active.count,
                "business_events_24h": recent.count,
                "engine_version": "v1.1",
            },
        }

    except Exception as e:
        logger.error("Watch Engine status failed: %s", e)
        return {"status": "error", "message": str(e)}
