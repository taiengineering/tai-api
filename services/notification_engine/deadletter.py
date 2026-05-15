"""Dead Letter Queue — 반복 실패 Queue 격리.

테이블: runtime_notification_deadletter
규칙: max_retry 초과 시 DLQ 이동.
"""

import logging
from typing import Optional

logger = logging.getLogger("notification_engine.deadletter")


def move_to_deadletter(queue_item: dict, failure_reason: str) -> Optional[dict]:
    """Queue Item → Dead Letter 이동 + 원본 Queue DEADLETTER 상태 변경."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        queue_id = queue_item["id"]

        # 1. DLQ INSERT
        dlq_row = {
            "original_queue_id": queue_id,
            "event_id": queue_item.get("runtime_event_id"),
            "failure_reason": failure_reason[:500],
            "retry_count": queue_item.get("retry_count", 0),
            "delivery_channel": queue_item.get("delivery_channel"),
            "message_title": queue_item.get("message_title"),
            "message_body": queue_item.get("message_body"),
            "payload": queue_item.get("payload") or {},
            "trace_id": queue_item.get("trace_id"),
            "source_engine": queue_item.get("source_engine"),
            "event_type": queue_item.get("notification_type"),
        }

        resp = sb.table("runtime_notification_deadletter").insert(dlq_row).execute()

        # 2. 원본 Queue 상태 변경
        sb.table("runtime_notification_queue").update({
            "delivery_status": "DEADLETTER",
        }).eq("id", queue_id).execute()

        logger.info("Moved to DLQ: queue=%s reason=%s", queue_id, failure_reason[:100])
        return resp.data[0] if resp.data else None

    except Exception as e:
        logger.error("DLQ move failed: %s — %s", queue_item.get("id"), e)
        return None


def count_deadletters() -> int:
    """현재 DLQ 건수."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        resp = sb.table("runtime_notification_deadletter") \
            .select("id", count="exact").execute()
        return resp.count or 0
    except Exception:
        return -1
