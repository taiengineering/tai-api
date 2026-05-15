"""Notification Engine API Router v3.0 — Observability & Metrics
prefix: /notification-engine

API:
  GET    /notification-engine/health              Runtime Health
  GET    /notification-engine/registry             Event Registry
  GET    /notification-engine/deadletters          DLQ 목록
  POST   /notification-engine/process-queue        Queue Worker 수동
  GET    /notification-engine/queue-status          Queue 현황
  GET    /notification-engine/events               최근 이벤트
  POST   /notification-engine/emit-test            테스트 E2E
  POST   /notification-engine/ack/{queue_id}       ACK
  POST   /notification-engine/resolve/{queue_id}   RESOLVE
  GET    /notification-engine/metrics              Metrics 이력
  GET    /notification-engine/runtime-summary      실시간 요약
  POST   /notification-engine/collect-metrics      Metrics 수동 집계
  GET    /notification-engine/timeline/{trace_id}  Trace Timeline
"""

import logging
from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notification-engine", tags=["알림엔진"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# ═══ Health ═══

@router.get("/health")
def notification_health():
    try:
        from services.notification_engine.metrics_aggregator import get_runtime_summary
        summary = get_runtime_summary()
        return {"status": "success", "data": summary}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Runtime Summary (실시간) ═══

@router.get("/runtime-summary")
def runtime_summary():
    try:
        from services.notification_engine.metrics_aggregator import get_runtime_summary
        summary = get_runtime_summary()
        return {"status": "success", "data": summary}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Metrics 이력 ═══

@router.get("/metrics")
def list_metrics(limit: int = Query(24, ge=1, le=100)):
    """최근 Metrics 이력."""
    try:
        resp = _sb().table("runtime_notification_metrics") \
            .select("*").order("metric_time", desc=True).limit(limit).execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Metrics 수동 집계 ═══

@router.post("/collect-metrics")
def collect_metrics_manual(window_minutes: int = Query(10, ge=1, le=60)):
    try:
        from services.notification_engine.metrics_aggregator import collect_and_record
        result = collect_and_record(window_minutes=window_minutes)
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Trace Timeline ═══

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


# ═══ Registry ═══

@router.get("/registry")
def list_event_registry():
    try:
        from services.notification_engine.registry import list_all_event_types
        return {"status": "success", "data": list_all_event_types()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Dead Letters ═══

@router.get("/deadletters")
def list_deadletters(limit: int = Query(20, ge=1, le=100)):
    try:
        resp = _sb().table("runtime_notification_deadletter") \
            .select("*").order("created_at", desc=True).limit(limit).execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Queue Worker ═══

@router.post("/process-queue")
def process_queue_manual(limit: int = Query(20, ge=1, le=100)):
    try:
        from services.notification_engine.worker import process_queue
        return {"status": "success", "data": process_queue(limit=limit)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Queue 현황 ═══

@router.get("/queue-status")
def get_queue_status():
    try:
        sb = _sb()
        statuses = ["QUEUED", "PROCESSING", "DELIVERED", "FAILED",
                    "RETRY_PENDING", "DEADLETTER", "ACKNOWLEDGED", "RESOLVED"]
        result = {}
        for s in statuses:
            resp = sb.table("runtime_notification_queue") \
                .select("id", count="exact").eq("delivery_status", s).execute()
            result[s] = resp.count or 0
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ 최근 이벤트 ═══

@router.get("/events")
def list_recent_events(limit: int = Query(20, ge=1, le=100)):
    try:
        resp = _sb().table("runtime_notification_event") \
            .select("*").order("created_at", desc=True).limit(limit).execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ 테스트 E2E ═══

@router.post("/emit-test")
def emit_test_event():
    try:
        from services.notification_engine.schemas import NotificationEventCreate
        from services.notification_engine.pipeline import run_pipeline
        from services.notification_engine.worker import process_queue

        event = NotificationEventCreate(
            event_type="test_notification",
            source_engine="notification_engine_test",
            severity="INFO",
            trace_id="TEST-MANUAL",
            payload={"message": "Notification Engine Phase 1 Test"},
            source_domain="notification_engine",
        )

        pipeline_result = run_pipeline(
            event=event,
            message_title="\U0001f6a8 [TEST] Notification Engine",
            message_body="Notification Engine Phase 1 \ud14c\uc2a4\ud2b8.\n\uc815\uc0c1 \uc218\uc2e0\ub418\uba74 Pipeline \uc5f0\ub3d9 \uc644\ub8cc.",
            cooldown_minutes=1,
        )
        worker_stats = process_queue(limit=10)

        return {
            "status": "success",
            "pipeline": {
                "event_id": pipeline_result.get("event", {}).get("id") if pipeline_result.get("event") else None,
                "trace_id": pipeline_result.get("event", {}).get("trace_id") if pipeline_result.get("event") else None,
                "recipients": len(pipeline_result.get("recipients", [])),
                "queued": len(pipeline_result.get("queued", [])),
                "error": pipeline_result.get("error"),
            },
            "worker": worker_stats,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ ACK ═══

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


# ═══ RESOLVE ═══

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
