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
    return _kosha_http(
        "/kosha-collect/run",
        params={"target": "accident-cases"},
        timeout=p.get("timeout_seconds", 300),
    )


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


def _run_shared_search_incremental(p):
    """Drain the search_index_outbox — incremental OpenSearch sync (§21-§23)."""
    from services.shared_search.incremental import process_queue
    limit = int(p.get("limit", 50))
    return process_queue(
        batch_size=limit,
        supabase_client=_sb(),
    )


def _run_shared_search_reconcile(p):
    """OpenSearch ↔ Domain SoT reconcile — safety net (§35-§37)."""
    from services.shared_search.opensearch_reconcile import run_reconcile
    from services.shared_search.production_bindings import build_production_adapters
    from services.shared_search.incremental import _try_build_legal_client, _try_build_mkt_client
    from services.shared_search.opensearch_client import get_client, CURRENT_ALIAS
    sb = _sb()
    adapters = build_production_adapters(
        sb,
        legal_client=_try_build_legal_client(),
        marketing_client=_try_build_mkt_client(),
    )
    client = get_client()
    return run_reconcile(
        adapters=adapters,
        client=client,
        index=CURRENT_ALIAS,
        supabase=sb,
    )


def _run_saas_recurring_billing(p):
    from services.saas_recurring_billing_scheduler import run_due_saas_recurring_billing
    return run_due_saas_recurring_billing(p)


def _run_qa_scheduler_tick(p):
    from services.qa_scheduler_svc import scheduler_tick
    return asyncio.run(scheduler_tick(_sb()))


def _run_public_data_sync_tick(p):
    from services.public_data_sync.scheduler_bridge import tick_public_data_sources
    limit = int(p.get("limit", 2))
    lease = int(p.get("lease_seconds", 900))
    hb_interval = int(p.get("heartbeat_interval_seconds", 60))
    retry_delay = int(p.get("retry_delay_seconds", 3600))
    results = tick_public_data_sources(
        limit=limit,
        lease_seconds=lease,
        heartbeat_interval_seconds=hb_interval,
        retry_delay_seconds=retry_delay,
    )
    return {"executed": len(results), "results": results}


def _run_leg_law_refresh(p):
    """Trigger used-law form refresh via LEG API (WO-TAI-LEG-USED-LAW-REFRESH-001).

    Resolves Case C scope (inspection_sets JOIN law_master — confirmed used laws only)
    and passes law_targets to LEG server. LEG does not connect to TAI DB.
    """
    import requests
    base = os.environ.get("LEG_RUNTIME_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("LEG_RUNTIME_URL not set")
    token = os.environ.get("LEG_INTERNAL_API_KEY", "")
    if not token:
        raise RuntimeError("LEG_INTERNAL_API_KEY not set")
    timeout = int(p.get("timeout_seconds", 300))

    # Resolve Case C scope: laws used in service (inspection_sets UNION
    # construction_check_templates) AND confirmed in law_master.
    # inspection_sets covers 점검SET + 법령진단 + 의무추출 paths (all three write here).
    # construction_check_templates covers future law fields (currently dormant).
    # law_master.is_active alone (768 laws) is NOT sufficient — must have usage evidence.
    sb = _sb()
    is_rows = (
        sb.table("inspection_sets")
        .select("law_name")
        .eq("is_active", True)
        .execute()
    )
    cct_rows = (
        sb.table("construction_check_templates")
        .select("law_name")
        .eq("is_active", True)
        .execute()
    )
    used_names = {r["law_name"] for r in (is_rows.data or []) if r.get("law_name")}
    used_names |= {r["law_name"] for r in (cct_rows.data or []) if r.get("law_name")}

    lm_rows = (
        sb.table("law_master")
        .select("law_name, law_api_id, law_mst_no")
        .eq("is_active", True)
        .not_.is_("law_api_id", "null")
        .execute()
    )
    lm_by_name = {
        r["law_name"]: r
        for r in (lm_rows.data or [])
        if r.get("law_name") and r.get("law_api_id")
    }

    law_targets = [
        {
            "law_name": name,
            "law_api_id": lm_by_name[name]["law_api_id"],
            "law_mst_no": lm_by_name[name].get("law_mst_no") or "",
        }
        for name in used_names
        if name in lm_by_name
    ]

    # admrul_targets: confirmed-used admin rule serials must be resolved from TAI DB.
    # No TAI-side usage confirmation table exists yet — admbyl refresh deferred.
    admrul_targets: list = []

    resp = requests.post(
        f"{base}/law-intake/refresh",
        json={"law_targets": law_targets, "admrul_targets": admrul_targets},
        headers={"X-Leg-Internal-Token": token},
        timeout=timeout,
    )
    resp.raise_for_status()

    try:
        body = resp.json()
    except Exception:
        body = {"text": resp.text[:500]}

    outcome = body.get("outcome", "")
    if outcome == "ERROR":
        raise RuntimeError(f"LEG refresh returned ERROR: {body}")
    if outcome == "PARTIAL_HOLD":
        raise RuntimeError(f"LEG refresh returned PARTIAL_HOLD — non-terminal tasks remain: {body}")

    return {
        "http_status": resp.status_code,
        "body": body,
        "scope_sent": len(law_targets),
    }


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
        "direct://shared_search_incremental": _run_shared_search_incremental,
        "direct://shared_search_reconcile":   _run_shared_search_reconcile,
        "direct://saas_recurring_billing":    _run_saas_recurring_billing,
        "direct://qa_scheduler_tick":         _run_qa_scheduler_tick,
        "direct://public_data_sync_tick":     _run_public_data_sync_tick,
        "direct://leg_law_refresh":           _run_leg_law_refresh,
    })
    return DIRECT_HANDLERS


def execute_direct(endpoint_url: str, payload: dict | None = None) -> Any:
    register_direct_handlers()
    handler = DIRECT_HANDLERS.get(endpoint_url)
    if handler is None:
        raise ValueError(f"No direct handler for: {endpoint_url}")
    return handler(payload or {})
