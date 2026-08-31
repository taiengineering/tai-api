"""DIRECT handlers: existing master jobs + pg_cron DB_FUNCTION/HTTP/CLEANUP + holiday."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import timedelta
from typing import Any, Callable

from services.time import now_kst, serialize_business_datetime

logger = logging.getLogger(__name__)

Handler = Callable[[dict], Any]
DIRECT_HANDLERS: dict[str, Handler] = {}


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


def _rpc(name: str, payload: dict) -> Any:
    res = _sb().rpc(name, payload or {}).execute()
    return res.data if hasattr(res, "data") else res


def _kosha_http(path: str, params: dict | None = None, timeout: int = 300) -> dict:
    import requests
    base = os.environ.get("INTERNAL_API_URL", "https://api.taieng.co.kr")
    url = base.rstrip("/") + path
    resp = requests.post(url, params=params or {}, json={}, timeout=timeout)
    try:
        body = resp.json()
    except Exception:
        body = {"text": resp.text[:500]}
    return {"http_status": resp.status_code, "body": body, "url": url, "params": params or {}}


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
    return cleanup_synthetic_data(
        event_retention_days=p.get("event_retention_days", 7),
        service_data_retention_hours=p.get("service_data_retention_hours", 24),
    )


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
    return detect_repeated_failures(_sb())


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


def _run_education_assignment_expire(p):
    from services.education_assignment_svc import expire_overdue_education_assignments
    return expire_overdue_education_assignments(_sb())


def _run_situation_retention_policy(p):
    from schedulers.situation_retention_policy import handler
    return asyncio.run(handler())


def _run_situation_snapshot_generate(p):
    from schedulers.situation_snapshot_generate import handler
    return asyncio.run(handler())


def _run_generate_daily_assignments(p):
    return _rpc("generate_daily_assignments", p or {})


def _run_daily_health_check(p):
    return _rpc("daily_health_check", p or {})


def _run_send_auto_qa_requests(p):
    return _rpc("send_auto_qa_requests", p or {})


def _run_collect_auto_qa_results(p):
    return _rpc("collect_auto_qa_results", p or {})


def _run_kosha_construction_safety_light(p):
    return _kosha_http("/kosha-collect/construction-safety-light", timeout=p.get("timeout_seconds", 300))


def _run_kosha_accident_cases(p):
    return _kosha_http("/kosha-collect/accident-cases", timeout=p.get("timeout_seconds", 300))


def _run_kosha_safety_materials(p):
    return _kosha_http(
        "/kosha-collect/run",
        params={"target": "safety-materials"},
        timeout=p.get("timeout_seconds", 300),
    )


def _run_health_cleanup(p):
    sb = _sb()
    cutoff = serialize_business_datetime(now_kst() - timedelta(days=30))
    h = sb.table("health_checks").delete().lt("checked_at", cutoff).execute()
    a = sb.table("health_alerts").delete().lt("created_at", cutoff).execute()
    return {"health_checks": getattr(h, "data", None), "health_alerts": getattr(a, "data", None)}


def _run_cron_job_log_retention(p):
    """Retention cutoff is now() in KST. Postgres local-timestamp is forbidden."""
    sb = _sb()
    cutoff = serialize_business_datetime(now_kst() - timedelta(days=30))
    res = (
        sb.table("cron_job_log")
        .delete()
        .lt("started_at", cutoff)
        .execute()
    )
    return {"deleted": getattr(res, "data", None), "predicate": "started_at < now() - interval '30 days'"}


def _run_business_event_retention(p):
    sb = _sb()
    cutoff = serialize_business_datetime(now_kst() - timedelta(days=90))
    res = sb.table("business_event").delete().lt("created_at", cutoff).execute()
    return {"deleted": getattr(res, "data", None), "predicate": "created_at < now() - interval '90 days'"}


def _run_holiday_sync(p):
    from services.holiday_sync_svc import sync_current_and_next
    return sync_current_and_next(created_by=None)


def register_direct_handlers() -> dict[str, Handler]:
    if DIRECT_HANDLERS:
        return DIRECT_HANDLERS
    DIRECT_HANDLERS.update({
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
        "direct://education_assignment_expire": _run_education_assignment_expire,
        "direct://situation_retention_policy": _run_situation_retention_policy,
        "direct://situation_snapshot_generate": _run_situation_snapshot_generate,
        "direct://generate_daily_assignments": _run_generate_daily_assignments,
        "direct://daily_health_check": _run_daily_health_check,
        "direct://send_auto_qa_requests": _run_send_auto_qa_requests,
        "direct://collect_auto_qa_results": _run_collect_auto_qa_results,
        "direct://kosha_construction_safety_light": _run_kosha_construction_safety_light,
        "direct://kosha_accident_cases": _run_kosha_accident_cases,
        "direct://kosha_safety_materials": _run_kosha_safety_materials,
        "direct://health_cleanup": _run_health_cleanup,
        "direct://cron_job_log_retention": _run_cron_job_log_retention,
        "direct://business_event_retention": _run_business_event_retention,
        "direct://holiday_sync": _run_holiday_sync,
    })
    return DIRECT_HANDLERS


def execute_direct(endpoint_url: str, payload: dict | None = None) -> Any:
    register_direct_handlers()
    handler = DIRECT_HANDLERS.get(endpoint_url)
    if handler is None:
        raise ValueError(f"No direct handler for: {endpoint_url}")
    return handler(payload or {})
