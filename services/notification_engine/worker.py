"""Queue Worker v4.0 — trace_id context 전파 + IN_APP user_id 전달."""

import logging
from datetime import datetime, timezone
from typing import Optional

from . import audit
from . import retry_policy
from . import deadletter
from . import channel_registry

logger = logging.getLogger("notification_engine.worker")

FALLBACK_ADAPTERS = {}
try:
    from .adapters import telegram as _tg
    FALLBACK_ADAPTERS["TELEGRAM"] = _tg.send
except Exception:
    pass


def process_queue(limit: int = 20) -> dict:
    stats = {"processed": 0, "sent": 0, "failed": 0, "retried": 0,
             "deadlettered": 0, "quiet_hour_resumed": 0}
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        now = datetime.now(timezone.utc).isoformat()

        r1 = sb.table("runtime_notification_queue").select("*").eq("delivery_status", "QUEUED").order("created_at").limit(limit).execute()
        r2 = sb.table("runtime_notification_queue").select("*").eq("delivery_status", "RETRY_PENDING").lte("next_retry_at", now).order("next_retry_at").limit(limit).execute()
        r3 = sb.table("runtime_notification_queue").select("*").eq("delivery_status", "QUIET_HOUR_DELAYED").lte("next_retry_at", now).order("next_retry_at").limit(limit).execute()

        items = (r1.data or []) + (r2.data or []) + (r3.data or [])

        for item in items:
            stats["processed"] += 1
            was_delayed = item.get("delivery_status") == "QUIET_HOUR_DELAYED"
            sent_before = stats["sent"]
            _deliver_item(sb, item, stats)
            if was_delayed and stats["sent"] > sent_before:
                stats["quiet_hour_resumed"] += 1
                _log_qh_resume(item)
    except Exception as e:
        logger.error("Worker failed: %s", e)
    return stats


def _deliver_item(sb, item: dict, stats: dict):
    queue_id = item["id"]
    channel = item.get("delivery_channel", "TELEGRAM")
    event_id = item.get("runtime_event_id", queue_id)
    trace_id = item.get("trace_id", "")
    user_id = item.get("recipient_user_id")

    _update_queue(sb, queue_id, {"delivery_status": "PROCESSING"})

    # Set context for IN_APP adapter (trace_id + user_id)
    if channel == "IN_APP":
        try:
            from .adapters import in_app
            in_app.set_context(trace_id=trace_id, user_id=user_id)
        except Exception:
            pass

    adapter_fn = channel_registry.resolve_adapter(channel)
    if not adapter_fn:
        adapter_fn = FALLBACK_ADAPTERS.get(channel)
    if not adapter_fn:
        _handle_failure(sb, item, f"No adapter for {channel}", stats)
        return

    title = item.get("message_title") or ""
    body = item.get("message_body") or ""
    message = f"{title}\n{body}".strip() if title or body else f"[{item.get('notification_type')}]"

    success, error_msg = adapter_fn(message)
    now = datetime.now(timezone.utc).isoformat()

    if success:
        _update_queue(sb, queue_id, {"delivery_status": "DELIVERED", "delivered_at": now})
        stats["sent"] += 1
        audit.log_delivery(queue_id=queue_id, event_id=event_id, action="DELIVERED",
                           channel=channel, delivery_status="DELIVERED", trace_id=trace_id)
    else:
        _handle_failure(sb, item, error_msg or "Unknown error", stats)


def _handle_failure(sb, item, error_msg, stats):
    queue_id = item["id"]
    event_id = item.get("runtime_event_id", queue_id)
    trace_id = item.get("trace_id", "")
    channel = item.get("delivery_channel", "TELEGRAM")
    current_retry = item.get("retry_count", 0) + 1
    max_retries = item.get("max_retries", retry_policy.DEFAULT_MAX_RETRIES)

    if retry_policy.should_deadletter(current_retry, max_retries):
        deadletter.move_to_deadletter(item, error_msg)
        stats["deadlettered"] += 1
        audit.log_delivery(queue_id=queue_id, event_id=event_id, action="DEADLETTER",
                           channel=channel, delivery_status="DEADLETTER",
                           error_message=error_msg, trace_id=trace_id)
    else:
        next_at = retry_policy.calculate_next_retry_at(current_retry)
        _update_queue(sb, queue_id, {
            "delivery_status": "RETRY_PENDING", "retry_count": current_retry,
            "last_error": error_msg[:500] if error_msg else None,
            "next_retry_at": next_at.isoformat(),
        })
        stats["retried"] += 1
        audit.log_delivery(queue_id=queue_id, event_id=event_id, action=f"RETRY_{current_retry}",
                           channel=channel, delivery_status="RETRY_PENDING",
                           error_message=error_msg, trace_id=trace_id)


def _log_qh_resume(item):
    try:
        from db.supabase_client import get_supabase
        get_supabase().table("runtime_notification_policy_audit").insert({
            "notification_id": item.get("runtime_event_id"),
            "event_id": item.get("runtime_event_id"),
            "actor_id": item.get("recipient_user_id"),
            "source_type": item.get("notification_type"),
            "channel_key": item.get("delivery_channel"),
            "policy_type": "QUIET_HOUR_RESUME",
            "policy_result": "DELIVERED",
            "reason": "Quiet hour ended",
            "trace_id": item.get("trace_id"),
        }).execute()
    except Exception:
        pass


def _update_queue(sb, queue_id, updates):
    try:
        sb.table("runtime_notification_queue").update(updates).eq("id", queue_id).execute()
    except Exception as e:
        logger.error("Queue update failed: %s", e)
