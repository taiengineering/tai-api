"""Queue Worker — QUEUED 항목 poll → Channel Adapter → delivery update → audit.

Phase 1: Telegram only. Adapter 구조로 확장 가능.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from .adapters import telegram as telegram_adapter
from . import audit

logger = logging.getLogger("notification_engine.worker")

CHANNEL_ADAPTERS = {
    "TELEGRAM": telegram_adapter.send,
}


def process_queue(limit: int = 20) -> dict:
    """Queue에서 QUEUED 항목 poll → 발송 → 결과 업데이트.

    Returns:
        {"processed": int, "sent": int, "failed": int, "retried": int}
    """
    stats = {"processed": 0, "sent": 0, "failed": 0, "retried": 0}

    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        # 1. QUEUED 항목 조회
        resp = sb.table("runtime_notification_queue") \
            .select("*") \
            .eq("delivery_status", "QUEUED") \
            .order("created_at") \
            .limit(limit) \
            .execute()

        items = resp.data or []
        logger.info("Worker: %d items to process", len(items))

        for item in items:
            stats["processed"] += 1
            _deliver_item(sb, item, stats)

    except Exception as e:
        logger.error("Worker failed: %s", e)

    logger.info(
        "Worker done: %d processed, %d sent, %d failed, %d retried",
        stats["processed"], stats["sent"], stats["failed"], stats["retried"],
    )
    return stats


def _deliver_item(sb, item: dict, stats: dict):
    """단일 Queue Item 발송."""
    queue_id = item["id"]
    channel = item.get("delivery_channel", "TELEGRAM")
    event_id = item.get("runtime_event_id", queue_id)

    adapter_fn = CHANNEL_ADAPTERS.get(channel)
    if not adapter_fn:
        logger.error("No adapter for channel: %s", channel)
        _update_queue_status(sb, queue_id, "FAILED", error="Unknown channel")
        stats["failed"] += 1
        return

    # Build message
    title = item.get("message_title") or ""
    body = item.get("message_body") or ""
    message = f"{title}\n{body}".strip() if title or body else f"[{item.get('notification_type')}] Notification"

    # Send
    success, error_msg = adapter_fn(message)
    now = datetime.now(timezone.utc).isoformat()

    if success:
        _update_queue_status(sb, queue_id, "DELIVERED", delivered_at=now)
        stats["sent"] += 1
        audit.log_delivery(
            queue_id=queue_id, event_id=event_id,
            action="DELIVERED", channel=channel,
            delivery_status="DELIVERED",
        )
    else:
        retry_count = item.get("retry_count", 0) + 1
        max_retries = item.get("max_retries", 3)

        if retry_count >= max_retries:
            _update_queue_status(sb, queue_id, "FAILED", error=error_msg, retry_count=retry_count)
            stats["failed"] += 1
            audit.log_delivery(
                queue_id=queue_id, event_id=event_id,
                action="FAILED", channel=channel,
                delivery_status="FAILED", error_message=error_msg,
            )
        else:
            _update_queue_status(sb, queue_id, "QUEUED", error=error_msg, retry_count=retry_count)
            stats["retried"] += 1
            audit.log_delivery(
                queue_id=queue_id, event_id=event_id,
                action="RETRY", channel=channel,
                delivery_status="QUEUED", error_message=error_msg,
            )


def _update_queue_status(
    sb, queue_id: str, status: str,
    delivered_at: Optional[str] = None,
    error: Optional[str] = None,
    retry_count: Optional[int] = None,
):
    """Queue 상태 업데이트."""
    try:
        update = {"delivery_status": status}
        if delivered_at:
            update["delivered_at"] = delivered_at
        if error:
            update["last_error"] = error[:500]
        if retry_count is not None:
            update["retry_count"] = retry_count
        sb.table("runtime_notification_queue").update(update).eq("id", queue_id).execute()
    except Exception as e:
        logger.error("Queue status update failed: %s — %s", queue_id, e)
