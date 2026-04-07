"""
메세지미 API v2 기반 SMS/알림톡 라우터 — v1.0.0

환경변수 (Railway):
  MESSAGEME_API_KEY  — API 키 (OLE1LL37ZPR0407)
  MESSAGEME_USER_ID  — 사용자 ID
  MESSAGEME_SENDER   — 발신번호 (010-XXXX-XXXX)

API:
  POST /messaging/send-sms       SMS/LMS 단일 발송
  POST /messaging/send-alimtalk  카카오 알림톡 발송
  POST /messaging/send           통합 (알림톡 우선 → 실패 시 SMS fallback)
"""
import logging
import os
from typing import Optional

import requests as _req
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/messaging", tags=["메시지"])

# ── 환경변수 ───────────────────────────────────────────
MESSAGEME_API_KEY = os.getenv("MESSAGEME_API_KEY", "")
MESSAGEME_USER_ID = os.getenv("MESSAGEME_USER_ID", "")
MESSAGEME_SENDER  = os.getenv("MESSAGEME_SENDER",  "")

SMS_URL      = "https://www.messageme.co.kr/send_api_v2.jsp"
ALIMTALK_URL = "https://www.messageme.co.kr/alimtalk_api_v2.jsp"


# ── Pydantic 모델 ───────────────────────────────────────────

class SmsSendBody(BaseModel):
    receiver: str               # 01012345678
    message:  str               # 내용 (90byte 이내 SMS, 초과 시 LMS 자동)
    title:    Optional[str] = None   # LMS 제목 (선택)
    sender:   Optional[str] = None   # 발신번호 오버라이드


class AlimtalkSendBody(BaseModel):
    receiver:      str
    message:       str
    template_code: str
    yellow_id:     str           # 카카오 마케팅 체널 ID
    fail_type:     Optional[str] = "SMS"   # 실패 시 대체발송 (SMS/LMS/None)
    fail_msg:      Optional[str] = None    # 대체발송 메시지
    fail_sender:   Optional[str] = None    # 대체발송 발신번호


class UnifiedSendBody(BaseModel):
    receiver:      str
    message:       str
    template_code: Optional[str] = None   # 있으면 알림톡 시도
    yellow_id:     Optional[str] = None
    fail_msg:      Optional[str] = None   # 알림톡 fallback SMS 내용 (없으면 message 사용)
    sender:        Optional[str] = None


# ── 내부 헬퍼 ───────────────────────────────────────────

def _cfg_check():
    if not MESSAGEME_API_KEY or not MESSAGEME_USER_ID or not MESSAGEME_SENDER:
        raise HTTPException(
            status_code=503,
            detail="MESSAGEME 환경변수가 설정되지 않았습니다. "
                   "(MESSAGEME_API_KEY / MESSAGEME_USER_ID / MESSAGEME_SENDER)"
        )


def _msg_type(message: str) -> str:
    """90바이트(한글 45자) 이초과 시 LMS."""
    return "LMS" if len(message.encode("euc-kr", errors="replace")) > 90 else "SMS"


def _send_sms_raw(
    receiver: str,
    message:  str,
    title:    Optional[str] = None,
    sender:   Optional[str] = None,
) -> dict:
    """메세지미 SMS/LMS 실제 호출."""
    msg_type = _msg_type(message)
    params = {
        "user_id":  MESSAGEME_USER_ID,
        "api_key":  MESSAGEME_API_KEY,
        "sender":   sender or MESSAGEME_SENDER,
        "receiver": receiver,
        "msg":      message,
        "msg_type": msg_type,
    }
    if title and msg_type == "LMS":
        params["title"] = title

    try:
        resp = _req.post(SMS_URL, data=params, timeout=15)
        result = resp.json() if resp.headers.get("content-type", "").startswith("application/json") \
                 else {"raw": resp.text}
        log.info(f"[MESSAGING] SMS 답변 receiver={receiver}: {result}")
        return result
    except Exception as e:
        log.error(f"[MESSAGING] SMS 실패: {e}")
        raise


