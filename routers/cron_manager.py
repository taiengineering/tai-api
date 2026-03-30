# routers/cron_manager.py — 크론 관리 API
import os, requests
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from db.database import get_supabase

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
    category:        str                      # LAW / DATA / SYSTEM / REPORT
    endpoint_url:    str
    http_method:     str = "POST"
    cron_expression: str
    schedule_desc:   str
    request_payload: Optional[dict] = None
    timeout_seconds: int = 300
    notify_on_fail:  bool = True


# ── 목록 ─────────────────────────────────────────────────
@router.get("/jobs")
def list_jobs():
    sb = get_supabase()
    jobs = sb.table("cron_job_master").select(
        "*, cron_schedule_config(last_run_at, next_run_at, last_status, is_enabled)"
    ).order("category").order("job_name").execute()
    return {"status": "success", "data": jobs.data}


# ── 단건 조회 ────────────────────────────────────────────
@router.get("/jobs/{job_code}")
def get_job(job_code: str):
    sb = get_supabase()
    job = sb.table("cron_job_master").select("*").eq("job_code", job_code).single().execute()
    if not job.data:
        raise HTTPException(status_code=404, detail="크론 작업을 찾을 수 없습니다")
    logs = sb.table("cron_job_log").select("*") \
        .eq("job_code", job_code).order("started_at", desc=True).limit(20).execute()
    return {"status": "success", "data": job.data, "recent_logs": logs.data}


# ── 신규 등록 ────────────────────────────────────────────
@router.post("/jobs")
def create_job(body: CronJobCreate):
    sb = get_supabase()
    job = sb.table("cron_job_master").insert(body.dict()).execute()
    if not job.data:
        raise HTTPException(status_code=500, detail="등록 실패")
    sb.table("cron_schedule_config").insert({
        "job_id":          job.data[0]["id"],
        "job_code":        body.job_code,
        "cron_expression": body.cron_expression,
    }).execute()
    # 스케줄러 리로드
    try:
        from scheduler import load_jobs_from_db
        load_jobs_from_db()
    except Exception:
        pass
    return {"status": "success", "data": job.data[0]}


# ── 수정 ────────────────────────────────────────────────
@router.patch("/jobs/{job_code}")
def update_job(job_code: str, body: CronJobUpdate):
    sb = get_supabase()
    update_data = {k: v for k, v in body.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now().isoformat()
    job = sb.table("cron_job_master") \
        .update(update_data).eq("job_code", job_code).execute()
    if body.cron_expression:
        sb.table("cron_schedule_config") \
            .update({"cron_expression": body.cron_expression,
                     "updated_at": datetime.now().isoformat()}) \
            .eq("job_code", job_code).execute()
    # 스케줄러 리로드
    try:
        from scheduler import load_jobs_from_db
        load_jobs_from_db()
    except Exception:
        pass
    return {"status": "success", "data": job.data}


# ── 삭제 ────────────────────────────────────────────────
@router.delete("/jobs/{job_code}")
def delete_job(job_code: str):
    sb = get_supabase()
    job = sb.table("cron_job_master").select("is_system").eq("job_code", job_code).single().execute()
    if not job.data:
        raise HTTPException(status_code=404, detail="없는 작업")
    if job.data.get("is_system"):
        raise HTTPException(status_code=403, detail="시스템 크론은 삭제할 수 없습니다")
    sb.table("cron_job_master").delete().eq("job_code", job_code).execute()
    return {"status": "success", "message": f"{job_code} 삭제 완료"}


# ── 수동 실행 ────────────────────────────────────────────
@router.post("/jobs/{job_code}/run")
def run_job_now(job_code: str, user_email: str = "admin"):
    sb = get_supabase()
    job = sb.table("cron_job_master").select("*").eq("job_code", job_code).single().execute()
    if not job.data:
        raise HTTPException(status_code=404, detail="없는 작업")
    j = job.data

    log = sb.table("cron_job_log").insert({
        "job_id":            j["id"],
        "job_code":          job_code,
        "triggered_by":      "MANUAL",
        "triggered_by_user": user_email,
        "status":            "RUNNING",
    }).execute()
    log_id  = log.data[0]["id"]
    started = datetime.now()

    try:
        base_url = os.environ.get("INTERNAL_API_URL", "https://api.taieng.co.kr")
        url      = base_url + j["endpoint_url"]
        method   = j.get("http_method", "POST").upper()
        timeout  = j.get("timeout_seconds", 300)
        payload  = j.get("request_payload") or {}

        resp = requests.post(url, json=payload, timeout=timeout) \
            if method == "POST" else requests.get(url, timeout=timeout)
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
        sb.table("cron_schedule_config").update({
            "last_run_at": datetime.now().isoformat(),
            "last_status": status,
        }).eq("job_code", job_code).execute()

        return {"status": status, "duration": duration,
                "http_status": resp.status_code, "result": result}

    except Exception as e:
        duration = (datetime.now() - started).total_seconds()
        sb.table("cron_job_log").update({
            "finished_at":    datetime.now().isoformat(),
            "duration_seconds": duration,
            "status":         "FAILED",
            "error_message":  str(e),
        }).eq("id", log_id).execute()
        raise HTTPException(status_code=500, detail=str(e))


# ── 스케줄러 리로드 ───────────────────────────────────────
@router.post("/reload")
def reload_scheduler():
    try:
        from scheduler import load_jobs_from_db
        load_jobs_from_db()
        return {"status": "success", "message": "스케줄러 리로드 완료"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 로그 조회 ────────────────────────────────────────────
@router.get("/logs")
def get_logs(job_code: str = None, status: str = None, limit: int = 50):
    sb  = get_supabase()
    q   = sb.table("cron_job_log").select("*").order("started_at", desc=True).limit(limit)
    if job_code:
        q = q.eq("job_code", job_code)
    if status:
        q = q.eq("status", status)
    logs = q.execute()
    return {"status": "success", "data": logs.data}


# ── 통계 ─────────────────────────────────────────────────
@router.get("/stats")
def get_stats():
    sb     = get_supabase()
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
