"""Queue Worker v2.0 — Retry Policy + Dead Letter + Trace Propagation.

Phase 1: Telegram only. Adapter 구조로 확장 가능.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from .adapters import telegram as telegram_adapter
from . import audit
from . import retry_policy
from . import deadletter

logger = logging.getLogger("notification_engine.worker")

CHANNEL_ADAPTERS = {
    "TELEGRAM": telegram_adapter.send,
}

# 허용 Queue Status
VALID_STATUSES = {
    "QUEUED", "PROCESSING", "DELIVERED", "FAILED",
    "RETRY_PENDING", "DEADLETTER", "ACKNOWLEDGED", "RESOLVED", "IGNORED",
}


def process_queue(limit: int = 20) -> dict:
    """Queue에서 QUEUED + RETRY_PENDING(시간 도래) 항목 poll → 발송.

    Returns:
        {"processed": int, "sent": int, "failed": int, "retried": int, "deadlettered": int}
    """
    stats = {"processed": 0, "sent": 0, "failed": 0, "retried": 0, "deadlettered": 0}

    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        now = datetime.now(timezone.utc).isoformat()

        # QUEUED 항목
        resp1 = sb.table("runtime_notification_queue") \
            .select("*") \
            .eq("delivery_status", "QUEUED") \
            .order("created_at") \
            .limit(limit).execute()

        # RETRY_PENDING 중 시간 도래한 항목
        resp2 = sb.table("runtime_notification_queue") \
            .select("*") \
            .eq("delivery_status", "RETRY_PENDING") \
            .lte("next_retry_at", now) \
            .order("next_retry_at") \
            .limit(limit).execute()

        items = (resp1.data or []) + (resp2.data or [])
        logger.info("Worker: %d items to process", len(items))

        for item in items:
            stats["processed"] += 1
            _deliver_item(sb, item, stats)

    except Exception as e:
        logger.error("Worker failed: %s", e)

    logger.info(
        "Worker done: processed=%d sent=%d failed=%d retried=%d dlq=%d",
        stats["processed"], stats["sent"], stats["failed"],
        stats["retried"], stats["deadlettered"],
    )
    return stats


def _deliver_item(sb, item: dict, stats: dict):
    """단일 Queue Item 발송."""
    queue_id = item["id"]
    channel = item.get("delivery_channel", "TELEGRAM")
    event_id = item.get("runtime_event_id", queue_id)
    trace_id = item.get("trace_id", "")

    # Mark PROCESSING
    _update_queue(sb, queue_id, {"delivery_status": "PROCESSING"})

    adapter_fn = CHANNEL_ADAPTERS.get(channel)
    if not adapter_fn:
        logger.error("No adapter for channel: %s (trace=%s)", channel, trace_id)
        _handle_failure(sb, item, "Unknown channel", stats)
        return

    # Build message
    title = item.get("message_title") or ""
    body = item.get("message_body") or ""
    message = f"{title}\n{body}".strip() if title or body else f"[{item.get('notification_type')}] Notification"

    # Send
    success, error_msg = adapter_fn(message)
    now = datetime.now(timezone.utc).isoformat()

    if success:
        _update_queue(sb, queue_id, {
            "delivery_status": "DELIVERED",
            "delivered_at": now,
        })
        stats["sent"] += 1
        audit.log_delivery(
            queue_id=queue_id, event_id=event_id,
            action="DELIVERED", channel=channel,
            delivery_status="DELIVERED", trace_id=trace_id,
        )
    else:
        _handle_failure(sb, item, error_msg or "Unknown error", stats)


def _handle_failure(sb, item: dict, error_msg: str, stats: dict):
    """Retry or DLQ."""
    queue_id = item["id"]
    event_id = item.get("runtime_event_id", queue_id)
    trace_id = item.get("trace_id", "")
    channel = item.get("delivery_channel", "TELEGRAM")
    current_retry = item.get("retry_count", 0) + 1
    max_retries = item.get("max_retries", retry_policy.DEFAULT_MAX_RETRIES)

    if retry_policy.should_deadletter(current_retry, max_retries):
        # DLQ 이동
        deadletter.move_to_deadletter(item, error_msg)
        stats["deadlettered"] += 1
        audit.log_delivery(
            queue_id=queue_id, event_id=event_id,
            action="DEADLETTER", channel=channel,
            delivery_status="DEADLETTER",
            error_message=error_msg, trace_id=trace_id,
        )
    else:
        # Retry
        next_at = retry_policy.calculate_next_retry_at(current_retry)
        _update_queue(sb, queue_id, {
            "delivery_status": "RETRY_PENDING",
            "retry_count": current_retry,
            "last_error": error_msg[:500] if error_msg else None,
            "next_retry_at": next_at.isoformat(),
        })
        stats["retried"] += 1
        audit.log_delivery(
            queue_id=queue_id, event_id=event_id,
            action=f"RETRY_{current_retry}", channel=channel,
            delivery_status="RETRY_PENDING",
            error_message=error_msg, trace_id=trace_id,
        )


def _update_queue(sb, queue_id: str, updates: dict):
    """Queue 상태 업데이트."""
    try:
        sb.table("runtime_notification_queue").update(updates).eq("id", queue_id).execute()
    except Exception as e:
        logger.error("Queue update failed: %s — %s", queue_id, e)
