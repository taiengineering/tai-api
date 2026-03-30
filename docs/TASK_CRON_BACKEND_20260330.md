# 크론 관리 시스템 — 백엔드 작업 지시서

## DB 테이블 (이미 생성 완료)
- `cron_job_master` — 크론 작업 마스터
- `cron_job_log` — 실행 로그
- `cron_schedule_config` — 스케줄 설정

---

## STEP 1. routers/cron_manager.py 생성

```python
# routers/cron_manager.py
import os, requests
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from db.database import get_supabase

router = APIRouter(prefix="/cron", tags=["크론 관리"])

class CronJobUpdate(BaseModel):
    cron_expression: Optional[str] = None
    is_active: Optional[bool] = None
    job_name: Optional[str] = None
    job_description: Optional[str] = None
    notify_on_fail: Optional[bool] = None

class CronJobCreate(BaseModel):
    job_code: str
    job_name: str
    job_description: Optional[str] = None
    category: str  # LAW/DATA/SYSTEM/REPORT
    endpoint_url: str
    http_method: str = "POST"
    cron_expression: str
    schedule_desc: str
    request_payload: Optional[dict] = None
    timeout_seconds: int = 300
    notify_on_fail: bool = True

@router.get("/jobs")
def list_jobs():
    """크론 작업 전체 목록 조회"""
    sb = get_supabase()
    jobs = sb.table("cron_job_master").select(
        "*, cron_schedule_config(last_run_at, next_run_at, last_status, is_enabled)"
    ).order("category").order("job_name").execute()
    return {"status": "success", "data": jobs.data}

@router.get("/jobs/{job_code}")
def get_job(job_code: str):
    """단일 크론 작업 조회"""
    sb = get_supabase()
    job = sb.table("cron_job_master").select("*").eq("job_code", job_code).single().execute()
    if not job.data:
        raise HTTPException(status_code=404, detail="크론 작업을 찾을 수 없습니다")
    logs = sb.table("cron_job_log").select("*") \
        .eq("job_code", job_code).order("started_at", desc=True).limit(20).execute()
    return {"status": "success", "data": job.data, "recent_logs": logs.data}

@router.post("/jobs")
def create_job(body: CronJobCreate):
    """크론 작업 신규 등록"""
    sb = get_supabase()
    job = sb.table("cron_job_master").insert(body.dict()).execute()
    if not job.data:
        raise HTTPException(status_code=500, detail="등록 실패")
    # schedule_config 동기화
    sb.table("cron_schedule_config").insert({
        "job_id": job.data[0]["id"],
        "job_code": body.job_code,
        "cron_expression": body.cron_expression,
    }).execute()
    return {"status": "success", "data": job.data[0]}

@router.patch("/jobs/{job_code}")
def update_job(job_code: str, body: CronJobUpdate):
    """크론 작업 수정"""
    sb = get_supabase()
    update_data = {k: v for k, v in body.dict().items() if v is not None}
    update_data["updated_at"] = datetime.now().isoformat()
    job = sb.table("cron_job_master") \
        .update(update_data).eq("job_code", job_code).execute()
    if body.cron_expression:
        sb.table("cron_schedule_config") \
            .update({"cron_expression": body.cron_expression, "updated_at": datetime.now().isoformat()}) \
            .eq("job_code", job_code).execute()
    return {"status": "success", "data": job.data}

@router.delete("/jobs/{job_code}")
def delete_job(job_code: str):
    """크론 작업 삭제 (is_system=true 불가)"""
    sb = get_supabase()
    job = sb.table("cron_job_master").select("is_system").eq("job_code", job_code).single().execute()
    if not job.data:
        raise HTTPException(status_code=404, detail="없는 작업")
    if job.data.get("is_system"):
        raise HTTPException(status_code=403, detail="시스템 크론은 삭제할 수 없습니다")
    sb.table("cron_job_master").delete().eq("job_code", job_code).execute()
    return {"status": "success", "message": f"{job_code} 삭제 완료"}

@router.post("/jobs/{job_code}/run")
def run_job_now(job_code: str, user_email: str = "admin"):
    """크론 수동 실행"""
    sb = get_supabase()
    job = sb.table("cron_job_master").select("*").eq("job_code", job_code).single().execute()
    if not job.data:
        raise HTTPException(status_code=404, detail="없는 작업")
    j = job.data
    # 로그 생성
    log = sb.table("cron_job_log").insert({
        "job_id": j["id"],
        "job_code": job_code,
        "triggered_by": "MANUAL",
        "triggered_by_user": user_email,
        "status": "RUNNING",
    }).execute()
    log_id = log.data[0]["id"]
    started = datetime.now()
    try:
        base_url = os.environ.get("INTERNAL_API_URL", "https://api.taieng.co.kr")
        url = base_url + j["endpoint_url"]
        method = j.get("http_method", "POST").upper()
        timeout = j.get("timeout_seconds", 300)
        payload = j.get("request_payload") or {}
        if method == "POST":
            resp = requests.post(url, json=payload, timeout=timeout)
        else:
            resp = requests.get(url, timeout=timeout)
        duration = (datetime.now() - started).total_seconds()
        status = "SUCCESS" if resp.status_code < 400 else "FAILED"
        result = {}
        try:
            result = resp.json()
        except Exception:
            pass
        sb.table("cron_job_log").update({
            "finished_at": datetime.now().isoformat(),
            "duration_seconds": duration,
            "status": status,
            "http_status_code": resp.status_code,
            "result_summary": str(result)[:500],
            "result_detail": result,
        }).eq("id", log_id).execute()
        sb.table("cron_schedule_config").update({
            "last_run_at": datetime.now().isoformat(),
            "last_status": status,
        }).eq("job_code", job_code).execute()
        return {"status": status, "duration": duration, "http_status": resp.status_code, "result": result}
    except Exception as e:
        duration = (datetime.now() - started).total_seconds()
        sb.table("cron_job_log").update({
            "finished_at": datetime.now().isoformat(),
            "duration_seconds": duration,
            "status": "FAILED",
            "error_message": str(e),
        }).eq("id", log_id).execute()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/logs")
def get_logs(job_code: str = None, status: str = None, limit: int = 50):
    """실행 로그 조회"""
    sb = get_supabase()
    q = sb.table("cron_job_log").select("*").order("started_at", desc=True).limit(limit)
    if job_code:
        q = q.eq("job_code", job_code)
    if status:
        q = q.eq("status", status)
    logs = q.execute()
    return {"status": "success", "data": logs.data}

@router.get("/stats")
def get_stats():
    """크론 전체 현황 통계"""
    sb = get_supabase()
    total = sb.table("cron_job_master").select("id", count="exact").execute()
    active = sb.table("cron_job_master").select("id", count="exact").eq("is_active", True).execute()
    today_logs = sb.table("cron_job_log").select("id", count="exact") \
        .gte("started_at", datetime.now().strftime("%Y-%m-%d")).execute()
    failed = sb.table("cron_job_log").select("id", count="exact") \
        .eq("status", "FAILED") \
        .gte("started_at", datetime.now().strftime("%Y-%m-%d")).execute()
    return {
        "total_jobs": total.count,
        "active_jobs": active.count,
        "today_runs": today_logs.count,
        "today_failed": failed.count,
    }
```

