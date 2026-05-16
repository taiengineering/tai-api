"""Notification Pipeline v3.0 — force_quiet_hour 지원."""

import logging
from typing import Optional
from .schemas import NotificationEventCreate
from . import event_intake
from . import recipient_resolver
from . import queue_manager
from . import registry

logger = logging.getLogger("notification_engine.pipeline")


def run_pipeline(
    event: NotificationEventCreate,
    message_title: str = "",
    message_body: str = "",
    cooldown_minutes: int = 15,
    dedupe_key: Optional[str] = None,
    force_quiet_hour: bool = False,
) -> dict:
    """Full pipeline: Registry Check → Emit → Resolve → Queue."""
    result = {"event": None, "recipients": [], "queued": [], "error": None}

    try:
        if not registry.is_notification_enabled(event.event_type):
            result["error"] = "Event type disabled in registry"
            return result

        if event.severity == "INFO":
            reg_severity = registry.get_default_severity(event.event_type)
            if reg_severity != "INFO":
                event.severity = reg_severity

        event_row = event_intake.emit_event(event)
        if not event_row:
            result["error"] = "Event emission failed"
            return result
        result["event"] = event_row

        recipients = recipient_resolver.resolve_recipients(
            event_type=event.event_type, event_row=event_row,
        )
        result["recipients"] = recipients

        if not recipients:
            _mark_event_processed(event_row["id"], "NO_RECIPIENTS")
            return result

        queued = queue_manager.create_queue_items(
            event_row=event_row,
            recipients=recipients,
            message_title=message_title,
            message_body=message_body,
            dedupe_key=dedupe_key,
            cooldown_minutes=cooldown_minutes,
            force_quiet_hour=force_quiet_hour,
        )
        result["queued"] = queued

        status = "QUEUED" if queued else "SUPPRESSED"
        _mark_event_processed(event_row["id"], status)

        logger.info("Pipeline: event=%s trace=%s recipients=%d queued=%d",
                     event_row["id"], event_row.get("trace_id"),
                     len(recipients), len(queued))

    except Exception as e:
        logger.error("Pipeline failed: %s", e)
        result["error"] = str(e)

    return result


def _mark_event_processed(event_id: str, status: str):
    try:
        from db.supabase_client import get_supabase
        from datetime import datetime, timezone
        get_supabase().table("runtime_notification_event").update({
            "event_status": status,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", event_id).execute()
    except Exception as e:
        logger.error("Event status update failed: %s — %s", event_id, e)
