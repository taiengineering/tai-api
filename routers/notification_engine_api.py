"""Notification Engine API Router — v1.0.0
prefix: /notification-engine

API:
  POST  /notification-engine/process-queue    Queue Worker 수동 실행
  GET   /notification-engine/queue-status      Queue 현황
  GET   /notification-engine/events            최근 이벤트 조회
  POST  /notification-engine/emit-test         테스트 이벤트 발행
  POST  /notification-engine/ack/{queue_id}    ACK 처리
"""

import logging
from fastapi import APIRouter, Query
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notification-engine", tags=["알림엔진"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# ═══ Queue Worker 수동 실행 ═══

@router.post("/process-queue")
def process_queue_manual(limit: int = Query(20, ge=1, le=100)):
    """대기 중인 Queue 항목 발송 처리."""
    try:
        from services.notification_engine.worker import process_queue
        stats = process_queue(limit=limit)
        return {"status": "success", "data": stats}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Queue 현황 ═══

@router.get("/queue-status")
def get_queue_status():
    """현재 Queue 상태 요약."""
    try:
        sb = _sb()
        statuses = ["QUEUED", "DELIVERED", "FAILED"]
        result = {}
        for s in statuses:
            resp = sb.table("runtime_notification_queue") \
                .select("id", count="exact") \
                .eq("delivery_status", s).execute()
            result[s] = resp.count or 0
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ 최근 이벤트 ═══

@router.get("/events")
def list_recent_events(limit: int = Query(20, ge=1, le=100)):
    """최근 Notification Event 목록."""
    try:
        resp = _sb().table("runtime_notification_event") \
            .select("*") \
            .order("created_at", desc=True) \
            .limit(limit).execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ 테스트 이벤트 발행 ═══

@router.post("/emit-test")
def emit_test_event():
    """테스트 이벤트 발행 + Pipeline 실행 + Worker 동기 실행."""
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
            message_body="Notification Engine Phase 1 \ud14c\uc2a4\ud2b8.\n\uc815\uc0c1 \uc218\uc2e0\ub418\uba74 Pipeline 연\ub3d9 \uc644\ub8cc.",
            cooldown_minutes=1,
        )

        worker_stats = process_queue(limit=10)

        return {
            "status": "success",
            "pipeline": {
                "event_id": pipeline_result.get("event", {}).get("id") if pipeline_result.get("event") else None,
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
    """Queue Item ACK 처리."""
    try:
        from datetime import datetime, timezone
        sb = _sb()

        sb.table("runtime_notification_queue").update({
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
    """Queue Item RESOLVE 처리."""
    try:
        from datetime import datetime, timezone
        sb = _sb()

        sb.table("runtime_notification_queue").update({
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
