"""Event Intake — Signal 수신 → runtime_notification_event 생성.

모든 엔진은 이 모듈을 통해 이벤트를 발행한다.
Notification Engine의 유일한 입구.
"""

import logging
from typing import Optional
from .schemas import NotificationEventCreate

logger = logging.getLogger("notification_engine.intake")


def emit_event(event: NotificationEventCreate) -> Optional[dict]:
    """이벤트 생성 → DB INSERT → 생성된 row 반환.

    Fail-safe: 절대 호출자에게 예외를 전파하지 않는다.
    """
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        row = event.to_db_row()
        resp = sb.table("runtime_notification_event").insert(row).execute()

        if resp.data:
            logger.info(
                "Event emitted: type=%s engine=%s severity=%s trace=%s",
                event.event_type, event.source_engine,
                event.severity, row["trace_id"],
            )
            return resp.data[0]
        else:
            logger.error("Event INSERT returned empty: %s", event.event_type)
            return None

    except Exception as e:
        logger.error("Event intake failed: %s — %s", event.event_type, e)
        return None


def emit_from_dict(data: dict) -> Optional[dict]:
    """dict → NotificationEventCreate → emit.
    Watch Engine 등 기존 코드에서 쉽게 호출할 수 있도록.
    """
    try:
        event = NotificationEventCreate(**data)
        return emit_event(event)
    except Exception as e:
        logger.error("emit_from_dict failed: %s", e)
        return None
