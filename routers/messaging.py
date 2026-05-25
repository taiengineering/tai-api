"""
메세지미 SMS/알림톡 라우터 — v7.0.0 (Capability Wrapper Migration)

Wrapper: transport only (request parse, auth, response format)
Capability: _cap_* functions (SMS dispatch, no framework/DB dependency)

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
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/messaging", tags=["메시지"])


# ═══════════════════════════════════════════════════════
# Capability Core (_cap_*) — Framework/DB 모름
# ═══════════════════════════════════════════════════════

_CAP_MAX_RETRIES = 2
_CAP_TIMEOUT_SEC = 60

def _cap_get_edge_url() -> str:
    """Edge Function URL 결정. framework 모름."""
    url = os.getenv("TAI_EDGE_SMS_URL", "")
    if not url:
        sb = os.getenv("SUPABASE_URL", "")
        if sb:
            url = f"{sb}/functions/v1/send-sms"
    return url

def _cap_msg_type(message: str) -> str:
    """메시지 타입 판별. framework 모름."""
    return "LMS" if len(message.encode("utf-8")) > 90 else "SMS"

async def _cap_call_edge(payload: dict) -> dict:
    """Edge Function SMS 호출. framework/DB 모름. httpx만 사용."""
    edge_url = _cap_get_edge_url()
    if not edge_url:
        raise RuntimeError("TAI_EDGE_SMS_URL 또는 SUPABASE_URL 미설정")

    internal_key = os.getenv("TAI_INTERNAL_KEY", "").strip()
    headers = {"Content-Type": "application/json"}
    if internal_key:
        headers["x-tai-key"] = internal_key

    last_error = None
    for attempt in range(1, _CAP_MAX_RETRIES + 2):
        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=_CAP_TIMEOUT_SEC) as client:
                resp = await client.post(edge_url, json=payload, headers=headers)
            elapsed = round(time.time() - start, 2)

            try:
                parsed = resp.json()
            except Exception:
                parsed = {"raw": resp.text, "http_status": resp.status_code}

            return {
                "success": parsed.get("success", False),
                "code": str(parsed.get("code", "")),
                "raw": resp.text,
                "parsed": parsed,
                "mode": "edge_function(seoul)",
                "attempt": attempt,
                "elapsed_sec": elapsed,
            }
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_error = e
            log.warning(f"[MESSAGING] attempt={attempt} failed: {type(e).__name__}: {e}")
            if attempt <= _CAP_MAX_RETRIES:
                import asyncio
                await asyncio.sleep(2)
            continue
        except Exception as e:
            raise RuntimeError(f"Edge Function 호출 실패: {e}")

    raise RuntimeError(f"Edge Function {_CAP_MAX_RETRIES + 1}회 시도 실패: {type(last_error).__name__}: {last_error}")

async def _cap_dispatch_sms(receiver: str, message: str, title: Optional[str] = None) -> dict:
    """SMS dispatch. runtime queue absorption 시도 후 Edge Function fallback. framework 모름."""
    try:
        from services.notification_engine.runtime_compat import compat_send_sms
        if compat_send_sms(
            receiver, message,
            event_type="API_SMS", source_engine="messaging_router",
            title=title or "TAI Safe",
        ):
            return {"success": True, "code": "QUEUED", "mode": "runtime_queue", "parsed": {"absorbed": True}}
    except Exception as e:
        log.warning("[MESSAGING] compat SMS failed, legacy fallback: %s", e)

    payload: dict = {"receiver": receiver, "message": message}
    if title:
        payload["title"] = title
    return await _cap_call_edge(payload)


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
        result = await _cap_dispatch_sms(receiver, message)
        return {"receiver": receiver, "result": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Edge Function 호출 실패: {e}")

@router.post("/send-sms")
async def send_sms(body: SmsSendBody):
    """SMS 발송. wrapper → _cap_dispatch_sms() 호출."""
    try:
        result = await _cap_dispatch_sms(body.receiver, body.message, body.title)
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
    """알림톡 발송. wrapper → _cap_call_edge() 호출."""
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
    """통합 발송. wrapper → _cap_call_edge() 호출."""
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
