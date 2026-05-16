"""In-App Adapter — notifications 테이블 스키마 정합 v2.

실제 notifications 테이블 컨럼:
  id, company_id, user_id, trigger_code(NOT NULL), trigger_group,
  title(NOT NULL), body, link_url, priority, is_read, read_at,
  channel, send_status, sent_at, created_at

inbox_notify_svc.py 삭제 금지. 병렬 유지.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from .delivery_result import DeliveryResult

logger = logging.getLogger("notification_engine.adapters.in_app")


def send(message: str, user_id: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Worker 호환 인터페이스 (bool, error)."""
    result = send_in_app(message, user_id)
    return result.success, result.error_message


def send_in_app(
    message: str,
    user_id: Optional[str] = None,
    title: Optional[str] = None,
    trigger_code: str = "RUNTIME_NOTIFICATION",
    trigger_group: str = "NOTIFICATION_ENGINE",
    company_id: Optional[str] = None,
    link_url: Optional[str] = None,
    priority: str = "INFO",
) -> DeliveryResult:
    """notifications 테이블 INSERT → DeliveryResult."""
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
            "trigger_code": trigger_code,
            "trigger_group": trigger_group,
            "title": (title or "TAI Safe")[:200],
            "body": (message or "")[:2000],
            "priority": priority,
            "is_read": False,
            "channel": "SITE",
            "send_status": "SENT",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        if company_id:
            row["company_id"] = company_id
        if link_url:
            row["link_url"] = link_url

        resp = sb.table("notifications").insert(row).execute()
        if resp.data:
            return DeliveryResult(
                success=True, delivery_status="DELIVERED",
                external_id=str(resp.data[0].get("id")),
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
