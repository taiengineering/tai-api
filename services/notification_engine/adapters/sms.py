"""SMS Adapter — notification_engine 채널.

v2.0.0: 발송 경로를 기존 SMS 모듈(capabilities.sms.core)로 교체.

  종전에는 api.messagemi.com 을 직접 호출했으나 그 도메인이 존재하지 않아
  DNS 해석에 실패했다(NameResolutionError). 즉 이 채널로 나가는 SMS 는
  모두 실패해 왔다.

  실제 검증된 발송 경로는 capabilities/sms/core.py 이며 routers/messaging.py
  v8.0.0 과 routers/worker_registry.py v1.2.0 이 그것을 쓴다.
  Supabase Edge Function(서울)을 경유해 메세지미로 나가고, retry 2회 +
  timeout 60초가 내장돼 있다.

계약 유지
  channel_registry.resolve_adapter() 가 이 모듈의 send 를 가져가며
  (bool, error) 튜플을 기대한다. core.send_sms 는 async 이므로 여기서 흡수한다.
  send_sms(message, phone) -> DeliveryResult 시그니처도 그대로 둔다.
"""

import asyncio
import logging
import os
from typing import Optional
from .delivery_result import DeliveryResult

logger = logging.getLogger("notification_engine.adapters.sms")


def send(message: str, phone: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """SMS 발송. Worker 호환 인터페이스 (bool, error)."""
    result = send_sms(message, phone)
    return result.success, result.error_message


def _run(coro):
    """동기 컨텍스트에서 async 코루틴을 실행한다.

    channel_registry 는 동기 send() 를 기대하지만 core.send_sms 는 async 다.
    이미 이벤트 루프가 돌고 있으면 별도 스레드에서 새 루프를 돌린다 —
    실행 중인 루프에 asyncio.run 을 쓰면 RuntimeError 가 난다.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


def send_sms(message: str, phone: Optional[str] = None) -> DeliveryResult:
    """SMS 발송 → DeliveryResult.

    수신번호가 없으면 NOTIFICATION_SMS_DEFAULT_PHONE 로 폴백한다(종전 동작 유지).
    """
    target_phone = phone or os.environ.get("NOTIFICATION_SMS_DEFAULT_PHONE", "")
    if not target_phone:
        return DeliveryResult(
            success=False, delivery_status="FAILED",
            error_message="SMS not configured (phone missing)",
        )

    try:
        from capabilities.sms.core import send_sms as core_send_sms
        result = _run(core_send_sms(target_phone, message, title="TAI Safe"))
    except Exception as e:
        logger.error("[sms] 발송 예외 phone=%s: %s", target_phone, e)
        return DeliveryResult(
            success=False, delivery_status="FAILED",
            error_message=str(e)[:200],
        )

    if result.get("success"):
        return DeliveryResult(
            success=True, delivery_status="DELIVERED",
            # Edge Function 은 messageId 대신 code 를 준다(정상 접수 시 100).
            external_id=str(result.get("code") or ""),
        )

    # 실패 사유에 code·raw 를 담는다. 발신번호 미등록·잔액 부족 등을 구분하려면
    # 중계사 응답 원문이 필요하다.
    err = f"code={result.get('code')} {str(result.get('raw'))[:150]}"
    logger.error("[sms] 발송 실패 phone=%s: %s", target_phone, err)
    return DeliveryResult(
        success=False, delivery_status="FAILED",
        error_message=err[:200],
    )
