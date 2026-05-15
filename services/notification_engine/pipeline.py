"""Notification Pipeline — Event → Resolve → Queue → (Worker는 별도 실행).

전체 파이프라인을 하나로 묶는 orchestrator.
Watch Engine 등에서 호출할 메인 진입점.
"""

import logging
from typing import Optional
from .schemas import NotificationEventCreate
from . import event_intake
from . import recipient_resolver
from . import queue_manager

logger = logging.getLogger("notification_engine.pipeline")


def run_pipeline(
    event: NotificationEventCreate,
    message_title: str = "",
    message_body: str = "",
    cooldown_minutes: int = 15,
    dedupe_key: Optional[str] = None,
) -> dict:
    """Full pipeline: Emit → Resolve → Queue.

    Returns:
        {"event": dict|None, "recipients": list, "queued": list, "error": str|None}
    """
    result = {"event": None, "recipients": [], "queued": [], "error": None}

    try:
        # 1. Event Intake
        event_row = event_intake.emit_event(event)
        if not event_row:
            result["error"] = "Event emission failed"
            return result
        result["event"] = event_row

        # 2. Recipient Resolution
        recipients = recipient_resolver.resolve_recipients(
            event_type=event.event_type,
            event_row=event_row,
        )
        result["recipients"] = recipients

        if not recipients:
            logger.warning("No recipients for event %s", event.event_type)
            _mark_event_processed(event_row["id"], "NO_RECIPIENTS")
            return result

        # 3. Queue Creation
        queued = queue_manager.create_queue_items(
            event_row=event_row,
            recipients=recipients,
            message_title=message_title,
            message_body=message_body,
            dedupe_key=dedupe_key,
            cooldown_minutes=cooldown_minutes,
        )
        result["queued"] = queued

        # 4. Event 상태 업데이트
        status = "QUEUED" if queued else "SUPPRESSED"
        _mark_event_processed(event_row["id"], status)

        logger.info(
            "Pipeline complete: event=%s recipients=%d queued=%d",
            event_row["id"], len(recipients), len(queued),
        )

    except Exception as e:
        logger.error("Pipeline failed: %s", e)
        result["error"] = str(e)

    return result


def _mark_event_processed(event_id: str, status: str):
    """이벤트 처리 완료 상태 업데이트."""
    try:
        from db.supabase_client import get_supabase
        from datetime import datetime, timezone
        sb = get_supabase()
        sb.table("runtime_notification_event").update({
            "event_status": status,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", event_id).execute()
    except Exception as e:
        logger.error("Event status update failed: %s — %s", event_id, e)
