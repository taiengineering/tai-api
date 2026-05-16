"""Queue Worker v3.0 — Channel Registry Adapter Resolution.

Adapter를 CHANNEL_ADAPTERS 고정 dict 대신
channel_registry.resolve_adapter()로 동적 해결.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from . import audit
from . import retry_policy
from . import deadletter
from . import channel_registry

logger = logging.getLogger("notification_engine.worker")

# Fallback static map (registry 실패 시)
FALLBACK_ADAPTERS = {}
try:
    from .adapters import telegram as _tg
    FALLBACK_ADAPTERS["TELEGRAM"] = _tg.send
except Exception:
    pass

VALID_STATUSES = {
    "QUEUED", "PROCESSING", "DELIVERED", "FAILED",
    "RETRY_PENDING", "DEADLETTER", "ACKNOWLEDGED", "RESOLVED", "IGNORED",
}


def process_queue(limit: int = 20) -> dict:
    """QUEUED + RETRY_PENDING(시간 도래) 항목 poll → 발송."""
    stats = {"processed": 0, "sent": 0, "failed": 0, "retried": 0, "deadlettered": 0}

    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        now = datetime.now(timezone.utc).isoformat()

        resp1 = sb.table("runtime_notification_queue") \
            .select("*").eq("delivery_status", "QUEUED") \
            .order("created_at").limit(limit).execute()

        resp2 = sb.table("runtime_notification_queue") \
            .select("*").eq("delivery_status", "RETRY_PENDING") \
            .lte("next_retry_at", now) \
            .order("next_retry_at").limit(limit).execute()

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
    queue_id = item["id"]
    channel = item.get("delivery_channel", "TELEGRAM")
    event_id = item.get("runtime_event_id", queue_id)
    trace_id = item.get("trace_id", "")

    _update_queue(sb, queue_id, {"delivery_status": "PROCESSING"})

    # Dynamic adapter resolution via channel_registry
    adapter_fn = channel_registry.resolve_adapter(channel)
    if not adapter_fn:
        adapter_fn = FALLBACK_ADAPTERS.get(channel)
    if not adapter_fn:
        logger.error("No adapter for channel: %s (trace=%s)", channel, trace_id)
        _handle_failure(sb, item, f"No adapter for {channel}", stats)
        return

    title = item.get("message_title") or ""
    body = item.get("message_body") or ""
    message = f"{title}\n{body}".strip() if title or body else f"[{item.get('notification_type')}] Notification"

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
    queue_id = item["id"]
    event_id = item.get("runtime_event_id", queue_id)
    trace_id = item.get("trace_id", "")
    channel = item.get("delivery_channel", "TELEGRAM")
    current_retry = item.get("retry_count", 0) + 1
    max_retries = item.get("max_retries", retry_policy.DEFAULT_MAX_RETRIES)

    if retry_policy.should_deadletter(current_retry, max_retries):
        deadletter.move_to_deadletter(item, error_msg)
        stats["deadlettered"] += 1
        audit.log_delivery(
            queue_id=queue_id, event_id=event_id,
            action="DEADLETTER", channel=channel,
            delivery_status="DEADLETTER",
            error_message=error_msg, trace_id=trace_id,
        )
    else:
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
    try:
        sb.table("runtime_notification_queue").update(updates).eq("id", queue_id).execute()
    except Exception as e:
        logger.error("Queue update failed: %s — %s", queue_id, e)
