"""Push (FCM) Delivery Adapter — Mock Phase.

Phase 1: Mock logging only.
Phase 2: 실제 FCM 연동 예정.

Adapter Interface: send_push(token, title, body, data) -> (success, error)
"""

import logging
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger("notification_engine.adapters.push")


def send_push(
    fcm_token: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, Optional[str]]:
    """FCM Push 발송 (Mock).

    Phase 1: 실제 FCM 연동 없이 로깅만 수행.
    Phase 2: firebase-admin SDK 연동 예정.

    Args:
        fcm_token: 대상 디바이스 FCM 토큰
        title: 알림 제목
        body: 알림 본문
        data: 추가 데이터 (optional)

    Returns:
        (success: bool, error_message: str|None)
    """
    if not fcm_token:
        logger.warning("Push adapter: empty fcm_token")
        return False, "Empty FCM token"

    # ── Mock Phase: 로깅만 수행 ──
    logger.info(
        "[MOCK PUSH] token=%s... title=%s body=%s data=%s",
        fcm_token[:20] if len(fcm_token) > 20 else fcm_token,
        title[:50],
        body[:80],
        data,
    )

    return True, None


def send(
    message: str,
    context: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, Optional[str]]:
    """Notification Engine Adapter Interface.

    worker.py에서 channel_key='PUSH'일 때 호출.
    context에 fcm_token, title, body 포함.

    Args:
        message: 발송 메시지 (body fallback)
        context: {fcm_token, title, body, data}

    Returns:
        (success: bool, error_message: str|None)
    """
    ctx = context or {}
    fcm_token = ctx.get("fcm_token", "")
    title = ctx.get("title", "TAI Safe 알림")
    body = ctx.get("body", message)
    data = ctx.get("data")

    if not fcm_token:
        logger.warning("Push adapter: no fcm_token in context")
        return False, "No FCM token in delivery context"

    return send_push(fcm_token, title, body, data)
