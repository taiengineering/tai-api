"""SMS Adapter — MessageMi Runtime 흡수.

Runtime Queue 소비 → MessageMi HTTP → DeliveryResult 반환.
sms_service.py 삭제 금지. 병렬 유지.

v1.1.0: 환경변수 이름 폴백 추가.
  Railway 에는 MESSAGEME_* (ME) 로 설정돼 있는데 이 어댑터는 MESSAGEMI_* (MI) 를
  읽고 있어, 키가 있어도 "SMS not configured" 로 실패했다. 서비스명이 '메시지미'라
  MI 로 적었으나 실제 설정은 ME 다. 어느 쪽이 표준인지 확정되기 전까지 양쪽을
  모두 읽는다. Railway 변수를 건드리면 이 값을 쓰는 다른 코드(sms_service.py 등)가
  깨질 수 있어 어댑터에서 흡수한다.
"""

import logging
import os
from typing import Optional
from .delivery_result import DeliveryResult

logger = logging.getLogger("notification_engine.adapters.sms")


def _env(*names: str, default: str = "") -> str:
    """여러 후보 이름 중 먼저 설정된 값을 돌려준다."""
    for n in names:
        v = os.environ.get(n, "")
        if v:
            return v
    return default


def send(message: str, phone: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """SMS 발송. Worker 호환 인터페이스 (bool, error)."""
    result = send_sms(message, phone)
    return result.success, result.error_message


def send_sms(message: str, phone: Optional[str] = None) -> DeliveryResult:
    """MessageMi SMS 발송 → DeliveryResult."""
    # MI/ME 양쪽 표기를 모두 허용한다(위 모듈 주석 참조).
    api_key = _env("MESSAGEMI_API_KEY", "MESSAGEME_API_KEY")
    sender = _env("MESSAGEMI_SENDER", "MESSAGEME_SENDER")
    user_id = _env("MESSAGEMI_USER_ID", "MESSAGEME_USER_ID")
    default_phone = os.environ.get("NOTIFICATION_SMS_DEFAULT_PHONE", "")
    target_phone = phone or default_phone

    if not api_key or not target_phone:
        # 어느 쪽이 비었는지 구분해 남긴다. 종전에는 한 문장이라 원인을 알 수 없었다.
        missing = []
        if not api_key:
            missing.append("api_key")
        if not target_phone:
            missing.append("phone")
        return DeliveryResult(
            success=False, delivery_status="FAILED",
            error_message=f"SMS not configured (missing: {', '.join(missing)})",
        )

    try:
        import requests
        url = "https://api.messagemi.com/v1/send"
        payload = {
            "apiKey": api_key,
            "sender": sender,
            "receiver": target_phone,
            "message": message[:90],
            "type": "SMS",
        }
        # 계정 식별자를 요구하는 계약일 수 있어, 설정돼 있으면 함께 보낸다.
        if user_id:
            payload["userId"] = user_id

        resp = requests.post(url, json=payload, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            return DeliveryResult(
                success=True, delivery_status="DELIVERED",
                external_id=data.get("messageId"),
            )
        else:
            return DeliveryResult(
                success=False, delivery_status="FAILED",
                error_message=f"SMS {resp.status_code}: {resp.text[:200]}",
            )
    except Exception as e:
        return DeliveryResult(
            success=False, delivery_status="FAILED",
            error_message=str(e)[:200],
        )