---

## STEP 2. main.py에 라우터 등록

```python
# main.py에 추가
from routers.cron_manager import router as cron_manager_router
...
app.include_router(cron_manager_router)
```

---

## STEP 3. APScheduler 연동 (scheduler.py)

```python
# scheduler.py — APScheduler + DB 동기화
import os, requests, logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from db.database import get_supabase

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="Asia/Seoul")

def execute_cron_job(job_code: str, endpoint_url: str, http_method: str, payload: dict, timeout: int):
    sb = get_supabase()
    log = sb.table("cron_job_log").insert({
        "job_code": job_code, "triggered_by": "SCHEDULE", "status": "RUNNING"
    }).execute()
    log_id = log.data[0]["id"]
    started = datetime.now()
    try:
        base_url = os.environ.get("INTERNAL_API_URL", "https://api.taieng.co.kr")
        url = base_url + endpoint_url
        resp = requests.post(url, json=payload or {}, timeout=timeout) \
            if http_method == "POST" else requests.get(url, timeout=timeout)
        duration = (datetime.now() - started).total_seconds()
        status = "SUCCESS" if resp.status_code < 400 else "FAILED"
        result = {}
        try: result = resp.json()
        except: pass
        sb.table("cron_job_log").update({
            "finished_at": datetime.now().isoformat(),
            "duration_seconds": duration,
            "status": status,
            "http_status_code": resp.status_code,
            "result_summary": str(result)[:300],
        }).eq("id", log_id).execute()
        sb.table("cron_schedule_config").update({
            "last_run_at": datetime.now().isoformat(),
            "last_status": status,
        }).eq("job_code", job_code).execute()
        logger.info(f"[CRON] {job_code} {status} ({duration:.1f}s)")
    except Exception as e:
        duration = (datetime.now() - started).total_seconds()
        sb.table("cron_job_log").update({
            "finished_at": datetime.now().isoformat(),
            "duration_seconds": duration,
            "status": "FAILED",
            "error_message": str(e),
        }).eq("id", log_id).execute()
        logger.error(f"[CRON] {job_code} FAILED: {e}")

def load_jobs_from_db():
    """DB에서 활성 크론 작업 로드 후 스케줄러에 등록"""
    sb = get_supabase()
    jobs = sb.table("cron_job_master").select("*").eq("is_active", True).execute()
    scheduler.remove_all_jobs()
    for j in (jobs.data or []):
        if not j.get("cron_expression"):
            continue
        try:
            parts = j["cron_expression"].split()
            trigger = CronTrigger(
                minute=parts[0], hour=parts[1],
                day=parts[2], month=parts[3], day_of_week=parts[4],
                timezone="Asia/Seoul"
            )
            scheduler.add_job(
                execute_cron_job,
                trigger=trigger,
                id=j["job_code"],
                args=[j["job_code"], j["endpoint_url"], j.get("http_method","POST"), j.get("request_payload"), j.get("timeout_seconds",300)],
                replace_existing=True
            )
            logger.info(f"[CRON] 등록: {j['job_code']} ({j['cron_expression']})")
        except Exception as e:
            logger.error(f"[CRON] 등록 실패 {j['job_code']}: {e}")
    logger.info(f"[CRON] 총 {len(scheduler.get_jobs())}개 작업 등록")

def start_scheduler():
    load_jobs_from_db()
    scheduler.start()
    logger.info("[CRON] 스케줄러 시작")
```

## STEP 4. main.py startup 이벤트에 스케줄러 연결

```python
# main.py에 추가
from scheduler import start_scheduler
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield

app = FastAPI(title="TAI API", version="4.3.0", lifespan=lifespan)
```

---

## STEP 5. git push
git add routers/cron_manager.py scheduler.py
git commit -m "feat: 크론 관리 시스템 — API + APScheduler + DB 연동"
git push origin main

## 완료 기준
- [ ] GET /cron/jobs 정상 응답
- [ ] POST /cron/jobs/{job_code}/run 수동 실행
- [ ] GET /cron/logs 로그 조회
- [ ] 스케줄러 시작 시 DB에서 크론 자동 로드
