"""Audit Logger — 누가 언제 무엇을 받았고 ACK 했는가 추적."""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("notification_engine.audit")


def log_delivery(
    queue_id: str,
    event_id: str,
    action: str,
    channel: str,
    delivery_status: str,
    action_by: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Optional[dict]:
    """Audit trail INSERT."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        row = {
            "notification_id": queue_id,
            "queue_id": queue_id,
            "event_id": event_id,
            "action": action,
            "action_by": action_by,
            "channel": channel,
            "delivery_status": delivery_status,
            "error_message": error_message,
            "source_trace": "NOTIFICATION_ENGINE_AUDIT",
        }

        resp = sb.table("runtime_notification_audit").insert(row).execute()
        return resp.data[0] if resp.data else None

    except Exception as e:
        logger.error("Audit log failed: queue=%s action=%s — %s", queue_id, action, e)
        return None


def log_ack(queue_id: str, acked_by: Optional[str] = None) -> Optional[dict]:
    """ACK 기록."""
    return log_delivery(
        queue_id=queue_id,
        event_id=queue_id,  # fallback
        action="ACK",
        channel="SYSTEM",
        delivery_status="ACKNOWLEDGED",
        action_by=acked_by,
    )
