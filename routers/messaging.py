"""
메세지미 SMS/알림톡 라우터 — v2.0.0

v2.0.0 (2026-04-09):
  [FIX] Railway → Supabase Edge Function → 메세지미 서버 구조로 변경
        (Railway 유동 IP → 메세지미 직접 연결 불가 문제 해결)
  Edge Function URL: https://xntdkrjhgcscmqctdzyo.supabase.co/functions/v1/send-sms

환경변수 (Railway):
  MESSAGEME_API_KEY   — 메세지미 API 전송키 (Edge Function Secrets에도 동일 설정 필요)
  MESSAGEME_SENDER    — 발신번호
  TAI_INTERNAL_KEY    — Edge Function 내부 인증키 (임의 문자열, 동일값으로 양쪽 설정)

Supabase Edge Function Secrets 설정:
  Dashboard → Edge Functions → send-sms → Secrets
  MESSAGEME_API_KEY, MESSAGEME_SENDER, TAI_INTERNAL_KEY 추가
"""
import logging
import os
from typing import Optional

import requests as _req
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/messaging", tags=["메시지"])

EDGE_FUNCTION_URL = "https://xntdkrjhgcscmqctdzyo.supabase.co/functions/v1/send-sms"


def _get_cfg():
    return {
        "internal_key": os.getenv("TAI_INTERNAL_KEY", ""),
    }


def _call_edge(payload: dict) -> dict:
    """Supabase Edge Function 호출."""
    cfg = _get_cfg()
    headers = {"Content-Type": "application/json"}
    if cfg["internal_key"]:
        headers["x-tai-key"] = cfg["internal_key"]

    resp = _req.post(EDGE_FUNCTION_URL, json=payload, headers=headers, timeout=30)
    try:
        result = resp.json()
    except Exception:
        result = {"raw": resp.text, "http_status": resp.status_code}

    log.info(f"[MESSAGING] Edge 호출 결과: {result}")
    return result


class SmsSendBody(BaseModel):
    receiver: str
    message:  str
    title:    Optional[str] = None
    sender:   Optional[str] = None


class AlimtalkSendBody(BaseModel):
    receiver:      str
    message:       str
    template_code: str
    variable:      Optional[str] = None
    fail_type:     Optional[str] = "sms"
    sender:        Optional[str] = None


class UnifiedSendBody(BaseModel):
    receiver:      str
    message:       str
    template_code: Optional[str] = None
    variable:      Optional[str] = None
    fail_msg:      Optional[str] = None
    sender:        Optional[str] = None


# ══════════════════════════════════════════════
# GET /messaging/debug
# ══════════════════════════════════════════════

@router.get("/debug")
def debug_messaging():
    cfg = _get_cfg()
    return {
        "status":            "ready",
        "edge_function_url": EDGE_FUNCTION_URL,
        "tai_internal_key":  "설정됨" if cfg["internal_key"] else "❌ 미설정 (선택사항)",
        "message":           "Supabase Edge Function 경유 발송 구조. "
                             "Edge Function Secrets에 MESSAGEME_API_KEY/MESSAGEME_SENDER 설정 필요.",
    }


# ══════════════════════════════════════════════
# GET /messaging/debug-send — 실제 발송 테스트
# ══════════════════════════════════════════════

@router.get("/debug-send")
def debug_send(receiver: str, message: str = "TAI Safe 테스트 메시지"):
    """Edge Function 경유 실제 발송 + 원본 응답 확인."""
    try:
        result = _call_edge({"receiver": receiver, "message": message})
        return {"source": "edge_function", "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Edge Function 호출 실패: {e}")


# ══════════════════════════════════════════════
# POST /messaging/send-sms
# ══════════════════════════════════════════════

@router.post("/send-sms")
def send_sms(body: SmsSendBody):
    try:
        payload = {"receiver": body.receiver, "message": body.message, "type": "sms"}
        if body.title:  payload["title"] = body.title
        result = _call_edge(payload)
        return {
            "status":   "success" if result.get("success") else "fail",
            "receiver": body.receiver,
            "result":   result,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SMS 발송 실패: {e}")


# ══════════════════════════════════════════════
# POST /messaging/send-alimtalk
# ══════════════════════════════════════════════

@router.post("/send-alimtalk")
def send_alimtalk(body: AlimtalkSendBody):
    try:
        payload = {
            "receiver":      body.receiver,
            "message":       body.message,
            "type":          "alimtalk",
            "template_code": body.template_code,
        }
        if body.variable: payload["variable"] = body.variable
        result = _call_edge(payload)
        return {
            "status":   "success" if result.get("success") else "fail",
            "receiver": body.receiver,
            "result":   result,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"알림톡 발송 실패: {e}")


# ══════════════════════════════════════════════
# POST /messaging/send (통합)
# ══════════════════════════════════════════════

@router.post("/send")
def send_unified(body: UnifiedSendBody):
    try:
        payload = {"receiver": body.receiver, "message": body.message}
        if body.template_code:
            payload["type"]          = "alimtalk"
            payload["template_code"] = body.template_code
            if body.variable: payload["variable"] = body.variable
        else:
            payload["type"] = "sms"
        if body.fail_msg: payload["fail_msg"] = body.fail_msg

        result = _call_edge(payload)
        return {
            "status":   "success" if result.get("success") else "fail",
            "receiver": body.receiver,
            "result":   result,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"메시지 발송 실패: {e}")
