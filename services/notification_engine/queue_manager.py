"""Queue Manager v2.0 — trace_id 전파 + Registry 검증."""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

logger = logging.getLogger("notification_engine.queue")


def create_queue_items(
    event_row: dict,
    recipients: List[dict],
    message_title: str,
    message_body: str,
    dedupe_key: Optional[str] = None,
    cooldown_minutes: int = 15,
) -> List[dict]:
    """Recipient 목록 → Queue Item INSERT.

    dedupe: 같은 dedupe_key가 cooldown 내 이미 있으면 skip.
    trace_id: event_row에서 전파.
    """
    created = []
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        now = datetime.now(timezone.utc)
        trace_id = event_row.get("trace_id", "")

        for recipient in recipients:
            item_dedupe = dedupe_key or _build_dedupe_key(event_row, recipient)

            if _is_in_cooldown(sb, item_dedupe, cooldown_minutes, now):
                logger.info("Suppressed (cooldown): %s trace=%s", item_dedupe, trace_id)
                continue

            row = {
                "runtime_event_id": event_row["id"],
                "recipient_user_id": recipient.get("user_id") or event_row.get("triggered_by") or "00000000-0000-0000-0000-000000000000",
                "notification_type": event_row.get("event_type", "ALERT"),
                "delivery_channel": recipient.get("delivery_channel", "TELEGRAM"),
                "delivery_status": "QUEUED",
                "message_title": message_title[:200] if message_title else "",
                "message_body": message_body[:2000] if message_body else "",
                "dedupe_key": item_dedupe,
                "cooldown_until": (now + timedelta(minutes=cooldown_minutes)).isoformat(),
                "escalation_level": recipient.get("escalation_level", 0),
                "trace_id": trace_id,
                "source_trace": "NOTIFICATION_ENGINE_QUEUE",
            }

            resp = sb.table("runtime_notification_queue").insert(row).execute()
            if resp.data:
                created.append(resp.data[0])

    except Exception as e:
        logger.error("Queue creation failed: %s", e)

    logger.info("Queue created: %d items for event %s", len(created), event_row.get("id"))
    return created


def _build_dedupe_key(event_row: dict, recipient: dict) -> str:
    return f"{event_row.get('event_type')}_{event_row.get('source_engine')}_{recipient.get('recipient_source', 'OP')}"


def _is_in_cooldown(sb, dedupe_key: str, cooldown_minutes: int, now: datetime) -> bool:
    try:
        since = (now - timedelta(minutes=cooldown_minutes)).isoformat()
        resp = sb.table("runtime_notification_queue") \
            .select("id", count="exact") \
            .eq("dedupe_key", dedupe_key) \
            .gte("created_at", since) \
            .in_("delivery_status", ["QUEUED", "PROCESSING", "DELIVERED", "RETRY_PENDING"]) \
            .execute()
        return (resp.count or 0) > 0
    except Exception:
        return False
