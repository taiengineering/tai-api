"""
Internal: Inbox 알림 엔드포인트

Doc: docs/inbox-system/PHASE3_NOTIFY_ENDPOINT.md
"""
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from services.inbox_notify_svc import send_inbox_notification

router = APIRouter(prefix="/internal/inbox", tags=["internal-inbox"])


class NotifyPayload(BaseModel):
    record: Dict[str, Any]  # 전체 inquiries row jsonb


@router.post("/notify")
async def notify_inbox(
    payload: NotifyPayload,
    x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret"),
):
    expected = os.environ.get("INTERNAL_API_SECRET")
    if not expected or x_internal_secret != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid internal secret",
        )

    record = payload.record or {}
    sent = await send_inbox_notification(record)

    return {
        "ok": True,
        "sent": sent,
        "row_id": record.get("id"),
    }
