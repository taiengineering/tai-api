# scheduler.py — APScheduler + DB 연동 크론 스케줄러
import os, requests, logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger    = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="Asia/Seoul")


def execute_cron_job(job_code: str, endpoint_url: str,
                     http_method: str, payload: dict, timeout: int):
    """크론 작업 실행 + 로그 기록"""
    from db.database import get_supabase
    sb = get_supabase()

    log = sb.table("cron_job_log").insert({
        "job_code":     job_code,
        "triggered_by": "SCHEDULE",
        "status":       "RUNNING",
    }).execute()
    log_id  = log.data[0]["id"]
    started = datetime.now()

    try:
        base_url = os.environ.get("INTERNAL_API_URL", "https://api.taieng.co.kr")
        url      = base_url + endpoint_url
        method   = (http_method or "POST").upper()
        resp     = requests.post(url, json=payload or {}, timeout=timeout) \
            if method == "POST" else requests.get(url, timeout=timeout)
        duration = (datetime.now() - started).total_seconds()
        status   = "SUCCESS" if resp.status_code < 400 else "FAILED"
        result   = {}
        try:
            result = resp.json()
        except Exception:
            pass

        sb.table("cron_job_log").update({
            "finished_at":      datetime.now().isoformat(),
            "duration_seconds": duration,
            "status":           status,
            "http_status_code": resp.status_code,
            "result_summary":   str(result)[:300],
        }).eq("id", log_id).execute()
        sb.table("cron_schedule_config").update({
            "last_run_at": datetime.now().isoformat(),
            "last_status": status,
        }).eq("job_code", job_code).execute()
        logger.info(f"[CRON] {job_code} {status} ({duration:.1f}s)")

    except Exception as e:
        duration = (datetime.now() - started).total_seconds()
        sb.table("cron_job_log").update({
            "finished_at":      datetime.now().isoformat(),
            "duration_seconds": duration,
            "status":           "FAILED",
            "error_message":    str(e),
        }).eq("id", log_id).execute()
        logger.error(f"[CRON] {job_code} FAILED: {e}")


def load_jobs_from_db():
    """DB에서 활성 크론 작업 로드 후 스케줄러 등록"""
    from db.database import get_supabase
    sb   = get_supabase()
    jobs = sb.table("cron_job_master").select("*").eq("is_active", True).execute()

    scheduler.remove_all_jobs()
    registered = 0
    for j in (jobs.data or []):
        expr = j.get("cron_expression", "")
        if not expr:
            continue
        try:
            parts   = expr.strip().split()
            trigger = CronTrigger(
                minute=parts[0], hour=parts[1],
                day=parts[2],    month=parts[3],
                day_of_week=parts[4],
                timezone="Asia/Seoul"
            )
            scheduler.add_job(
                execute_cron_job,
                trigger=trigger,
                id=j["job_code"],
                args=[
                    j["job_code"],
                    j["endpoint_url"],
                    j.get("http_method", "POST"),
                    j.get("request_payload"),
                    j.get("timeout_seconds", 300),
                ],
                replace_existing=True,
            )
            registered += 1
            logger.info(f"[CRON] 등록: {j['job_code']} ({expr})")
        except Exception as e:
            logger.error(f"[CRON] 등록 실패 {j['job_code']}: {e}")

    logger.info(f"[CRON] 총 {registered}개 작업 등록")


def start_scheduler():
    """스케줄러 시작"""
    try:
        load_jobs_from_db()
        if not scheduler.running:
            scheduler.start()
        logger.info("[CRON] 스케줄러 시작 완료")
    except Exception as e:
        logger.error(f"[CRON] 스케줄러 시작 실패: {e}")
