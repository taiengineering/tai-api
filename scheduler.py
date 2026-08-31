# scheduler.py — DB-backed KST dispatcher (WP-TIME-SCHEDULER-C-01)
# Business jobs are not registered into APScheduler memory.
# Occurrence identity = (job_code, scheduled_for=persisted next_run_at).
import logging

from services.time import now_kst, serialize_business_datetime
from services.scheduler.handlers import (
    DIRECT_HANDLERS,
    execute_direct as _handlers_execute_direct,
    register_direct_handlers as _register_handlers_impl,
)

logger = logging.getLogger(__name__)

# Kept for tests/cron_manager that patch `scheduler.scheduler`.
# Business jobs are not registered here; get_jobs() is empty by design.
class _DispatcherHandle:
    def __init__(self):
        self.running = False

    def start(self):
        from scheduler_worker import start_dispatcher_thread
        start_dispatcher_thread()
        self.running = True

    def get_jobs(self):
        return []


scheduler = _DispatcherHandle()


def _register_direct_handlers():
    _register_handlers_impl()
    return DIRECT_HANDLERS


def execute_cron_job(job_code, endpoint_url, http_method, payload, timeout):
    from db.database import get_supabase
    sb = get_supabase()
    log = sb.table("cron_job_log").insert({"job_code": job_code, "triggered_by": "SCHEDULE", "status": "RUNNING"}).execute()
    log_id = log.data[0]["id"]
    started = now_kst()
    try:
        if endpoint_url and endpoint_url.startswith("direct://"):
            result = _execute_direct(endpoint_url, payload or {})
            duration = (now_kst() - started).total_seconds()
            errors = result.get("errors", 0) if isinstance(result, dict) else 0
            status = "WARNING" if errors > 0 else "SUCCESS"
            summary = _build_summary(result)
            sb.table("cron_job_log").update({
                "finished_at": serialize_business_datetime(now_kst()),
                "duration_seconds": duration,
                "status": status,
                "result_summary": summary[:500],
                "result_detail": result if isinstance(result, dict) else {"raw": str(result)},
            }).eq("id", log_id).execute()
            sb.table("cron_schedule_config").update({
                "last_run_at": serialize_business_datetime(now_kst()),
                "last_status": status,
            }).eq("job_code", job_code).execute()
            logger.info(f"[CRON] {job_code} {status} ({duration:.1f}s) [DIRECT]")
            return
        import os
        import requests
        base_url = os.environ.get("INTERNAL_API_URL", "https://api.taieng.co.kr")
        url = base_url + endpoint_url
        method = (http_method or "POST").upper()
        resp = requests.post(url, json=payload or {}, timeout=timeout) if method == "POST" else requests.get(url, timeout=timeout)
        duration = (now_kst() - started).total_seconds()
        status = "SUCCESS" if resp.status_code < 400 else "FAILED"
        result = {}
        try:
            result = resp.json()
        except Exception:
            pass
        sb.table("cron_job_log").update({
            "finished_at": serialize_business_datetime(now_kst()),
            "duration_seconds": duration,
            "status": status,
            "http_status_code": resp.status_code,
            "result_summary": str(result)[:300],
        }).eq("id", log_id).execute()
        sb.table("cron_schedule_config").update({
            "last_run_at": serialize_business_datetime(now_kst()),
            "last_status": status,
        }).eq("job_code", job_code).execute()
        logger.info(f"[CRON] {job_code} {status} ({duration:.1f}s)")
    except Exception as e:
        duration = (now_kst() - started).total_seconds()
        sb.table("cron_job_log").update({
            "finished_at": serialize_business_datetime(now_kst()),
            "duration_seconds": duration,
            "status": "FAILED",
            "error_message": str(e)[:1000],
        }).eq("id", log_id).execute()
        logger.error(f"[CRON] {job_code} FAILED: {e}")


def _execute_direct(endpoint_url, payload):
    _register_direct_handlers()
    return _handlers_execute_direct(endpoint_url, payload or {})


def _build_summary(result):
    if not isinstance(result, dict):
        return str(result)
    parts = []
    if "evaluated_traces" in result:
        parts.append(f"{result['evaluated_traces']} traces")
        if result.get("issues_found", 0) > 0:
            parts.append(f"{result['issues_found']} issues")
    if "scenario_run_id" in result:
        parts.append(f"run={result['scenario_run_id']}")
        parts.append(f"{result.get('passed', 0)} passed")
        if result.get("failed", 0) > 0:
            parts.append(f"{result['failed']} failed")
    if "business_events_deleted" in result:
        total = sum(result.get(k, 0) for k in ("business_events_deleted", "integrity_events_deleted", "service_data_deleted"))
        parts.append(f"{total} cleaned")
    if "alerts_sent" in result:
        parts.append(f"{result['alerts_sent']} alerts")
    if "detected" in result:
        parts.append(f"{result['detected']} repeated, {result.get('created', 0)} created")
    if "patterns_updated" in result:
        parts.append(f"{result['patterns_updated']} updated, {result.get('patterns_created', 0)} new")
    if result.get("suppressed", 0) > 0:
        parts.append(f"{result['suppressed']} suppressed")
    if result.get("errors", 0) > 0:
        parts.append(f"{result['errors']} errors")
    if "processed" in result and "sent" in result:
        parts.append(f"{result['processed']} processed, {result['sent']} sent")
    if "health_score" in result:
        parts.append(f"health={result['health_score']}")
    if "tenants" in result and "workflows" in result:
        parts.append(f"{result['tenants']}t {result['workflows']}wf {result.get('events', 0)}ev {result.get('chaos', 0)}chaos")
    if "evaluated" in result and "projected" in result:
        parts.append(f"{result['evaluated']}eval {result['projected']}proj {result.get('escalation', 0)}esc")
    return ", ".join(parts) if parts else "No activity"


def load_jobs_from_db():
    """No-op: dispatcher reads cron_job_master each tick. Memory registration = 0."""
    logger.info("[CRON] load_jobs_from_db skipped (DB-backed KST dispatcher)")


def start_scheduler():
    try:
        scheduler.start()
        logger.info("[CRON] KST dispatcher thread started")
    except Exception as e:
        logger.error(f"[CRON] 스케줄러 시작 실패: {e}")
