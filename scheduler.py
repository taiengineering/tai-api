# scheduler.py — APScheduler + DB 연동 크론 스케줄러 v2.0
# v2.0: Control Bridge handler (TASK 45)
import os, logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger    = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="Asia/Seoul")

DIRECT_HANDLERS = {}


def _register_direct_handlers():
    global DIRECT_HANDLERS
    if DIRECT_HANDLERS:
        return

    def _run_integrity_evaluate(p): 
        from watch_engine.integrity.evaluator import evaluate_recent_events
        return evaluate_recent_events(last_minutes=p.get("last_minutes", 10))
    def _run_synthetic_login(p):
        from watch_engine.synthetic.runner import run_synthetic
        return run_synthetic(scenarios=["login"])
    def _run_synthetic_process_reg(p):
        from watch_engine.synthetic.runner import run_synthetic
        return run_synthetic(scenarios=["process_registration"])
    def _run_synthetic_cleanup(p):
        from watch_engine.synthetic.cleanup import cleanup_synthetic_data
        return cleanup_synthetic_data(event_retention_days=p.get("event_retention_days",7), service_data_retention_hours=p.get("service_data_retention_hours",24))
    def _run_alert_evaluate(p):
        from watch_engine.alert.engine import evaluate_and_alert
        return evaluate_and_alert()
    def _run_browser_synthetic_login(p):
        from watch_engine.browser_synthetic.runner import run_browser_synthetic
        return run_browser_synthetic(scenarios=["login_browser"])
    def _run_browser_synthetic_process(p):
        from watch_engine.browser_synthetic.runner import run_browser_synthetic
        return run_browser_synthetic(scenarios=["process_registration_browser"])
    def _run_incident_repeated(p):
        from watch_engine.incident.repeated import detect_repeated_failures
        from db.supabase_client import get_supabase
        return detect_repeated_failures(get_supabase())
    def _run_pattern_sync(p):
        from watch_engine.knowledge.pattern_updater import update_patterns
        return update_patterns(window_hours=p.get("window_hours", 24))
    def _run_notification_queue_worker(p):
        from services.notification_engine.worker import process_queue
        return process_queue(limit=p.get("limit", 50))
    def _run_notification_collect_metrics(p):
        from services.notification_engine.metrics_aggregator import collect_and_record
        return collect_and_record(window_minutes=p.get("window_minutes", 10))
    def _run_synthetic_runtime_tick(p):
        from watch_engine.synthetic_runtime.orchestrator import run_synthetic_tick
        return run_synthetic_tick()
    def _run_synthetic_chaos_injection(p):
        from watch_engine.synthetic_runtime.orchestrator import run_synthetic_tick
        return run_synthetic_tick()
    def _run_control_bridge_evaluate(p):
        from watch_engine.control_bridge.bridge_evaluator import evaluate_bridge
        return evaluate_bridge(window_minutes=p.get("window_minutes", 5), include_mock=True)

    DIRECT_HANDLERS = {
        "direct://integrity_evaluate": _run_integrity_evaluate,
        "direct://synthetic_login": _run_synthetic_login,
        "direct://synthetic_process_reg": _run_synthetic_process_reg,
        "direct://synthetic_cleanup": _run_synthetic_cleanup,
        "direct://alert_evaluate": _run_alert_evaluate,
        "direct://browser_synthetic_login": _run_browser_synthetic_login,
        "direct://browser_synthetic_process": _run_browser_synthetic_process,
        "direct://incident_repeated": _run_incident_repeated,
        "direct://pattern_sync": _run_pattern_sync,
        "direct://notification_queue_worker": _run_notification_queue_worker,
        "direct://notification_collect_metrics": _run_notification_collect_metrics,
        "direct://synthetic_runtime_tick": _run_synthetic_runtime_tick,
        "direct://synthetic_chaos_injection": _run_synthetic_chaos_injection,
        "direct://control_bridge_evaluate": _run_control_bridge_evaluate,
    }


