"""
메세지미 SMS/알림톡 라우터 — v3.0.0

v3.0.0 (2026-04-13):
  [FIX] Fly.io 고정 IP(137.66.9.95) 확보로 메세지미 직접 연결 가능
        Supabase Edge Function 우회 구조 제거 → 단순화
  메세지미 IP 화이트리스트에 137.66.9.95 등록 필요

v2.0.0: Supabase Edge Function 경유 구조 (Railway 유동 IP 문제 해결용)
v1.0.0: 메세지미 직접 연결

환경변수:
  MESSAGEME_API_KEY   — 메세지미 API 전송키
  MESSAGEME_SENDER    — 발신번호
"""
import logging
import os
from typing import Optional

import requests as _req
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/messaging", tags=["메시지"])

MESSAGEME_API_URL = "https://api.messageme.co.kr/api/v1/send"


def _get_cfg():
    return {
        "api_key": os.getenv("MESSAGEME_API_KEY", ""),
        "sender":  os.getenv("MESSAGEME_SENDER", ""),
    }


def _call_messageme(payload: dict) -> dict:
    """메세지미 API 직접 호출."""
    cfg = _get_cfg()
    if not cfg["api_key"]:
        raise ValueError("MESSAGEME_API_KEY 미설정")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }

    resp = _req.post(MESSAGEME_API_URL, json=payload, headers=headers, timeout=30)
    try:
        result = resp.json()
    except Exception:
        result = {"raw": resp.text, "http_status": resp.status_code}

    log.info(f"[MESSAGING] 메세지미 직접 호출 결과: {result}")
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
        "status":          "ready",
        "mode":            "direct (Fly.io 고정 IP: 137.66.9.95)",
        "api_key":         "설정됨" if cfg["api_key"] else "❌ 미설정",
        "sender":          cfg["sender"] or "❌ 미설정",
        "messageme_url":   MESSAGEME_API_URL,
        "message":         "메세지미 IP 화이트리스트에 137.66.9.95 등록 필요",
    }


# ══════════════════════════════════════════════
# GET /messaging/debug-send — 실제 발송 테스트
# ══════════════════════════════════════════════

@router.get("/debug-send")
def debug_send(receiver: str, message: str = "TAI Safe 테스트 메시지"):
    """메세지미 직접 발송 테스트."""
    cfg = _get_cfg()
    try:
        payload = {
            "receiver": receiver,
            "message":  message,
            "type":     "sms",
            "sender":   cfg["sender"],
        }
        result = _call_messageme(payload)
        return {"mode": "direct", "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"발송 실패: {e}")


# ══════════════════════════════════════════════
# POST /messaging/send-sms
# ══════════════════════════════════════════════

@router.post("/send-sms")
def send_sms(body: SmsSendBody):
    cfg = _get_cfg()
    try:
        payload = {
            "receiver": body.receiver,
            "message":  body.message,
            "type":     "sms",
            "sender":   body.sender or cfg["sender"],
        }
        if body.title:
            payload["title"] = body.title
        result = _call_messageme(payload)
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
    cfg = _get_cfg()
    try:
        payload = {
            "receiver":      body.receiver,
            "message":       body.message,
            "type":          "alimtalk",
            "template_code": body.template_code,
            "sender":        body.sender or cfg["sender"],
        }
        if body.variable:
            payload["variable"] = body.variable
        if body.fail_type:
            payload["fail_type"] = body.fail_type
        result = _call_messageme(payload)
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
    cfg = _get_cfg()
    try:
        payload = {
            "receiver": body.receiver,
            "message":  body.message,
            "sender":   body.sender or cfg["sender"],
        }
        if body.template_code:
            payload["type"]          = "alimtalk"
            payload["template_code"] = body.template_code
            if body.variable:
                payload["variable"] = body.variable
        else:
            payload["type"] = "sms"
        if body.fail_msg:
            payload["fail_msg"] = body.fail_msg

        result = _call_messageme(payload)
        return {
            "status":   "success" if result.get("success") else "fail",
            "receiver": body.receiver,
            "result":   result,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"메시지 발송 실패: {e}")
