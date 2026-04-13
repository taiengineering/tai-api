"""
메세지미 SMS/알림톡 라우터 — v3.2.0

v3.2.0 (2026-04-13):
  [FIX] Supabase Edge Function 경유 방식으로 복구
        메세지미가 Supabase IP만 허용 (Fly.io IP 미허가)
        TAI_INTERNAL_KEY 없어도 작동하도록 수정

구조: Fly.io → Supabase Edge Function → 메세지미 서버

환경변수:
  MESSAGEME_API_KEY   — 메세지미 API 전송키 (Edge Function Secrets에도 동일 설정)
  MESSAGEME_SENDER    — 발신번호 (Edge Function Secrets에도 동일 설정)
  TAI_INTERNAL_KEY    — 선택사항 (없으면 인증 없이 호출)
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
    cfg = _get_cfg()
    headers = {"Content-Type": "application/json"}
    if cfg["internal_key"]:
        headers["x-tai-key"] = cfg["internal_key"]

    resp = _req.post(EDGE_FUNCTION_URL, json=payload, headers=headers, timeout=30)
    try:
        result = resp.json()
    except Exception:
        result = {"raw": resp.text, "http_status": resp.status_code}

    log.info(f"[MESSAGING] Edge 호출 결과 (status={resp.status_code}): {result}")
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


@router.get("/debug")
def debug_messaging():
    cfg = _get_cfg()
    return {
        "status":          "ready",
        "mode":            "Supabase Edge Function 경유 (메세지미 IP 허가 방식)",
        "edge_url":        EDGE_FUNCTION_URL,
        "tai_internal_key": "설정됨" if cfg["internal_key"] else "미설정 (인증 없이 호출)",
    }


@router.get("/debug-send")
def debug_send(receiver: str, message: str = "TAI Safe 테스트 메시지"):
    try:
        result = _call_edge({"receiver": receiver, "message": message, "type": "sms"})
        return {"mode": "edge_function", "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Edge Function 호출 실패: {e}")


@router.post("/send-sms")
def send_sms(body: SmsSendBody):
    try:
        payload = {"receiver": body.receiver, "message": body.message, "type": "sms"}
        if body.title:
            payload["title"] = body.title
        result = _call_edge(payload)
        return {"status": "success" if result.get("success") else "fail",
                "receiver": body.receiver, "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SMS 발송 실패: {e}")


@router.post("/send-alimtalk")
def send_alimtalk(body: AlimtalkSendBody):
    try:
        payload = {
            "receiver":      body.receiver,
            "message":       body.message,
            "type":          "alimtalk",
            "template_code": body.template_code,
        }
        if body.variable:
            payload["variable"] = body.variable
        if body.fail_type:
            payload["fail_type"] = body.fail_type
        result = _call_edge(payload)
        return {"status": "success" if result.get("success") else "fail",
                "receiver": body.receiver, "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"알림톡 발송 실패: {e}")


@router.post("/send")
def send_unified(body: UnifiedSendBody):
    try:
        payload = {"receiver": body.receiver, "message": body.message}
        if body.template_code:
            payload["type"] = "alimtalk"
            payload["template_code"] = body.template_code
            if body.variable:
                payload["variable"] = body.variable
        else:
            payload["type"] = "sms"
        if body.fail_msg:
            payload["fail_msg"] = body.fail_msg
        result = _call_edge(payload)
        return {"status": "success" if result.get("success") else "fail",
                "receiver": body.receiver, "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"메시지 발송 실패: {e}")
