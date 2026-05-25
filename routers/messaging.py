"""
메세지미 SMS/알림톡 라우터 — v8.0.0 (Capability Consume)

Wrapper: transport only (request parse, auth, response format)
Capability: capabilities.sms.core (SMS dispatch, no framework/DB dependency)

v8.0.0 (2026-05-25): Phase 2 capability consume — inline _cap_* 제거, capabilities.sms.core import
v7.0.0 (2026-05-25): Phase 2 thin wrapper migration
v6.2.1 (2026-05-11): SMS_URL / _call_messageme 하위호환 alias
v6.2.0 (2026-04-30): 타임아웃 60초 + 재시도 2회 + httpx 비동기

환경변수:
  TAI_EDGE_SMS_URL   — Edge Function URL (최우선, 선택)
  SUPABASE_URL       — fallback
  TAI_INTERNAL_KEY   — Edge Function 인증키 (선택)
  MESSAGEME_API_KEY  — debug 표시용
  MESSAGEME_SENDER   — debug 표시용
"""
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from capabilities.sms.core import (
    send_sms as _cap_send_sms,
    call_edge as _cap_call_edge,
    get_edge_url as _cap_get_edge_url,
    detect_msg_type as _cap_msg_type,
    MAX_RETRIES as _CAP_MAX_RETRIES,
    TIMEOUT_SEC as _CAP_TIMEOUT_SEC,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/messaging", tags=["메시지"])


# ── 하위호환 alias (law_collector 등에서 import) ────────────────
EDGE_SMS_URL = _cap_get_edge_url()
SMS_URL = EDGE_SMS_URL
_call_edge_function = _cap_call_edge
_call_messageme = _cap_call_edge


# ═══════════════════════════════════════════════════════
# Pydantic 모델
# ═══════════════════════════════════════════════════════

class SmsSendBody(BaseModel):
    receiver: str
    message:  str
    title:    Optional[str] = None

class AlimtalkSendBody(BaseModel):
    receiver:      str
    message:       str
    template_code: str
    variable:      Optional[str] = None
    fail_type:     Optional[str] = "sms"

class UnifiedSendBody(BaseModel):
    receiver:      str
    message:       str
    template_code: Optional[str] = None
    variable:      Optional[str] = None
    fail_msg:      Optional[str] = None


# ═══════════════════════════════════════════════════════
# Wrapper (transport only)
# ═══════════════════════════════════════════════════════

@router.get("/debug")
def debug_messaging():
    """디버그 정보. wrapper: transport only."""
    cfg_key = os.getenv("TAI_INTERNAL_KEY", "")
    return {
        "status": "ready", "mode": "Supabase Edge Function (서울) 경유",
        "edge_url": _cap_get_edge_url() or "미설정",
        "internal_key": "설정됨" if cfg_key else "미설정 (선택)",
        "api_key": "설정됨" if os.getenv("MESSAGEME_API_KEY") else "Edge Function에서 관리",
        "sender": os.getenv("MESSAGEME_SENDER") or "Edge Function에서 관리",
        "timeout": f"{_CAP_TIMEOUT_SEC}s", "max_retries": _CAP_MAX_RETRIES,
    }

@router.get("/debug-send")
async def debug_send(receiver: str, message: str = "TAI Safe 테스트 메시지"):
    """SMS 테스트 발송. wrapper → capability core 호출."""
    try:
        result = await _cap_send_sms(receiver, message)
        return {"receiver": receiver, "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Edge Function 호출 실패: {e}")

@router.post("/send-sms")
async def send_sms(body: SmsSendBody):
    """SMS 발송. wrapper → capabilities.sms.core.send_sms() 호출."""
    try:
        result = await _cap_send_sms(body.receiver, body.message, body.title)
        return {
            "status": "success" if result["success"] else "fail",
            "receiver": body.receiver,
            "type": _cap_msg_type(body.message),
            "result": result,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SMS 발송 실패: {e}")

@router.post("/send-alimtalk")
async def send_alimtalk(body: AlimtalkSendBody):
    """알림톡 발송. wrapper → capabilities.sms.core.call_edge() 호출."""
    try:
        payload = {
            "receiver": body.receiver, "message": body.message,
            "type": "alimtalk", "template_code": body.template_code,
        }
        if body.variable:
            payload["variable"] = body.variable
        result = await _cap_call_edge(payload)
        return {
            "status": "success" if result["success"] else "fail",
            "receiver": body.receiver, "type": "alimtalk", "result": result,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"알림톡 발송 실패: {e}")

@router.post("/send")
async def send_unified(body: UnifiedSendBody):
    """통합 발송. wrapper → capabilities.sms.core.call_edge() 호출."""
    try:
        payload = {"receiver": body.receiver, "message": body.message}
        if body.template_code:
            payload["type"] = "alimtalk"
            payload["template_code"] = body.template_code
            if body.variable:
                payload["variable"] = body.variable
            if body.fail_msg:
                payload["fail_msg"] = body.fail_msg
        result = await _cap_call_edge(payload)
        msg_type = "alimtalk" if body.template_code else _cap_msg_type(body.message)
        return {
            "status": "success" if result["success"] else "fail",
            "receiver": body.receiver, "type": msg_type, "result": result,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"메시지 발송 실패: {e}")
