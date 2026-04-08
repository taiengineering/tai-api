"""Firebase FCM 공통 유틸리티 — v1.0.0

환경변수:
  FIREBASE_CREDENTIALS  JSON 문자열 (서비스 계정 키 전체)
"""
import json
import logging
import os
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


def get_fcm_app():
    """
    firebase_admin 앱 싱글턴 초기화.
    다중 호출 안전: _apps가 이미 있으면 기존 앱 반환.
    """
    import firebase_admin
    from firebase_admin import credentials

    if not firebase_admin._apps:
        cred_raw = os.environ.get("FIREBASE_CREDENTIALS", "")
        if not cred_raw:
            raise RuntimeError(
                "FIREBASE_CREDENTIALS 환경변수가 설정되지 않았습니다."
            )
        cred_json = json.loads(cred_raw)
        cred = credentials.Certificate(cred_json)
        firebase_admin.initialize_app(cred)

    return firebase_admin.get_app()


def send_push(
    fcm_token: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> str:
    """
    FCM 단건 푸시 발송.

    Args:
        fcm_token: 도착지 디바이스 FCM 토큰
        title: 알림 제목
        body: 알림 내용
        data: data payload (str 변환 자동)

    Returns:
        FCM 메시지 ID
    """
    get_fcm_app()
    from firebase_admin import messaging

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
    response = messaging.send(msg)
    log.info(f"[FCM] 발송 성공 token={fcm_token[:20]}... message_id={response}")
    return response