def execute_cron_job(job_code, endpoint_url, http_method, payload, timeout):
    from db.database import get_supabase
    sb = get_supabase()
    log = sb.table("cron_job_log").insert({"job_code":job_code,"triggered_by":"SCHEDULE","status":"RUNNING"}).execute()
    log_id = log.data[0]["id"]
    started = datetime.now()
    try:
        if endpoint_url and endpoint_url.startswith("direct://"):
            result = _execute_direct(endpoint_url, payload or {})
            duration = (datetime.now()-started).total_seconds()
            errors = result.get("errors",0) if isinstance(result,dict) else 0
            status = "WARNING" if errors>0 else "SUCCESS"
            summary = _build_summary(result)
            sb.table("cron_job_log").update({"finished_at":datetime.now().isoformat(),"duration_seconds":duration,"status":status,"result_summary":summary[:500],"result_detail":result if isinstance(result,dict) else {"raw":str(result)}}).eq("id",log_id).execute()
            sb.table("cron_schedule_config").update({"last_run_at":datetime.now().isoformat(),"last_status":status}).eq("job_code",job_code).execute()
            logger.info(f"[CRON] {job_code} {status} ({duration:.1f}s) [DIRECT]")
            return
        import requests
        base_url = os.environ.get("INTERNAL_API_URL","https://api.taieng.co.kr")
        url = base_url+endpoint_url
        method = (http_method or "POST").upper()
        resp = requests.post(url,json=payload or {},timeout=timeout) if method=="POST" else requests.get(url,timeout=timeout)
        duration = (datetime.now()-started).total_seconds()
        status = "SUCCESS" if resp.status_code<400 else "FAILED"
        result = {}
        try: result=resp.json()
        except: pass
        sb.table("cron_job_log").update({"finished_at":datetime.now().isoformat(),"duration_seconds":duration,"status":status,"http_status_code":resp.status_code,"result_summary":str(result)[:300]}).eq("id",log_id).execute()
        sb.table("cron_schedule_config").update({"last_run_at":datetime.now().isoformat(),"last_status":status}).eq("job_code",job_code).execute()
        logger.info(f"[CRON] {job_code} {status} ({duration:.1f}s)")
    except Exception as e:
        duration = (datetime.now()-started).total_seconds()
        sb.table("cron_job_log").update({"finished_at":datetime.now().isoformat(),"duration_seconds":duration,"status":"FAILED","error_message":str(e)[:1000]}).eq("id",log_id).execute()
        logger.error(f"[CRON] {job_code} FAILED: {e}")


def _execute_direct(endpoint_url, payload):
    _register_direct_handlers()
    handler = DIRECT_HANDLERS.get(endpoint_url)
    if handler is None: raise ValueError(f"No direct handler for: {endpoint_url}")
    return handler(payload)


def _build_summary(result):
    if not isinstance(result,dict): return str(result)
    parts = []
    if "evaluated_traces" in result:
        parts.append(f"{result['evaluated_traces']} traces")
        if result.get("issues_found",0)>0: parts.append(f"{result['issues_found']} issues")
    if "scenario_run_id" in result:
        parts.append(f"run={result['scenario_run_id']}")
        parts.append(f"{result.get('passed',0)} passed")
        if result.get("failed",0)>0: parts.append(f"{result['failed']} failed")
    if "business_events_deleted" in result:
        total=sum(result.get(k,0) for k in ("business_events_deleted","integrity_events_deleted","service_data_deleted"))
        parts.append(f"{total} cleaned")
    if "alerts_sent" in result: parts.append(f"{result['alerts_sent']} alerts")
    if "detected" in result: parts.append(f"{result['detected']} repeated, {result.get('created',0)} created")
    if "patterns_updated" in result: parts.append(f"{result['patterns_updated']} updated, {result.get('patterns_created',0)} new")
    if result.get("suppressed",0)>0: parts.append(f"{result['suppressed']} suppressed")
    if result.get("errors",0)>0: parts.append(f"{result['errors']} errors")
    if "processed" in result and "sent" in result:
        parts.append(f"{result['processed']} processed, {result['sent']} sent")
    if "health_score" in result: parts.append(f"health={result['health_score']}")
    if "tenants" in result and "workflows" in result:
        parts.append(f"{result['tenants']}t {result['workflows']}wf {result.get('events',0)}ev {result.get('chaos',0)}chaos")
    if "evaluated" in result and "projected" in result:
        parts.append(f"{result['evaluated']}eval {result['projected']}proj {result.get('escalation',0)}esc")
    return ", ".join(parts) if parts else "No activity"


def load_jobs_from_db():
    from db.database import get_supabase
    sb = get_supabase()
    jobs = sb.table("cron_job_master").select("*").eq("is_active",True).execute()
    scheduler.remove_all_jobs()
    registered = 0
    for j in (jobs.data or []):
        expr = j.get("cron_expression","")
        if not expr: continue
        try:
            parts = expr.strip().split()
            trigger = CronTrigger(minute=parts[0],hour=parts[1],day=parts[2],month=parts[3],day_of_week=parts[4],timezone="Asia/Seoul")
            scheduler.add_job(execute_cron_job,trigger=trigger,id=j["job_code"],args=[j["job_code"],j["endpoint_url"],j.get("http_method","POST"),j.get("request_payload"),j.get("timeout_seconds",300)],replace_existing=True)
            registered += 1
            mode = "DIRECT" if j["endpoint_url"].startswith("direct://") else "HTTP"
            logger.info(f"[CRON] 등록: {j['job_code']} ({expr}) [{mode}]")
        except Exception as e:
            logger.error(f"[CRON] 등록 실패 {j['job_code']}: {e}")
    logger.info(f"[CRON] 총 {registered}개 작업 등록")


def start_scheduler():
    try:
        load_jobs_from_db()
        if not scheduler.running: scheduler.start()
        logger.info("[CRON] 스케줄러 시작 완료")
    except Exception as e:
        logger.error(f"[CRON] 스케줄러 시작 실패: {e}")
