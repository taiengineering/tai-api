"""SMS Adapter — MessageMi Runtime 흡수.

Runtime Queue 소비 → MessageMi HTTP → DeliveryResult 반환.
sms_service.py 삭제 금지. 병렬 유지.
"""

import logging
import os
from typing import Optional
from .delivery_result import DeliveryResult

logger = logging.getLogger("notification_engine.adapters.sms")


def send(message: str, phone: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """SMS 발송. Worker 호환 인터페이스 (bool, error)."""
    result = send_sms(message, phone)
    return result.success, result.error_message


def send_sms(message: str, phone: Optional[str] = None) -> DeliveryResult:
    """MessageMi SMS 발송 → DeliveryResult."""
    api_key = os.environ.get("MESSAGEMI_API_KEY", "")
    sender = os.environ.get("MESSAGEMI_SENDER", "")
    default_phone = os.environ.get("NOTIFICATION_SMS_DEFAULT_PHONE", "")
    target_phone = phone or default_phone

    if not api_key or not target_phone:
        return DeliveryResult(
            success=False, delivery_status="FAILED",
            error_message="SMS not configured (MESSAGEMI_API_KEY or phone missing)",
        )

    try:
        import requests
        url = "https://api.messagemi.com/v1/send"
        resp = requests.post(url, json={
            "apiKey": api_key,
            "sender": sender,
            "receiver": target_phone,
            "message": message[:90],
            "type": "SMS",
        }, timeout=10)

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
