"""SMS 발송 — 메세지미 연동 (routers.messaging 단일 구현 재사용)."""
from __future__ import annotations

from typing import Any, Optional


def send_sms(receiver: str, message: str, title: Optional[str] = None) -> dict[str, Any]:
    """
    receiver: 국내 휴대폰 번호(하이픈 허용)
    반환: messaging.send_sms와 동일 구조 dict
    """
    from routers.messaging import SmsSendBody, send_sms as messaging_send_sms

    return messaging_send_sms(SmsSendBody(receiver=receiver, message=message, title=title))
