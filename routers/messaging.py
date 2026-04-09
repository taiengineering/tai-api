"""
메세지미 API v2 기반 SMS/알림톡 라우터 — v1.2.0

v1.2.0:
  [ADD] GET /messaging/debug-send?receiver=&message= — 실제 발송 + 메세지미 원본 응답 반환
v1.1.0:
  [FIX] 환경변수 런타임 로딩
  [ADD] GET /messaging/debug

환경변수 (Railway):
  MESSAGEME_API_KEY  — API 전송키
  MESSAGEME_USER_ID  — 메세지미 로그인 아이디
  MESSAGEME_SENDER   — 발신번호 (01012345678 형식)
"""
import logging
import os
from typing import Optional

import requests as _req
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/messaging", tags=["메시지"])

SMS_URL      = "https://www.messageme.co.kr/send_api_v2.jsp"
ALIMTALK_URL = "https://www.messageme.co.kr/alimtalk_api_v2.jsp"


def _get_cfg():
    return {
        "api_key": os.getenv("MESSAGEME_API_KEY", ""),
        "user_id": os.getenv("MESSAGEME_USER_ID", ""),
        "sender":  os.getenv("MESSAGEME_SENDER",  ""),
    }


def _cfg_check():
    cfg = _get_cfg()
    missing = [k for k, v in cfg.items() if not v]
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"MESSAGEME 환경변수 미설정: {missing} "
                   "(MESSAGEME_API_KEY / MESSAGEME_USER_ID / MESSAGEME_SENDER)"
        )
    return cfg


class SmsSendBody(BaseModel):
    receiver: str
    message:  str
    title:    Optional[str] = None
    sender:   Optional[str] = None


class AlimtalkSendBody(BaseModel):
    receiver:      str
    message:       str
    template_code: str
    yellow_id:     str
    fail_type:     Optional[str] = "SMS"
    fail_msg:      Optional[str] = None
    fail_sender:   Optional[str] = None


class UnifiedSendBody(BaseModel):
    receiver:      str
    message:       str
    template_code: Optional[str] = None
    yellow_id:     Optional[str] = None
    fail_msg:      Optional[str] = None
    sender:        Optional[str] = None


def _msg_type(message: str) -> str:
    return "LMS" if len(message.encode("euc-kr", errors="replace")) > 90 else "SMS"


def _send_sms_raw(cfg: dict, receiver: str, message: str,
                  title: Optional[str] = None, sender: Optional[str] = None) -> dict:
    msg_type = _msg_type(message)
    params = {
        "user_id":  cfg["user_id"],
        "api_key":  cfg["api_key"],
        "sender":   sender or cfg["sender"],
        "receiver": receiver,
        "msg":      message,
        "msg_type": msg_type,
    }
    if title and msg_type == "LMS":
        params["title"] = title

    resp = _req.post(SMS_URL, data=params, timeout=15)
    raw  = resp.text
    try:
        result = resp.json()
    except Exception:
        result = {"raw": raw}

    log.info(f"[MESSAGING] SMS status={resp.status_code} receiver={receiver} result={result}")
    return result


def _send_alimtalk_raw(cfg: dict, receiver: str, message: str,
                        template_code: str, yellow_id: str,
                        fail_type: Optional[str] = "SMS",
                        fail_msg: Optional[str] = None,
                        fail_sender: Optional[str] = None) -> dict:
    params = {
        "user_id":       cfg["user_id"],
        "api_key":       cfg["api_key"],
        "receiver":      receiver,
        "yellow_id":     yellow_id,
        "template_code": template_code,
        "message":       message,
    }
    if fail_type:
        params["fail_type"]   = fail_type
        params["fail_sender"] = fail_sender or cfg["sender"]
        params["fail_msg"]    = fail_msg or message

    resp = _req.post(ALIMTALK_URL, data=params, timeout=15)
    try:
        result = resp.json()
    except Exception:
        result = {"raw": resp.text}

    log.info(f"[MESSAGING] 알림톡 status={resp.status_code} receiver={receiver} result={result}")
    return result


def _is_alimtalk_success(result: dict) -> bool:
    code = str(result.get("result_code") or result.get("code") or "")
    return code in ("1", "00", "0")


# ══════════════════════════════════════════════
# GET /messaging/debug — 환경변수 상태 확인
# ══════════════════════════════════════════════

@router.get("/debug")
def debug_messaging():
    cfg = _get_cfg()
    env_status = {
        "MESSAGEME_API_KEY": f"{'설정됨 (' + cfg['api_key'][:4] + '***)' if cfg['api_key'] else '❌ 미설정'}",
        "MESSAGEME_USER_ID": f"{'설정됨 (' + cfg['user_id'] + ')' if cfg['user_id'] else '❌ 미설정'}",
        "MESSAGEME_SENDER":  f"{'설정됨 (' + cfg['sender'] + ')' if cfg['sender'] else '❌ 미설정'}",
    }
    all_set = all([cfg["api_key"], cfg["user_id"], cfg["sender"]])
    return {
        "status":  "ready" if all_set else "config_error",
        "env":     env_status,
        "all_set": all_set,
        "message": "환경변수 정상." if all_set else "❌ 미설정 항목 있음.",
    }


# ══════════════════════════════════════════════
# GET /messaging/debug-send — 실제 발송 + 원본 응답 확인
# ══════════════════════════════════════════════

@router.get("/debug-send")
def debug_send(
    receiver: str = Query(...),
    message:  str = Query("TAI Safe 테스트 메시지"),
):
    """
    실제 SMS 발송 후 메세지미 원본 응답을 그대로 반환.
    result_code=1 이면 성공, 그 외는 실패.
    """
    cfg = _cfg_check()
    msg_type = _msg_type(message)
    params = {
        "user_id":  cfg["user_id"],
        "api_key":  cfg["api_key"],
        "sender":   cfg["sender"],
        "receiver": receiver,
        "msg":      message,
        "msg_type": msg_type,
    }

    try:
        resp = _req.post(SMS_URL, data=params, timeout=15)
        http_status = resp.status_code
        raw_text    = resp.text
        try:
            parsed = resp.json()
        except Exception:
            parsed = None

        return {
            "http_status": http_status,
            "raw":         raw_text,
            "parsed":      parsed,
            "params_sent": {k: v for k, v in params.items() if k != "api_key"},  # api_key 제외
            "msg_type":    msg_type,
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
            "status":   "success",
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
            cfg, body.receiver, body.message,
            body.template_code, body.yellow_id,
            body.fail_type, body.fail_msg, body.fail_sender,
        )
        return {
            "status":   "success",
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

    if body.template_code and body.yellow_id:
        try:
            at_result = _send_alimtalk_raw(
                cfg, body.receiver, body.message,
                body.template_code, body.yellow_id,
                "SMS", body.fail_msg or body.message, body.sender,
            )
            if _is_alimtalk_success(at_result):
                return {"status": "success", "method": "alimtalk",
                        "receiver": body.receiver, "result": at_result}
            log.warning(f"[MESSAGING] 알림톡 실패 → SMS fallback: {at_result}")
        except Exception as e:
            log.warning(f"[MESSAGING] 알림톡 예외 → SMS fallback: {e}")

    try:
        sms_result = _send_sms_raw(cfg, body.receiver, body.fail_msg or body.message, sender=body.sender)
        return {"status": "success", "method": "sms",
                "receiver": body.receiver, "result": sms_result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"메시지 발송 실패: {e}")
