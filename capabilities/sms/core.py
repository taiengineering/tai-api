"""SMS Capability Core — v1.0.0

SMS dispatch capability. Framework/DB 모름.
httpx만 사용. retry + timeout 내장.

사용:
  from capabilities.sms.core import send_sms, get_edge_url, detect_msg_type
"""
import asyncio
import logging
import os
import time
from typing import Optional

import httpx

log = logging.getLogger(__name__)

MAX_RETRIES = 2
TIMEOUT_SEC = 60


def get_edge_url() -> str:
    """Edge Function URL 결정."""
    url = os.getenv("TAI_EDGE_SMS_URL", "")
    if not url:
        sb = os.getenv("SUPABASE_URL", "")
        if sb:
            url = f"{sb}/functions/v1/send-sms"
    return url


def detect_msg_type(message: str) -> str:
    """메시지 타입 판별. SMS/LMS."""
    return "LMS" if len(message.encode("utf-8")) > 90 else "SMS"


async def call_edge(payload: dict) -> dict:
    """Edge Function SMS 호출. retry + timeout."""
    edge_url = get_edge_url()
    if not edge_url:
        raise RuntimeError("TAI_EDGE_SMS_URL 또는 SUPABASE_URL 미설정")

    internal_key = os.getenv("TAI_INTERNAL_KEY", "").strip()
    headers = {"Content-Type": "application/json"}
    if internal_key:
        headers["x-tai-key"] = internal_key

    last_error = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=TIMEOUT_SEC) as client:
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
            log.warning(f"[SMS] attempt={attempt} failed: {type(e).__name__}: {e}")
            if attempt <= MAX_RETRIES:
                await asyncio.sleep(2)
            continue
        except Exception as e:
            raise RuntimeError(f"Edge Function 호출 실패: {e}")

    raise RuntimeError(f"Edge Function {MAX_RETRIES + 1}회 시도 실패: {type(last_error).__name__}: {last_error}")


async def send_sms(receiver: str, message: str, title: Optional[str] = None) -> dict:
    """SMS dispatch. runtime queue 흡수 시도 후 Edge Function fallback."""
    try:
        from services.notification_engine.runtime_compat import compat_send_sms
        if compat_send_sms(
            receiver, message,
            event_type="API_SMS", source_engine="messaging_router",
            title=title or "TAI Safe",
        ):
            return {"success": True, "code": "QUEUED", "mode": "runtime_queue", "parsed": {"absorbed": True}}
    except Exception as e:
        log.warning("[SMS] compat SMS failed, legacy fallback: %s", e)

    payload: dict = {"receiver": receiver, "message": message}
    if title:
        payload["title"] = title
    return await call_edge(payload)
