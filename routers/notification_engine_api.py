"""Notification Engine API Router v5.2 — E2E Test Runner
prefix: /notification-engine
"""

import logging
from fastapi import APIRouter, Query
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notification-engine", tags=["알림엔진"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/health")
def notification_health():
    try:
        from services.notification_engine.metrics_aggregator import get_runtime_summary
        return {"status": "success", "data": get_runtime_summary()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/runtime-summary")
def runtime_summary():
    try:
        from services.notification_engine.metrics_aggregator import get_runtime_summary
        return {"status": "success", "data": get_runtime_summary()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/metrics")
def list_metrics(limit: int = Query(24, ge=1, le=100)):
    try:
        resp = _sb().table("runtime_notification_metrics") \
            .select("*").order("metric_time", desc=True).limit(limit).execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/collect-metrics")
def collect_metrics_manual(window_minutes: int = Query(10, ge=1, le=60)):
    try:
        from services.notification_engine.metrics_aggregator import collect_and_record
        return {"status": "success", "data": collect_and_record(window_minutes=window_minutes)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/timeline/{trace_id}")
def get_trace_timeline(trace_id: str):
    try:
        from services.notification_engine.timeline import get_timeline
        result = get_timeline(trace_id)
        if result is None:
            return {"status": "error", "message": "Timeline not found"}
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/registry")
def list_event_registry():
    try:
        from services.notification_engine.registry import list_all_event_types
        return {"status": "success", "data": list_all_event_types()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/channels")
def list_channels():
    try:
        from services.notification_engine.channel_registry import list_enabled_channels
        return {"status": "success", "data": list_enabled_channels()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/deadletters")
def list_deadletters(limit: int = Query(20, ge=1, le=100)):
    try:
        resp = _sb().table("runtime_notification_deadletter") \
            .select("*").order("created_at", desc=True).limit(limit).execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/policy-audit/{notification_id}")
def get_policy_audit(notification_id: str):
    try:
        resp = _sb().table("runtime_notification_policy_audit") \
            .select("*").eq("notification_id", notification_id) \
            .order("created_at").execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/policy-audit")
def list_policy_audit(
    policy_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    try:
        q = _sb().table("runtime_notification_policy_audit") \
            .select("*").order("created_at", desc=True).limit(limit)
        if policy_type:
            q = q.eq("policy_type", policy_type)
        return {"status": "success", "data": q.execute().data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/process-queue")
def process_queue_manual(limit: int = Query(20, ge=1, le=100)):
    try:
        from services.notification_engine.worker import process_queue
        return {"status": "success", "data": process_queue(limit=limit)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/queue-status")
def get_queue_status():
    try:
        sb = _sb()
        statuses = ["QUEUED", "PROCESSING", "DELIVERED", "FAILED",
                    "RETRY_PENDING", "DEADLETTER", "ACKNOWLEDGED",
                    "RESOLVED", "QUIET_HOUR_DELAYED"]
        result = {}
        for s in statuses:
            resp = sb.table("runtime_notification_queue") \
                .select("id", count="exact").eq("delivery_status", s).execute()
            result[s] = resp.count or 0
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/events")
def list_recent_events(limit: int = Query(20, ge=1, le=100)):
    try:
        resp = _sb().table("runtime_notification_event") \
            .select("*").order("created_at", desc=True).limit(limit).execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ emit-test ═══

@router.post("/emit-test")
def emit_test_event(
    channel_key: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    force_quiet_hour: bool = Query(False),
):
    try:
        from services.notification_engine.schemas import NotificationEventCreate
        from services.notification_engine.pipeline import run_pipeline
        from services.notification_engine.worker import process_queue

        src_type = source_type or "runtime_alert"
        event = NotificationEventCreate(
            event_type="test_notification",
            source_engine="notification_engine_test",
            severity="INFO",
            trace_id=f"TEST-{src_type.upper()}",
            payload={"message": f"Test (ch={channel_key or 'auto'}, src={src_type})"},
            source_domain="notification_engine",
        )
        pr = run_pipeline(
            event=event,
            message_title=f"\U0001f6a8 [TEST] ({channel_key or 'auto'})",
            message_body=f"Channel: {channel_key or 'auto'}\nSource: {src_type}",
            cooldown_minutes=1, force_quiet_hour=force_quiet_hour,
        )
        ws = process_queue(limit=10)
        return {
            "status": "success",
            "test_params": {"channel_key": channel_key, "source_type": src_type, "force_quiet_hour": force_quiet_hour},
            "pipeline": {
                "event_id": pr.get("event", {}).get("id") if pr.get("event") else None,
                "trace_id": pr.get("event", {}).get("trace_id") if pr.get("event") else None,
                "recipients": len(pr.get("recipients", [])),
                "queued": len(pr.get("queued", [])),
                "error": pr.get("error"),
            },
            "worker": ws,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ E2E Scenario Test Runner ═══

@router.post("/run-e2e-test")
def run_e2e_test(
    scenario: str = Query("NORMAL", description="NORMAL, MUTE, QUIET_HOUR, CRITICAL_BYPASS, RETRY, DLQ"),
    channel_key: str = Query("TELEGRAM"),
):
    """Scenario 기반 Runtime E2E 검증."""
    try:
        from services.notification_engine.e2e_executor import run_scenario
        return {"status": "success", "data": run_scenario(scenario=scenario, channel_key=channel_key)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ ACK / Resolve ═══

@router.post("/ack/{queue_id}")
def ack_notification(queue_id: str):
    try:
        from datetime import datetime, timezone
        _sb().table("runtime_notification_queue").update({
            "delivery_status": "ACKNOWLEDGED",
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", queue_id).execute()
        from services.notification_engine.audit import log_ack
        log_ack(queue_id=queue_id)
        return {"status": "success", "message": f"{queue_id} ACK 완료"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/resolve/{queue_id}")
def resolve_notification(queue_id: str):
    try:
        from datetime import datetime, timezone
        _sb().table("runtime_notification_queue").update({
            "delivery_status": "RESOLVED",
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", queue_id).execute()
        from services.notification_engine.audit import log_delivery
        log_delivery(
            queue_id=queue_id, event_id=queue_id,
            action="RESOLVED", channel="SYSTEM",
            delivery_status="RESOLVED",
        )
        return {"status": "success", "message": f"{queue_id} RESOLVE 완료"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
