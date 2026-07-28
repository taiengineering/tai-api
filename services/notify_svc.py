"""통합 발송 디스패처 (WO-8C NotifyDispatcher).

Goal: G-ms4je4z3-33eada
- 단일 진입점 send(channel, ...): SMS(capability) / MAIL(gmail_channel) / PUSH(fcm 예약).
- 채널별 기존 자산 위임(로직 중복 금지). 각 채널 실패는 표준 결과로 반환.
- DryRunPreview: 대량발송 전 대상 수·샘플 확인(안전장치).
- 발송 감사(NOTIFY_SEND) 기록.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from services import audit_svc

log = logging.getLogger(__name__)

CHANNELS = ("SMS", "MAIL", "PUSH")


class NotifyError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# ── 단일 발송 ────────────────────────────────────────────────────────
def send(channel: str, *, target: str, message: Optional[str] = None,
         subject: Optional[str] = None, html: Optional[str] = None,
         title: Optional[str] = None, actor_id: Optional[str] = None) -> Dict[str, Any]:
    """단일 진입 발송.

    - SMS:  target=수신번호, message=본문(title 선택)
    - MAIL: target=수신메일, subject=제목, html 또는 message(text)
    - PUSH: (예약)
    반환: {channel, target, status, provider, external_id, error}
    """
    channel = (channel or "").upper()
    if channel not in CHANNELS:
        raise NotifyError(400, f"지원하지 않는 채널: {channel}")

    if channel == "SMS":
        result = _send_sms(target, message or "", title)
    elif channel == "MAIL":
        result = _send_mail(target, subject or "", html=html, text=message)
    else:  # PUSH
        raise NotifyError(501, "PUSH 채널은 아직 지원되지 않습니다.")

    audit_svc.record(
        "NOTIFY_SEND", "notify", entity_id=target, actor_id=actor_id,
        after={"channel": channel, "status": result.get("status"),
               "provider": result.get("provider")},
    )
    return {"channel": channel, "target": target, **result}


def _send_sms(receiver: str, message: str, title: Optional[str]) -> Dict[str, Any]:
    if not receiver or not message:
        raise NotifyError(400, "SMS는 수신번호와 본문이 필요합니다.")
    try:
        from capabilities.sms.core import send_sms as cap_send_sms
        # capability가 async → 동기 컨텍스트에서 실행
        res = _run_async(cap_send_sms(receiver, message, title))
        ok = bool(res.get("success"))
        return {"status": "sent" if ok else "failed", "provider": "messageme",
                "external_id": None, "error": None if ok else str(res)}
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "provider": "messageme", "external_id": None, "error": str(e)}


def _send_mail(to: str, subject: str, *, html: Optional[str] = None,
               text: Optional[str] = None) -> Dict[str, Any]:
    if not to:
        raise NotifyError(400, "메일 수신자가 필요합니다.")
    if not (html or text):
        raise NotifyError(400, "메일 본문(html 또는 text)이 필요합니다.")
    to_list = [e.strip() for e in to.split(",") if e.strip()]
    try:
        from services.gmail_channel import send as gmail_send
        res = gmail_send(to_list, subject, html=html, text=text)
        return {"status": "sent", "provider": "gmail",
                "external_id": res.get("id"), "error": None}
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "provider": "gmail", "external_id": None, "error": str(e)}


def _run_async(coro):
    """async 코루틴을 동기 컨텍스트에서 실행."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 이미 이벤트 루프 안이면 새 루프에서 실행
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(coro)
            finally:
                new_loop.close()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ── DryRun 미리보기 (대량발송 안전장치) ──────────────────────────────
def dry_run_preview(channel: str, targets: List[str], *,
                    sample_size: int = 5) -> Dict[str, Any]:
    """대량발송 전 미리보기: 대상 수·유효/무효 분리·샘플. 실제 발송 없음."""
    channel = (channel or "").upper()
    if channel not in CHANNELS:
        raise NotifyError(400, f"지원하지 않는 채널: {channel}")

    valid, invalid = [], []
    for t in targets:
        t = (t or "").strip()
        if not t:
            continue
        if channel == "MAIL":
            (valid if "@" in t else invalid).append(t)
        elif channel == "SMS":
            digits = "".join(c for c in t if c.isdigit())
            (valid if len(digits) >= 10 else invalid).append(t)
        else:
            valid.append(t)

    # 중복 제거
    seen = set()
    unique_valid = []
    for t in valid:
        if t not in seen:
            seen.add(t)
            unique_valid.append(t)

    return {
        "channel": channel,
        "total": len(targets),
        "valid": len(unique_valid),
        "invalid": len(invalid),
        "duplicates_removed": len(valid) - len(unique_valid),
        "sample": unique_valid[:sample_size],
        "invalid_sample": invalid[:sample_size],
    }
