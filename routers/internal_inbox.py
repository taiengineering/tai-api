"""
Internal: Inbox 알림 엔드포인트

Doc: docs/inbox-system/PHASE3_NOTIFY_ENDPOINT.md
WO-SLACK-EVENT-HUB-001 PR-①: send_inbox_notification 대신 slack_dispatcher.send_slack
를 await 로 호출한다. §6 fire-and-forget 금지 — 전송 시도 완료 후 200 반환.
Slack 실패는 business failure 가 아님 (DB trigger 는 이미 INSERT 성공 후 호출됨).
"""
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from services.inbox_notify_svc import build_blocks, fallback_title, resolve_event_type
from services.slack_dispatcher import send_slack

logger = logging.getLogger("internal_inbox")

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
    event_type = resolve_event_type(record)
    blocks = build_blocks(record)
    title = fallback_title(record)

    # §6: fire-and-forget 금지 — send_slack 완료(전송 시도 종료)까지 await.
    # Slack 자체 실패는 business rollback 을 유발하지 않음(DB trigger 는 INSERT 성공 후 호출).
    try:
        await send_slack(event_type, "INFO", title, blocks=blocks)
        sent_attempted = True
    except Exception as e:  # noqa: BLE001
        logger.warning("[internal_inbox] dispatcher call failed: %s", e)
        sent_attempted = False

    return {
        "ok": True,
        "sent": sent_attempted,
        "event_type": event_type,
        "row_id": record.get("id"),
    }
