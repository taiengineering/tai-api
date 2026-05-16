"""In-App Adapter — DB INSERT 기반 In-app Notification Runtime 흡수.

notification_queue 소비 → notifications 테이블 INSERT → DeliveryResult.
inbox_notify_svc.py 삭제 금지. 병렬 유지.
"""

import logging
from typing import Optional
from .delivery_result import DeliveryResult

logger = logging.getLogger("notification_engine.adapters.in_app")


def send(message: str, user_id: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """In-App 발송. Worker 호환 인터페이스 (bool, error)."""
    result = send_in_app(message, user_id)
    return result.success, result.error_message


def send_in_app(
    message: str,
    user_id: Optional[str] = None,
    title: Optional[str] = None,
    notification_type: str = "SYSTEM",
    reference_id: Optional[str] = None,
) -> DeliveryResult:
    """In-App Notification INSERT → DeliveryResult."""
    if not user_id or user_id == "00000000-0000-0000-0000-000000000000":
        return DeliveryResult(
            success=False, delivery_status="FAILED",
            error_message="IN_APP requires valid user_id",
        )

    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        row = {
            "user_id": user_id,
            "title": (title or "")[:200],
            "message": (message or "")[:2000],
            "notification_type": notification_type,
            "is_read": False,
            "reference_id": reference_id,
        }

        resp = sb.table("notifications").insert(row).execute()
        if resp.data:
            notif_id = resp.data[0].get("id")
            return DeliveryResult(
                success=True, delivery_status="DELIVERED",
                external_id=str(notif_id),
            )
        else:
            return DeliveryResult(
                success=False, delivery_status="FAILED",
                error_message="INSERT returned empty",
            )
    except Exception as e:
        return DeliveryResult(
            success=False, delivery_status="FAILED",
            error_message=str(e)[:200],
        )
