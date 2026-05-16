"""Compatibility Layer — Legacy direct send를 Runtime으로 유도.

Legacy 삭제 금지. 점진적 흡수.
사용법: legacy sms_service.send() 대신 compat_send_sms() 호출.
"""

import logging
from typing import Optional

logger = logging.getLogger("notification_engine.compatibility")

# source_type 허용 값
VALID_SOURCE_TYPES = {
    "runtime_alert", "runtime_incident", "workflow_event",
    "service_notice", "campaign", "maintenance_notice",
    "billing_notice", "system_notice",
}


def compat_send_sms(
    message: str,
    phone: Optional[str] = None,
    source_type: str = "service_notice",
    trace_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    triggered_by: Optional[str] = None,
) -> dict:
    """Legacy SMS → Notification Runtime Pipeline 경유."""
    try:
        from services.notification_engine.schemas import NotificationEventCreate
        from services.notification_engine.pipeline import run_pipeline
        from services.notification_engine.worker import process_queue

        event = NotificationEventCreate(
            event_type="service_sms",
            source_engine="legacy_compat",
            severity="INFO",
            trace_id=trace_id,
            tenant_id=tenant_id,
            triggered_by=triggered_by,
            payload={"phone": phone, "message": message[:90]},
            source_domain="legacy_compat.sms",
            notification_required=True,
        )

        result = run_pipeline(
            event=event,
            message_title="",
            message_body=message[:90],
            cooldown_minutes=1,
        )

        process_queue(limit=5)
        return {"status": "success", "pipeline": result}

    except Exception as e:
        logger.error("compat_send_sms failed: %s", e)
        # Fallback: legacy direct send
        try:
            from services.sms_service import send_sms as legacy_send
            legacy_send(phone, message)
            return {"status": "fallback", "method": "legacy_direct"}
        except Exception as e2:
            return {"status": "error", "message": str(e2)}


def compat_send_in_app(
    message: str,
    user_id: str,
    title: Optional[str] = None,
    notification_type: str = "SYSTEM",
    source_type: str = "service_notice",
    trace_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> dict:
    """Legacy In-App → Notification Runtime Pipeline 경유."""
    try:
        from services.notification_engine.schemas import NotificationEventCreate
        from services.notification_engine.pipeline import run_pipeline
        from services.notification_engine.worker import process_queue

        event = NotificationEventCreate(
            event_type="service_in_app",
            source_engine="legacy_compat",
            severity="INFO",
            trace_id=trace_id,
            tenant_id=tenant_id,
            triggered_by=user_id,
            payload={"user_id": user_id, "title": title, "notification_type": notification_type},
            source_domain="legacy_compat.in_app",
            notification_required=True,
        )

        result = run_pipeline(
            event=event,
            message_title=title or "",
            message_body=message,
            cooldown_minutes=1,
        )

        process_queue(limit=5)
        return {"status": "success", "pipeline": result}

    except Exception as e:
        logger.error("compat_send_in_app failed: %s", e)
        # Fallback: legacy direct
        try:
            from services.inbox_notify_svc import create_notification
            create_notification(user_id=user_id, title=title, message=message)
            return {"status": "fallback", "method": "legacy_direct"}
        except Exception as e2:
            return {"status": "error", "message": str(e2)}
