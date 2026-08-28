# routers/cron_manager.py — 크론 관리 API v3
# v3 (§83 G-mtcrc6ot-ab95bd): /cron/* 전부 platform ALL(_require_admin) 전용.
#   MANUAL RUN audit identity = current.email or current.id (client user_email 불신).
# v2: reload시 scheduler.start() 포함, DIRECT handler 수동실행 지원
import os, logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from db.database import get_supabase
from routers.auth import get_current_user
from services.company_scope import _require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cron", tags=["크론 관리"])


class CronJobUpdate(BaseModel):
    cron_expression: Optional[str] = None
    is_active:       Optional[bool] = None
    job_name:        Optional[str] = None
    job_description: Optional[str] = None
    notify_on_fail:  Optional[bool] = None
    schedule_desc:   Optional[str] = None


class CronJobCreate(BaseModel):
    job_code:        str
    job_name:        str
    job_description: Optional[str] = None
    category:        str
    endpoint_url:    str
    http_method:     str = "POST"
    cron_expression: str
    schedule_desc:   str
    request_payload: Optional[dict] = None
    timeout_seconds: int = 300
    notify_on_fail:  bool = True


# ── 목록
@router.get("/jobs")
def list_jobs(current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _require_admin(current, sb)
    jobs = sb.table("cron_job_master").select(
        "*, cron_schedule_config(last_run_at, next_run_at, last_status, is_enabled)"
    ).order("category").order("job_name").execute()
    return {"status": "success", "data": jobs.data}


# ── 단건 조회
@router.get("/jobs/{job_code}")
def get_job(job_code: str, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _require_admin(current, sb)
    job = sb.table("cron_job_master").select("*").eq("job_code", job_code).single().execute()
    if not job.data:
        raise HTTPException(status_code=404, detail="크론 작업을 찾을 수 없습니다")
    logs = sb.table("cron_job_log").select("*") \
        .eq("job_code", job_code).order("started_at", desc=True).limit(20).execute()
    return {"status": "success", "data": job.data, "recent_logs": logs.data}


# ── 신규 등록
@router.post("/jobs")
def create_job(body: CronJobCreate, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _require_admin(current, sb)
    job = sb.table("cron_job_master").insert(body.dict()).execute()
    if not job.data:
        raise HTTPException(status_code=500, detail="등록 실패")
    sb.table("cron_schedule_config").insert({
        "job_id":          job.data[0]["id"],
        "job_code":        body.job_code,
        "cron_expression": body.cron_expression,
    }).execute()
    try:
        from scheduler import load_jobs_from_db
        load_jobs_from_db()
    except Exception:
        pass
    return {"status": "success", "data": job.data[0]}


# ── 수정
@router.patch("/jobs/{job_code}")
def update_job(job_code: str, body: CronJobUpdate, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _require_admin(current, sb)
    update_data = {k: v for k, v in body.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now().isoformat()
    job = sb.table("cron_job_master") \
        .update(update_data).eq("job_code", job_code).execute()
    if body.cron_expression:
        sb.table("cron_schedule_config") \
            .update({"cron_expression": body.cron_expression,
                     "updated_at": datetime.now().isoformat()}) \
            .eq("job_code", job_code).execute()
    try:
        from scheduler import load_jobs_from_db
        load_jobs_from_db()
    except Exception:
        pass
    return {"status": "success", "data": job.data}


# ── 삭제
@router.delete("/jobs/{job_code}")
def delete_job(job_code: str, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _require_admin(current, sb)
    job = sb.table("cron_job_master").select("is_system").eq("job_code", job_code).single().execute()
    if not job.data:
        raise HTTPException(status_code=404, detail="없는 작업")
    if job.data.get("is_system"):
        raise HTTPException(status_code=403, detail="시스템 크론은 삭제할 수 없습니다")
    sb.table("cron_job_master").delete().eq("job_code", job_code).execute()
    return {"status": "success", "message": f"{job_code} 삭제 완료"}


# ── 수동 실행 (HTTP + DIRECT 지원)
@router.post("/jobs/{job_code}/run")
def run_job_now(job_code: str, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _require_admin(current, sb)
    job = sb.table("cron_job_master").select("*").eq("job_code", job_code).single().execute()
    if not job.data:
        raise HTTPException(status_code=404, detail="없는 작업")
    j = job.data
    audit_user = current.get("email") or str(current["id"])

    log = sb.table("cron_job_log").insert({
        "job_code":          job_code,
        "triggered_by":      "MANUAL",
        "triggered_by_user": audit_user,
        "status":            "RUNNING",
    }).execute()
    log_id  = log.data[0]["id"]
    started = datetime.now()

    try:
        endpoint_url = j["endpoint_url"]

        # DIRECT handler 지원
        if endpoint_url and endpoint_url.startswith("direct://"):
            from scheduler import _execute_direct
            payload = j.get("request_payload") or {}
            result = _execute_direct(endpoint_url, payload)
            duration = (datetime.now() - started).total_seconds()

            errors = 0
            if isinstance(result, dict):
                errors = result.get("errors", 0)
            status = "WARNING" if errors > 0 else "SUCCESS"

            sb.table("cron_job_log").update({
                "finished_at":      datetime.now().isoformat(),
                "duration_seconds": duration,
                "status":           status,
                "result_summary":   str(result)[:500],
                "result_detail":    result if isinstance(result, dict) else {"raw": str(result)},
            }).eq("id", log_id).execute()
            try:
                sb.table("cron_schedule_config").update({
                    "last_run_at": datetime.now().isoformat(),
                    "last_status": status,
                }).eq("job_code", job_code).execute()
            except Exception:
                pass
            logger.info(f"[CRON] MANUAL {job_code} {status} ({duration:.1f}s) [DIRECT]")
            return {"status": status, "duration": duration, "result": result}

        # HTTP handler
        import requests as req
        base_url = os.environ.get("INTERNAL_API_URL", "https://api.taieng.co.kr")
        url      = base_url + endpoint_url
        method   = j.get("http_method", "POST").upper()
        timeout  = j.get("timeout_seconds", 300)
        payload  = j.get("request_payload") or {}

        resp = req.post(url, json=payload, timeout=timeout) \
            if method == "POST" else req.get(url, timeout=timeout)
        duration = (datetime.now() - started).total_seconds()
        status   = "SUCCESS" if resp.status_code < 400 else "FAILED"
        result   = {}
        try:
            result = resp.json()
        except Exception:
            pass

        sb.table("cron_job_log").update({
            "finished_at":    datetime.now().isoformat(),
            "duration_seconds": duration,
            "status":         status,
            "http_status_code": resp.status_code,
            "result_summary": str(result)[:500],
            "result_detail":  result,
        }).eq("id", log_id).execute()
        try:
            sb.table("cron_schedule_config").update({
                "last_run_at": datetime.now().isoformat(),
                "last_status": status,
            }).eq("job_code", job_code).execute()
        except Exception:
            pass

        return {"status": status, "duration": duration,
                "http_status": resp.status_code, "result": result}

    except Exception as e:
        duration = (datetime.now() - started).total_seconds()
        sb.table("cron_job_log").update({
            "finished_at":    datetime.now().isoformat(),
            "duration_seconds": duration,
            "status":         "FAILED",
            "error_message":  str(e)[:1000],
        }).eq("id", log_id).execute()
        raise HTTPException(status_code=500, detail=str(e))


# ── 스케줄러 리로드 + 시작
@router.post("/reload")
def reload_scheduler(current: dict = Depends(get_current_user)):
    """스케줄러 리로드 + 미실행시 시작."""
    _require_admin(current, get_supabase())
    try:
        from scheduler import load_jobs_from_db, scheduler
        load_jobs_from_db()
        if not scheduler.running:
            scheduler.start()
            logger.info("[CRON] 스케줄러 시작됨 (reload)")
        return {"status": "success", "message": "스케줄러 리로드 완료",
                "scheduler_running": scheduler.running}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 스케줄러 상태
@router.get("/scheduler-status")
def get_scheduler_status(current: dict = Depends(get_current_user)):
    """APScheduler 실행 상태 확인 (admin cron-list UI)."""
    sb = get_supabase()
    _require_admin(current, sb)
    try:
        from scheduler import scheduler
        active = sb.table("cron_job_master").select("id", count="exact").eq("is_active", True).execute()
        jobs = scheduler.get_jobs()
        return {
            "status": "success",
            "data": {
                "scheduler_running": bool(scheduler.running),
                "registered_jobs": len(jobs),
                "active_count": active.count or 0,
            },
            "jobs": [{"id": j.id, "next_run": str(j.next_run_time)} for j in jobs],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 로그 조회
@router.get("/logs")
def get_logs(job_code: str = None, status: str = None, limit: int = 50,
             current: dict = Depends(get_current_user)):
    sb  = get_supabase()
    _require_admin(current, sb)
    q   = sb.table("cron_job_log").select("*").order("started_at", desc=True).limit(limit)
    if job_code:
        q = q.eq("job_code", job_code)
    if status:
        q = q.eq("status", status)
    logs = q.execute()
    return {"status": "success", "data": logs.data}


# ── 통계
@router.get("/stats")
def get_stats(current: dict = Depends(get_current_user)):
    sb     = get_supabase()
    _require_admin(current, sb)
    today  = datetime.now().strftime("%Y-%m-%d")
    total  = sb.table("cron_job_master").select("id", count="exact").execute()
    active = sb.table("cron_job_master").select("id", count="exact").eq("is_active", True).execute()
    today_runs = sb.table("cron_job_log").select("id", count="exact").gte("started_at", today).execute()
    failed     = sb.table("cron_job_log").select("id", count="exact") \
        .eq("status", "FAILED").gte("started_at", today).execute()
    running    = sb.table("cron_job_log").select("id", count="exact").eq("status", "RUNNING").execute()
    return {
        "total_jobs":   total.count,
        "active_jobs":  active.count,
        "today_runs":   today_runs.count,
        "today_failed": failed.count,
        "running":      running.count,
    }
