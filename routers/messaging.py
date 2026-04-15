"""
메세지미 SMS/알림톡 라우터 — v4.0.0

v4.0.0 (2026-04-15):
  [CHANGE] Fly.io → 메세지미 직접 호출 (137.66.9.95 IP 예외처리 완료)
  Edge Function 경유 제거

v3.2.0: Supabase Edge Function 경유 방식 (IP 미허가 시 우회)

구조: Fly.io → 메세지미 서버 (직접)

환경변수:
  MESSAGEME_API_KEY  — 메세지미 API 전송키
  MESSAGEME_SENDER   — 발신번호 (사전 등록된 번호)
"""
import logging
import os
from typing import Optional

import requests as _req
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/messaging", tags=["메시지"])

SMS_URL      = "http://221.139.14.136/APIV2/API/sms_send"
ALIMTALK_URL = "http://221.139.14.136/APIV2/API/alimtalk_send"


def _get_cfg():
    return {
        "api_key": os.getenv("MESSAGEME_API_KEY", ""),
        "sender":  os.getenv("MESSAGEME_SENDER", ""),
    }


def _msg_type(message: str) -> str:
    return "LMS" if len(message.encode("utf-8")) > 90 else "SMS"


def _call_messageme(payload: dict, url: str) -> dict:
    """메세지미에 form-data로 직접 POST"""
    resp = _req.post(
        url,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    raw = resp.text
    try:
        parsed = resp.json()
    except Exception:
        parsed = {"raw": raw, "http_status": resp.status_code}

    code    = str(parsed.get("result", parsed.get("code", "")))
    success = (code == "100")
    log.info(f"[MESSAGING] 직접 호출 결과 (HTTP {resp.status_code}): code={code} raw={raw[:200]}")
    return {"success": success, "code": code, "raw": raw, "parsed": parsed}


# ── Pydantic 모델 ───────────────────────────────────────────────

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


# ── 디버그 ──────────────────────────────────────────────────────

@router.get("/debug")
def debug_messaging():
    cfg = _get_cfg()
    return {
        "status":    "ready",
        "mode":      "Fly.io 직접 호출 (메세지미 IP 허가 완료)",
        "sms_url":   SMS_URL,
        "api_key":   "설정됨" if cfg["api_key"] else "❌ 미설정",
        "sender":    cfg["sender"] or "❌ 미설정",
    }


@router.get("/debug-send")
def debug_send(receiver: str, message: str = "TAI Safe 테스트 메시지"):
    """SMS 테스트 발송 (GET)"""
    cfg = _get_cfg()
    if not cfg["api_key"] or not cfg["sender"]:
        raise HTTPException(status_code=503, detail="MESSAGEME_API_KEY / MESSAGEME_SENDER 미설정")
    try:
        payload = {
            "api_key":  cfg["api_key"],
            "callback": cfg["sender"],
            "dstaddr":  receiver,
            "msg":      message,
        }
        result = _call_messageme(payload, SMS_URL)
        return {"mode": "direct", "receiver": receiver, "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"메세지미 직접 호출 실패: {e}")


# ── SMS 발송 ────────────────────────────────────────────────────

@router.post("/send-sms")
def send_sms(body: SmsSendBody):
    cfg = _get_cfg()
    if not cfg["api_key"] or not cfg["sender"]:
        raise HTTPException(status_code=503, detail="MESSAGEME_API_KEY / MESSAGEME_SENDER 미설정")
    try:
        payload = {
            "api_key":  cfg["api_key"],
            "callback": cfg["sender"],
            "dstaddr":  body.receiver,
            "msg":      body.message,
        }
        if body.title:
            payload["subject"] = body.title
        result = _call_messageme(payload, SMS_URL)
        return {
            "status":   "success" if result["success"] else "fail",
            "receiver": body.receiver,
            "type":     _msg_type(body.message),
            "result":   result,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SMS 발송 실패: {e}")


# ── 알림톡 발송 ─────────────────────────────────────────────────

@router.post("/send-alimtalk")
def send_alimtalk(body: AlimtalkSendBody):
    cfg = _get_cfg()
    if not cfg["api_key"] or not cfg["sender"]:
        raise HTTPException(status_code=503, detail="MESSAGEME_API_KEY / MESSAGEME_SENDER 미설정")
    try:
        payload = {
            "api_key":       cfg["api_key"],
            "callback":      cfg["sender"],
            "dstaddr":       body.receiver,
            "template_code": body.template_code,
            "next_type":     body.fail_type or "sms",
            "msg":           body.message,
        }
        if body.variable:
            payload["variable"] = body.variable
        result = _call_messageme(payload, ALIMTALK_URL)
        return {
            "status":   "success" if result["success"] else "fail",
            "receiver": body.receiver,
            "type":     "alimtalk",
            "result":   result,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"알림톡 발송 실패: {e}")


# ── 통합 발송 ───────────────────────────────────────────────────

@router.post("/send")
def send_unified(body: UnifiedSendBody):
    cfg = _get_cfg()
    if not cfg["api_key"] or not cfg["sender"]:
        raise HTTPException(status_code=503, detail="MESSAGEME_API_KEY / MESSAGEME_SENDER 미설정")
    try:
        if body.template_code:
            # 알림톡
            payload = {
                "api_key":       cfg["api_key"],
                "callback":      cfg["sender"],
                "dstaddr":       body.receiver,
                "template_code": body.template_code,
                "next_type":     "sms",
                "msg":           body.message,
            }
            if body.variable:
                payload["variable"] = body.variable
            if body.fail_msg:
                payload["fail_msg"] = body.fail_msg
            result = _call_messageme(payload, ALIMTALK_URL)
            msg_type = "alimtalk"
        else:
            # SMS
            payload = {
                "api_key":  cfg["api_key"],
                "callback": cfg["sender"],
                "dstaddr":  body.receiver,
                "msg":      body.message,
            }
            result = _call_messageme(payload, SMS_URL)
            msg_type = _msg_type(body.message)

        return {
            "status":   "success" if result["success"] else "fail",
            "receiver": body.receiver,
            "type":     msg_type,
            "result":   result,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"메시지 발송 실패: {e}")
