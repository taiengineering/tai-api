"""
초대 문자 발송 — v1.0.0

작업자에게 앱 설치 초대 문자를 보낸다.

발송 경로
  capabilities.sms.core.send_sms() → Supabase Edge Function(서울) → 메세지미
  이 경로가 실제로 검증된 발송 경로다(routers/messaging.py v8.0.0 이 쓰는 것과 동일).

  services/notification_engine/adapters/sms.py 는 api.messagemi.com 을 직접
  호출하는데 그 도메인이 존재하지 않아(DNS NameResolutionError) 발송이 되지 않는다.
  검증된 적 없는 코드로 보이며, 초대 발송은 이 모듈의 경로를 쓴다.

메시지 길이
  core.detect_msg_type() 이 90바이트 초과 시 LMS 로 판별하므로 자르지 않는다.
  어댑터의 message[:90] 절단은 이 경로에 없다.
"""
import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

# 초대 링크. 코드에 적혀 있던 w.taieng.co.kr 은 프로젝트 어디에도 근거가 없어
# 실제 앱 주소를 쓴다. 환경변수로 바꿀 수 있게 둔다.
APP_INVITE_URL = os.getenv("APP_INVITE_URL", "https://safe.taieng.co.kr/app/")


def build_invite_message(name: str) -> str:
    """초대 문안.

    URL 을 앞쪽에 두어 이름이 길어도 링크가 온전하게 남도록 한다 —
    링크가 깨지면 초대의 목적 자체가 사라진다.
    """
    suffix = f"\n{name}님" if name else ""
    return f"[TAI Safe] 안전점검 앱 설치\n{APP_INVITE_URL}{suffix}"


async def send_invite_sms(phone: str, name: str = "") -> tuple[bool, Optional[str], str]:
    """초대 문자 발송.

    반환: (성공여부, 오류메시지, 발송한 메시지)
    예외를 올리지 않는다 — 호출부가 성공/실패를 명시적으로 판단하게 한다.
    """
    message = build_invite_message(name)

    try:
        from capabilities.sms.core import send_sms
        result = await send_sms(phone, message, title="TAI Safe")
    except Exception as e:
        log.error(f"[invite] SMS 발송 예외 phone={phone}: {e}")
        return False, str(e)[:200], message

    ok = bool(result.get("success"))
    if not ok:
        # code·raw 를 함께 남긴다. Edge Function 이 어떤 사유로 거절했는지
        # 알아야 발신번호 미등록·잔액 부족 등을 구분할 수 있다.
        err = f"code={result.get('code')} raw={str(result.get('raw'))[:150]}"
        log.error(f"[invite] SMS 발송 실패 phone={phone}: {err}")
        return False, err, message

    log.info(f"[invite] SMS 발송 성공 phone={phone} mode={result.get('mode')}")
    return True, None, message
