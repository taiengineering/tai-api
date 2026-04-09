"""
메세지미 API v2 기반 SMS/알림톡 라우터 — v1.3.0

v1.3.0 (2026-04-09):
  [FIX] SMS URL: http://221.139.14.136/APIV2/API/sms_send (HTTPS 미지원, IP 기반)
  [FIX] 파라미터명: sender→callback, receiver→dstaddr, 제목→subject
  [FIX] user_id 파라미터 제거 (api_key만 사용)
  [FIX] 성공 코드: 100 (기존 1/00/0 → 100)
  [FIX] 알림톡 URL: http://221.139.14.136/APIV2/API/alimtalk_send

환경변수 (Railway):
  MESSAGEME_API_KEY  — API 전송키
  MESSAGEME_SENDER   — 발신번호 (사전 등록된 번호, 예: 01047758888)
"""
import logging
import os
from typing import Optional

import requests as _req
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/messaging", tags=["메시지"])

SMS_URL      = "http://221.139.14.136/APIV2/API/sms_send"
ALIMTALK_URL = "http://221.139.14.136/APIV2/API/alimtalk_send"


def _get_cfg():
    return {
        "api_key": os.getenv("MESSAGEME_API_KEY", ""),
        "sender":  os.getenv("MESSAGEME_SENDER",  ""),
    }


def _cfg_check():
    cfg = _get_cfg()
    missing = [k for k, v in cfg.items() if not v]
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"MESSAGEME 환경변수 미설정: {missing} "
                   "(MESSAGEME_API_KEY / MESSAGEME_SENDER)"
        )
    return cfg


class SmsSendBody(BaseModel):
    receiver: str               # 수신번호 (dstaddr)
    message:  str               # 메시지 내용
    title:    Optional[str] = None   # 제목 (LMS/MMS)
    sender:   Optional[str] = None   # 발신번호 오버라이드


class AlimtalkSendBody(BaseModel):
    receiver:      str
    template_code: str
    variable:      Optional[str] = None   # 변수값 (|로 구분)
    fail_type:     Optional[str] = "sms"  # 실패 시 대체발송
    fail_message:  Optional[str] = None
    sender:        Optional[str] = None


class UnifiedSendBody(BaseModel):
    receiver:      str
    message:       str
    template_code: Optional[str] = None
    variable:      Optional[str] = None
    fail_msg:      Optional[str] = None
    sender:        Optional[str] = None


def _msg_type(message: str) -> str:
    """90바이트(한글 45자) 초과 시 LMS."""
    return "LMS" if len(message.encode("euc-kr", errors="replace")) > 90 else "SMS"


def _send_sms_raw(cfg: dict, receiver: str, message: str,
                  title: Optional[str] = None, sender: Optional[str] = None) -> dict:
    msg_type = _msg_type(message)
    params = {
        "api_key":  cfg["api_key"],
        "callback": sender or cfg["sender"],   # 발신번호
        "dstaddr":  receiver,                  # 수신번호
        "msg":      message,
    }
    if title and msg_type in ("LMS", "MMS"):
        params["subject"] = title

    resp = _req.post(SMS_URL, data=params, timeout=15)
    raw  = resp.text
    try:
        result = resp.json()
    except Exception:
        result = {"raw": raw}

    log.info(f"[MESSAGING] SMS status={resp.status_code} receiver={receiver} result={result}")
    return result


def _send_alimtalk_raw(cfg: dict, receiver: str, template_code: str,
                        variable: Optional[str] = None,
                        fail_type: Optional[str] = "sms",
                        fail_message: Optional[str] = None,
                        sender: Optional[str] = None) -> dict:
    params = {
        "api_key":       cfg["api_key"],
        "callback":      sender or cfg["sender"],
        "dstaddr":       receiver,
        "template_code": template_code,
    }
    if variable:
        params["variable"] = variable
    if fail_type:
        params["next_type"] = fail_type
    if fail_message:
        params["msg"] = fail_message

    resp = _req.post(ALIMTALK_URL, data=params, timeout=15)
    try:
        result = resp.json()
    except Exception:
        result = {"raw": resp.text}

    log.info(f"[MESSAGING] 알림톡 status={resp.status_code} receiver={receiver} result={result}")
    return result


