"""
메세지미 SMS/알림톡 라우터 — v6.0.0

v6.0.0 (2026-04-29):
  [CHANGE] Supabase Edge Function(서울) 경유로 전환
  구조: Railway(싱가포르) → Supabase Edge Function(서울) → 메세지미(한국)
  메세지미는 국외 IP 차단 → 한국 리전 Edge Function에서 호출

v5.0.0: Vultr 프록시 경유 (프록시 서버 종료로 폐기)
v4.0.0: 직접 호출 (국외 IP 차단으로 폐기)

환경변수:
  SUPABASE_URL       — Supabase 프로젝트 URL (이미 설정됨)
  TAI_INTERNAL_KEY   — Edge Function 인증키 (Railway + Supabase 양쪽 동일값)
  MESSAGEME_API_KEY  — 메세지미 API 전송키 (debug 표시용, 실제 발송은 Edge Function)
  MESSAGEME_SENDER   — 발신번호 (debug 표시용)
"""
import logging
import os
from typing import Optional

import requests as _req
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/messaging", tags=["메시지"])

SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
EDGE_FUNCTION_URL = f"{SUPABASE_URL}/functions/v1/send-sms" if SUPABASE_URL else ""


def _get_cfg():
    return {
        "api_key":      os.getenv("MESSAGEME_API_KEY", ""),
        "sender":       os.getenv("MESSAGEME_SENDER", ""),
        "internal_key": os.getenv("TAI_INTERNAL_KEY", ""),
        "edge_url":     EDGE_FUNCTION_URL,
    }


def _msg_type(message: str) -> str:
    return "LMS" if len(message.encode("utf-8")) > 90 else "SMS"


def _call_edge_function(payload: dict) -> dict:
    """
    Supabase Edge Function(서울)을 통해 메세지미 호출.
    Edge Function이 한국 IP로 메세지미에 접속하므로 IP 차단 우회.
    """
    cfg = _get_cfg()
    if not cfg["edge_url"]:
        raise Exception("SUPABASE_URL 미설정 — Edge Function URL을 구성할 수 없습니다")

    headers = {
        "Content-Type": "application/json",
    }
    if cfg["internal_key"]:
        headers["x-tai-key"] = cfg["internal_key"]

    resp = _req.post(
        cfg["edge_url"],
        json=payload,
        headers=headers,
        timeout=20,
    )
    raw = resp.text
    try:
        parsed = resp.json()
    except Exception:
        parsed = {"raw": raw, "http_status": resp.status_code}

    success = parsed.get("success", False)
    code    = str(parsed.get("code", ""))
    log.info(f"[MESSAGING] mode=edge_function HTTP {resp.status_code} code={code} raw={raw[:200]}")
    return {"success": success, "code": code, "raw": raw, "parsed": parsed, "mode": "edge_function(seoul)"}


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
        "status":       "ready",
        "mode":         "Supabase Edge Function (서울) 경유",
        "edge_url":     cfg["edge_url"] or "SUPABASE_URL 미설정",
        "internal_key": "설정됨" if cfg["internal_key"] else "미설정",
        "api_key":      "설정됨" if cfg["api_key"] else "미설정 (Edge Function 환경변수에서 관리)",
        "sender":       cfg.get("sender") or "미설정",
    }


@router.get("/debug-send")
def debug_send(receiver: str, message: str = "TAI Safe 테스트 메시지"):
    """SMS 테스트 발송 (GET) — Edge Function 경유"""
    try:
        payload = {
            "receiver": receiver,
            "message":  message,
        }
        result = _call_edge_function(payload)
        return {"receiver": receiver, "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Edge Function 호출 실패: {e}")


# ── SMS 발송 ────────────────────────────────────────────────────

@router.post("/send-sms")
def send_sms(body: SmsSendBody):
    try:
        payload = {
            "receiver": body.receiver,
            "message":  body.message,
        }
        if body.title:
            payload["title"] = body.title
        result = _call_edge_function(payload)
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
    try:
        payload = {
            "receiver":      body.receiver,
            "message":       body.message,
            "type":          "alimtalk",
            "template_code": body.template_code,
        }
        if body.variable:
            payload["variable"] = body.variable
        result = _call_edge_function(payload)
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
    try:
        payload = {
            "receiver": body.receiver,
            "message":  body.message,
        }
        if body.template_code:
            payload["type"]          = "alimtalk"
            payload["template_code"] = body.template_code
            if body.variable:
                payload["variable"] = body.variable
            if body.fail_msg:
                payload["fail_msg"] = body.fail_msg

        result   = _call_edge_function(payload)
        msg_type = "alimtalk" if body.template_code else _msg_type(body.message)

        return {
            "status":   "success" if result["success"] else "fail",
            "receiver": body.receiver,
            "type":     msg_type,
            "result":   result,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"메시지 발송 실패: {e}")
