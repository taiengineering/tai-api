"""
Firebase FCM 공통 유틸리티 — v1.0.0

환경변수:
  FIREBASE_CREDENTIALS — Firebase 서비스 계정 JSON 전체 (Railway Variables)
"""
import json
import logging
import os
from typing import Optional

log = logging.getLogger(__name__)


def get_fcm_app():
    """Firebase 앱 싱글턴 초기화."""
    try:
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:
            cred_raw = os.environ.get("FIREBASE_CREDENTIALS", "")
            if not cred_raw:
                raise RuntimeError("FIREBASE_CREDENTIALS 환경변수가 없습니다.")
            cred_json = json.loads(cred_raw)
            cred = credentials.Certificate(cred_json)
            firebase_admin.initialize_app(cred)

        return firebase_admin.get_app()
    except ImportError:
        raise RuntimeError(
            "firebase-admin 패키지가 설치되지 않았습니다. "
            "pip install firebase-admin"
        )


def send_push(
    fcm_token: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> str:
    """
    FCM 단건 발송.

    Returns:
        FCM message_id
    Raises:
        Exception: 발송 실패 시
    """
    from firebase_admin import messaging

    get_fcm_app()

    msg = messaging.Message(
        token=fcm_token,
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
        android=messaging.AndroidConfig(priority="high"),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default", badge=1)
            )
        ),
    )

    message_id = messaging.send(msg)
    log.info(f"[FCM] 전송 성공 token={fcm_token[:20]}... id={message_id}")
    return message_id


def send_push_safe(
    fcm_token: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> dict:
    """
    FCM 발송 (예외 안전 버전).
    Returns: {"ok": bool, "message_id": str | None, "error": str | None}
    """
    try:
        mid = send_push(fcm_token, title, body, data)
        return {"ok": True, "message_id": mid, "error": None}
    except Exception as e:
        log.error(f"[FCM] 전송 실패 token={fcm_token[:20]}...: {e}")
        return {"ok": False, "message_id": None, "error": str(e)}
