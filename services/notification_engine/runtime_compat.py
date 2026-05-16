"""Runtime absorption — legacy SMS / in-app → notification engine queue.

Legacy callers route through compat_send_* so delivery is visible on
GET /notification-engine/queue-status. SMS/IN_APP adapters may still be
pending; callers keep legacy fallback when absorption fails.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("notification_engine.runtime_compat")

_NULL_UUID = "00000000-0000-0000-0000-000000000000"


def _mark_event_queued(event_id: str) -> None:
    try:
        from db.supabase_client import get_supabase

        sb = get_supabase()
        sb.table("runtime_notification_event").update({
            "event_status": "QUEUED",
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", event_id).execute()
    except Exception as e:
        logger.warning("Event status update failed: %s — %s", event_id, e)


def _queue_item(
    *,
    event_row: dict,
    delivery_channel: str,
    message_title: str,
    message_body: str,
    recipient_user_id: Optional[str],
    dedupe_key: str,
    source_trace: str,
) -> bool:
    from db.supabase_client import get_supabase

    sb = get_supabase()
    row: dict[str, Any] = {
        "runtime_event_id": event_row["id"],
        "recipient_user_id": recipient_user_id or _NULL_UUID,
        "notification_type": event_row.get("event_type", "ALERT"),
        "delivery_channel": delivery_channel,
        "delivery_status": "QUEUED",
        "message_title": (message_title or "")[:200],
        "message_body": (message_body or "")[:2000],
        "dedupe_key": dedupe_key[:200],
        "trace_id": event_row.get("trace_id") or "",
        "source_trace": source_trace,
        "escalation_level": 0,
    }
    resp = sb.table("runtime_notification_queue").insert(row).execute()
    return bool(resp.data)


def compat_send_sms(
    phone: str,
    message: str,
    *,
    event_type: str = "LEGACY_SMS",
    source_engine: str = "legacy_messaging",
    user_id: Optional[str] = None,
    company_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    title: str = "TAI Safe",
    severity: str = "WARNING",
    source_entity_id: Optional[str] = None,
) -> bool:
    """Absorb SMS into runtime_notification_queue. True if queued."""
    if not phone or not message:
        return False
    try:
        from services.notification_engine.schemas import NotificationEventCreate
        from services.notification_engine import event_intake

        tid = trace_id or f"SMS-{uuid.uuid4().hex[:10]}"
        digest = hashlib.sha256(f"{phone}:{message}".encode()).hexdigest()[:16]
        event = NotificationEventCreate(
            event_type=event_type,
            source_engine=source_engine,
            severity=severity,
            trace_id=tid,
            tenant_id=company_id,
            payload={
                "phone": phone,
                "message": message,
                "company_id": company_id,
            },
            source_domain="messaging",
            source_entity_id=source_entity_id,
            triggered_by=user_id,
        )
        event_row = event_intake.emit_event(event)
        if not event_row:
            return False

        ok = _queue_item(
            event_row=event_row,
            delivery_channel="SMS",
            message_title=title,
            message_body=message,
            recipient_user_id=user_id,
            dedupe_key=f"SMS_{phone}_{event_type}_{digest}",
            source_trace="RUNTIME_ABSORPTION_SMS",
        )
        if ok:
            _mark_event_queued(event_row["id"])
            logger.info(
                "[runtime_compat] SMS queued phone=***%s trace=%s",
                phone[-4:],
                tid,
            )
        return ok
    except Exception as e:
        logger.warning("[runtime_compat] compat_send_sms failed: %s", e)
        return False


def compat_send_in_app(
    sb,
    user_id: str,
    company_id: Optional[str],
    title: str,
    body: str,
    *,
    event_type: str = "OVERDUE_ESCALATION",
    trigger_code: str = "OVERDUE_ESCALATION",
    trace_id: Optional[str] = None,
    source_entity_id: Optional[str] = None,
    severity: str = "WARNING",
) -> bool:
    """Absorb in-app notification into runtime queue. True if queued."""
    if not user_id:
        return False
    try:
        from services.notification_engine.schemas import NotificationEventCreate
        from services.notification_engine import event_intake

        tid = trace_id or f"INAPP-{uuid.uuid4().hex[:10]}"
        digest = hashlib.sha256(f"{user_id}:{title}:{body}".encode()).hexdigest()[:16]
        event = NotificationEventCreate(
            event_type=event_type,
            source_engine="overdue_checker",
            severity=severity,
            trace_id=tid,
            tenant_id=company_id,
            payload={
                "trigger_code": trigger_code,
                "trigger_group": "OVERDUE",
                "company_id": company_id,
            },
            source_domain="overdue",
            source_entity_id=source_entity_id,
            triggered_by=user_id,
        )
        event_row = event_intake.emit_event(event)
        if not event_row:
            return False

        ok = _queue_item(
            event_row=event_row,
            delivery_channel="IN_APP",
            message_title=title,
            message_body=body,
            recipient_user_id=user_id,
            dedupe_key=f"INAPP_{user_id}_{event_type}_{digest}",
            source_trace="RUNTIME_ABSORPTION_IN_APP",
        )
        if ok:
            _mark_event_queued(event_row["id"])
            logger.info("[runtime_compat] IN_APP queued user=%s trace=%s", user_id, tid)
        return ok
    except Exception as e:
        logger.warning("[runtime_compat] compat_send_in_app failed: %s", e)
        return False
