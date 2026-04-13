"""
메세지미 SMS/알림톡 라우터 — v3.1.0

v3.1.0 (2026-04-13):
  [FIX] 메세지미 실제 API 형식 적용
        - URL: http://221.139.14.136/APIV2/API/sms_send (IP 직접)
        - 인증: api_key 파라미터 (Bearer 아님)
        - Content-Type: application/x-www-form-urlencoded (JSON 미지원)
  [FIX] Fly.io 고정 IP(137.66.9.95)로 직접 연결

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

SMS_URL      = "http://221.139.14.136/APIV2/API/sms_send"
ALIMTALK_URL = "http://221.139.14.136/APIV2/API/alimtalk_send"


def _get_cfg():
    return {
        "api_key": os.getenv("MESSAGEME_API_KEY", ""),
        "sender":  os.getenv("MESSAGEME_SENDER", ""),
    }


def _msg_type(message: str) -> str:
    return "LMS" if len(message.encode("utf-8")) > 90 else "SMS"


def _send_sms(receiver: str, message: str, title: str = None) -> dict:
    cfg = _get_cfg()
    if not cfg["api_key"]:
        raise ValueError("MESSAGEME_API_KEY 미설정")

    params = {
        "api_key":  cfg["api_key"],
        "callback": cfg["sender"],
        "dstaddr":  receiver,
        "msg":      message,
    }
    if title:
        params["subject"] = title

    resp = _req.post(
        SMS_URL,
        data=params,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    raw = resp.text
    try:
        result = resp.json()
    except Exception:
        result = {"raw": raw}

    code    = result.get("result") or result.get("code") or ""
    success = code == "100"
    log.info(f"[MESSAGING] SMS 발송 결과: code={code}, receiver={receiver}")
    return {"success": success, "code": code, "raw": raw}


def _send_alimtalk(receiver: str, message: str, template_code: str,
                   variable: str = None, fail_type: str = "sms") -> dict:
    cfg = _get_cfg()
    if not cfg["api_key"]:
        raise ValueError("MESSAGEME_API_KEY 미설정")

    params = {
        "api_key":       cfg["api_key"],
        "callback":      cfg["sender"],
        "dstaddr":       receiver,
        "template_code": template_code,
        "next_type":     fail_type,
        "msg":           message,
    }
    if variable:
        params["variable"] = variable

    resp = _req.post(
        ALIMTALK_URL,
        data=params,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    raw = resp.text
    try:
        result = resp.json()
    except Exception:
        result = {"raw": raw}

    code    = result.get("result") or result.get("code") or ""
    success = code == "100"
    log.info(f"[MESSAGING] 알림톡 발송 결과: code={code}, receiver={receiver}")
    return {"success": success, "code": code, "raw": raw}


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


@router.get("/debug")
def debug_messaging():
    cfg = _get_cfg()
    return {
        "status":    "ready",
        "mode":      "direct (Fly.io 고정 IP: 137.66.9.95)",
        "api_key":   "설정됨" if cfg["api_key"] else "❌ 미설정",
        "sender":    cfg["sender"] or "❌ 미설정",
        "sms_url":   SMS_URL,
        "alimtalk_url": ALIMTALK_URL,
    }


@router.get("/debug-send")
def debug_send(receiver: str, message: str = "TAI Safe 테스트 메시지"):
    try:
        result = _send_sms(receiver, message)
        return {"mode": "direct", "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"발송 실패: {e}")


@router.post("/send-sms")
def send_sms(body: SmsSendBody):
    try:
        result = _send_sms(body.receiver, body.message, body.title)
        return {"status": "success" if result["success"] else "fail",
                "receiver": body.receiver, "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SMS 발송 실패: {e}")


@router.post("/send-alimtalk")
def send_alimtalk(body: AlimtalkSendBody):
    try:
        result = _send_alimtalk(body.receiver, body.message,
                                body.template_code, body.variable, body.fail_type)
        return {"status": "success" if result["success"] else "fail",
                "receiver": body.receiver, "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"알림톡 발송 실패: {e}")


@router.post("/send")
def send_unified(body: UnifiedSendBody):
    try:
        if body.template_code:
            result = _send_alimtalk(body.receiver, body.message,
                                    body.template_code, body.variable)
        else:
            result = _send_sms(body.receiver, body.message)
        return {"status": "success" if result["success"] else "fail",
                "receiver": body.receiver, "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"메시지 발송 실패: {e}")
