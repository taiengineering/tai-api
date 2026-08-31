# routers/watch_engine_browser_api.py — Browser Synthetic API
"""
Browser Synthetic Coverage + Status API.
Cockpit UI에서 브라우저 감시 상태 확인.
"""

import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter
from services.time import now_kst

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watch-engine/browser", tags=["브라우저감시"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/status")
def get_browser_status():
    """Browser Synthetic 최근 상태 요약."""
    try:
        sb = _sb()
        registry = sb.table("browser_synthetic_registry") \
            .select("*").order("coverage_priority").execute()

        # 최근 cron 실행 결과
        browser_jobs = ["SYNTHETIC_BROWSER_LOGIN", "SYNTHETIC_BROWSER_PROCESS"]
        job_status = {}
        for jc in browser_jobs:
            last = sb.table("cron_job_log").select("status,finished_at,result_detail,duration_seconds") \
                .eq("job_code", jc).order("started_at", desc=True).limit(1).execute()
            job_status[jc] = last.data[0] if last.data else None

        # 최근 24h browser business_event 통계
        since = (now_kst() - timedelta(hours=24)).isoformat()
        events_24h = sb.table("business_event") \
            .select("flow_key,result", count="exact") \
            .eq("connector_type", "browser") \
            .eq("actor_type", "synthetic_user") \
            .gte("created_at", since).execute()

        total = events_24h.count or 0
        success = sum(1 for e in (events_24h.data or []) if e.get("result") == "success")
        rate = round((success / total * 100), 1) if total > 0 else None

        return {
            "status": "success",
            "data": {
                "registry": registry.data or [],
                "scheduler": job_status,
                "events_24h": total,
                "success_rate_24h": rate,
            }
        }
    except Exception as e:
        logger.error("Browser status: %s", e)
        return {"status": "error", "message": str(e)}


@router.get("/coverage")
def get_browser_coverage():
    """Browser Synthetic Coverage 목록."""
    try:
        sb = _sb()
        resp = sb.table("browser_synthetic_registry") \
            .select("*").order("coverage_priority,flow_key").execute()

        # 각 flow별 최근 성공/실패 시간 계산
        enriched = []
        for row in (resp.data or []):
            fk = row["flow_key"]
            # 최근 성공
            last_ok = sb.table("business_event") \
                .select("created_at") \
                .eq("flow_key", fk).eq("connector_type", "browser") \
                .eq("actor_type", "synthetic_user").eq("result", "success") \
                .order("created_at", desc=True).limit(1).execute()
            # 최근 실패
            last_fail = sb.table("business_event") \
                .select("created_at,payload_summary") \
                .eq("flow_key", fk).eq("connector_type", "browser") \
                .eq("actor_type", "synthetic_user").eq("result", "failure") \
                .order("created_at", desc=True).limit(1).execute()

            row["last_browser_success_at"] = last_ok.data[0]["created_at"] if last_ok.data else None
            row["last_browser_failure_at"] = last_fail.data[0]["created_at"] if last_fail.data else None
            if last_fail.data:
                ps = last_fail.data[0].get("payload_summary") or {}
                row["last_error_type"] = ps.get("error")

            enriched.append(row)

        return {"status": "success", "data": enriched}
    except Exception as e:
        logger.error("Browser coverage: %s", e)
        return {"status": "error", "message": str(e)}