def _is_success(result: dict) -> bool:
    """메세지미 성공 코드: 100"""
    code = str(result.get("code") or result.get("result_code") or "")
    return code == "100"


# ══════════════════════════════════════════════
# GET /messaging/debug
# ══════════════════════════════════════════════

@router.get("/debug")
def debug_messaging():
    cfg = _get_cfg()
    env_status = {
        "MESSAGEME_API_KEY": f"{'설정됨 (' + cfg['api_key'][:4] + '***)' if cfg['api_key'] else '❌ 미설정'}",
        "MESSAGEME_SENDER":  f"{'설정됨 (' + cfg['sender'] + ')' if cfg['sender'] else '❌ 미설정'}",
    }
    all_set = all([cfg["api_key"], cfg["sender"]])
    return {
        "status":   "ready" if all_set else "config_error",
        "env":      env_status,
        "all_set":  all_set,
        "sms_url":  SMS_URL,
        "message":  "환경변수 정상." if all_set else "❌ 미설정 항목 있음.",
    }


# ══════════════════════════════════════════════
# GET /messaging/debug-send — 실제 발송 + 원본 응답
# ══════════════════════════════════════════════

@router.get("/debug-send")
def debug_send(
    receiver: str = Query(...),
    message:  str = Query("TAI Safe 테스트 메시지"),
):
    """실제 SMS 발송 후 메세지미 원본 응답 반환. 성공 코드: 100"""
    cfg = _cfg_check()
    params = {
        "api_key":  cfg["api_key"],
        "callback": cfg["sender"],
        "dstaddr":  receiver,
        "msg":      message,
    }
    try:
        resp = _req.post(SMS_URL, data=params, timeout=15)
        raw  = resp.text
        try:
            parsed = resp.json()
        except Exception:
            parsed = None
        return {
            "http_status":   resp.status_code,
            "raw":           raw,
            "parsed":        parsed,
            "success":       _is_success(parsed or {}),
            "params_sent":   {k: v for k, v in params.items() if k != "api_key"},
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"메세지미 호출 실패: {e}")


# ══════════════════════════════════════════════
# POST /messaging/send-sms
# ══════════════════════════════════════════════

@router.post("/send-sms")
def send_sms(body: SmsSendBody):
    cfg = _cfg_check()
    try:
        result = _send_sms_raw(cfg, body.receiver, body.message, body.title, body.sender)
        return {
            "status":   "success" if _is_success(result) else "fail",
            "method":   _msg_type(body.message),
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
    cfg = _cfg_check()
    try:
        result = _send_alimtalk_raw(
            cfg, body.receiver, body.template_code,
            body.variable, body.fail_type, body.fail_message, body.sender,
        )
        return {
            "status":   "success" if _is_success(result) else "fail",
            "method":   "alimtalk",
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
    cfg = _cfg_check()

    if body.template_code:
        try:
            at_result = _send_alimtalk_raw(
                cfg, body.receiver, body.template_code,
                body.variable, "sms", body.fail_msg or body.message, body.sender,
            )
            if _is_success(at_result):
                return {"status": "success", "method": "alimtalk",
                        "receiver": body.receiver, "result": at_result}
            log.warning(f"[MESSAGING] 알림톡 실패 → SMS fallback: {at_result}")
        except Exception as e:
            log.warning(f"[MESSAGING] 알림톡 예외 → SMS fallback: {e}")

    try:
        sms_result = _send_sms_raw(
            cfg, body.receiver, body.fail_msg or body.message, sender=body.sender
        )
        return {"status": "success" if _is_success(sms_result) else "fail",
                "method": "sms", "receiver": body.receiver, "result": sms_result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"메시지 발송 실패: {e}")