def _send_alimtalk_raw(
    receiver:      str,
    message:       str,
    template_code: str,
    yellow_id:     str,
    fail_type:     Optional[str] = "SMS",
    fail_msg:      Optional[str] = None,
    fail_sender:   Optional[str] = None,
) -> dict:
    """메세지미 알림톡 실제 호출."""
    params = {
        "user_id":       MESSAGEME_USER_ID,
        "api_key":       MESSAGEME_API_KEY,
        "receiver":      receiver,
        "yellow_id":     yellow_id,
        "template_code": template_code,
        "message":       message,
    }
    if fail_type:
        params["fail_type"]   = fail_type
        params["fail_sender"] = fail_sender or MESSAGEME_SENDER
        params["fail_msg"]    = fail_msg or message

    try:
        resp = _req.post(ALIMTALK_URL, data=params, timeout=15)
        result = resp.json() if resp.headers.get("content-type", "").startswith("application/json") \
                 else {"raw": resp.text}
        log.info(f"[MESSAGING] 알림톡 답변 receiver={receiver}: {result}")
        return result
    except Exception as e:
        log.error(f"[MESSAGING] 알림톡 실패: {e}")
        raise


def _is_alimtalk_success(result: dict) -> bool:
    """알림톡 성공 여부 판단. 메세지미 result_code='1' 또는 '00'."""
    code = str(result.get("result_code") or result.get("code") or "")
    return code in ("1", "00", "0")


# ── 1. POST /messaging/send-sms ──────────────────────────────

@router.post("/send-sms")
def send_sms(body: SmsSendBody):
    """
    SMS/LMS 단일 발송.
    - 90바이트 이내: SMS
    - 90바이트 초과: LMS (제목 선택)
    """
    _cfg_check()
    try:
        result = _send_sms_raw(
            receiver=body.receiver,
            message=body.message,
            title=body.title,
            sender=body.sender,
        )
        return {
            "status":   "success",
            "method":   _msg_type(body.message),
            "receiver": body.receiver,
            "result":   result,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SMS 발송 실패: {e}")


# ── 2. POST /messaging/send-alimtalk ───────────────────────

@router.post("/send-alimtalk")
def send_alimtalk(body: AlimtalkSendBody):
    """카카오 알림톡 발송."""
    _cfg_check()
    try:
        result = _send_alimtalk_raw(
            receiver=body.receiver,
            message=body.message,
            template_code=body.template_code,
            yellow_id=body.yellow_id,
            fail_type=body.fail_type,
            fail_msg=body.fail_msg,
            fail_sender=body.fail_sender,
        )
        return {
            "status":   "success",
            "method":   "alimtalk",
            "receiver": body.receiver,
            "result":   result,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"알림톡 발송 실패: {e}")


# ── 3. POST /messaging/send (통합) ──────────────────────────

@router.post("/send")
def send_unified(body: UnifiedSendBody):
    """
    통합 발송 엔드포인트.

    1. template_code + yellow_id 있으면 → 알림톡 시도
    2. 알림톡 result_code != '1' → SMS fallback
    3. template_code 없으면 → 바로 SMS
    """
    _cfg_check()

    # ─ 알림톡 시도
    if body.template_code and body.yellow_id:
        try:
            at_result = _send_alimtalk_raw(
                receiver=body.receiver,
                message=body.message,
                template_code=body.template_code,
                yellow_id=body.yellow_id,
                fail_type="SMS",
                fail_msg=body.fail_msg or body.message,
                fail_sender=body.sender,
            )
            if _is_alimtalk_success(at_result):
                return {
                    "status":   "success",
                    "method":   "alimtalk",
                    "receiver": body.receiver,
                    "result":   at_result,
                }
            # 알림톡 실패 → SMS fallback
            log.warning(f"[MESSAGING] 알림톡 실패 → SMS fallback receiver={body.receiver}: {at_result}")
        except Exception as e:
            log.warning(f"[MESSAGING] 알림톡 예외 → SMS fallback: {e}")

    # ─ SMS 발송 (실패 fallback 또는 단독)
    try:
        sms_result = _send_sms_raw(
            receiver=body.receiver,
            message=body.fail_msg or body.message,
            sender=body.sender,
        )
        return {
            "status":   "success",
            "method":   "sms",
            "receiver": body.receiver,
            "result":   sms_result,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"메시지 발송 실패: {e}")
