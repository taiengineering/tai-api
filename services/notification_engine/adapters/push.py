"""Push (FCM) Delivery Adapter — Compat Phase.

기존 fcm_utils.send_push()를 Notification Runtime Adapter로 래핑.
새 Push 시스템 구축 불필요 — 기존 인프라 그대로 사용.

Adapter Interface: send(message, context) -> (success, error)
"""

import logging
from typing import Tuple, Optional, Dict, Any

logger = logging.getLogger("notification_engine.adapters.push")

VERSION = "2.0.0"  # Mock → Compat (fcm_utils 실연결)


def _get_fcm_send():
    """fcm_utils.send_push 동적 import (firebase-admin 미설치 환경 대비)."""
    try:
        from utils.fcm_utils import send_push as fcm_send
        return fcm_send
    except ImportError:
        logger.warning("Push adapter: fcm_utils not available (firebase-admin missing?)")
        return None
    except Exception as e:
        logger.error("Push adapter: fcm_utils import failed: %s", e)
        return None


def send_push(
    fcm_token: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, Optional[str]]:
    """FCM Push 발송 — 기존 fcm_utils.send_push() 위임.

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

    fcm_send = _get_fcm_send()
    if not fcm_send:
        # fallback: mock logging
        logger.info(
            "[MOCK PUSH] fcm_utils unavailable — token=%s... title=%s",
            fcm_token[:20] if len(fcm_token) > 20 else fcm_token,
            title[:50],
        )
        return True, None  # mock success

    try:
        message_id = fcm_send(
            fcm_token=fcm_token,
            title=title,
            body=body,
            data=data or {},
        )
        logger.info(
            "[PUSH] sent token=%s... title=%s message_id=%s",
            fcm_token[:20] if len(fcm_token) > 20 else fcm_token,
            title[:50],
            message_id,
        )
        return True, None
    except Exception as e:
        logger.error(
            "[PUSH] failed token=%s... error=%s",
            fcm_token[:20] if len(fcm_token) > 20 else fcm_token,
            e,
        )
        return False, str(e)


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
