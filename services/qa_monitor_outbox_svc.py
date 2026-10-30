"""QA Monitor Notification Outbox — WO-016 WP-C.

qa_monitor_notification_outbox 테이블을 통해 WP-D 경보 Slack 발송을 원자적으로 관리.

상태 머신: PENDING → SENDING → SENT
실패 경로: SENDING → UNKNOWN (timeout/network) / FAILED (permanent Slack error)

UNIQUE(dedupe_key):
  dedupe_key = "<slot_utc_iso>|<status_code>"
  동일 Slot+상태 코드에 대한 중복 경보 억제.

claim_token CAS 펜싱으로 동시 Worker 충돌 방지.

안전 원칙:
  - 이 모듈은 DB 마이그레이션이 적용된 후에만 작동한다.
  - 마이그레이션: migrations/WO016_qa_monitor_notification_outbox.sql (Draft — 미적용)
  - 실제 Slack 발송은 services.slack_dispatcher.send_slack() 를 통해서만 수행.
  - 테이블 없이 accept/process 호출 시 Supabase 오류가 그대로 전파된다.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from services.slack_dispatcher import send_slack

log = logging.getLogger("qa_monitor_outbox")

_TABLE = "qa_monitor_notification_outbox"
_LEASE_SECONDS = 120
_STALE_SENDING_SECONDS = 600


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _now_dt() -> datetime:
    return datetime.now(tz=timezone.utc)


def _future_sec(seconds: int) -> str:
    return (_now_dt() + timedelta(seconds=seconds)).isoformat()


def _past_sec(seconds: int) -> str:
    return (_now_dt() - timedelta(seconds=seconds)).isoformat()


# ── 공개 인터페이스 ───────────────────────────────────────────────────────────

def accept_monitor_notification(
    supabase: Any,
    *,
    dedupe_key: str,
    slot_utc: str,
    status_code: str,
    slack_payload: Dict[str, Any],
) -> tuple[bool, Optional[str]]:
    """경보를 PENDING 상태로 DB에 원자적 삽입.

    UNIQUE(dedupe_key) 충돌 시 ON CONFLICT DO NOTHING → (False, None).
    신규 삽입 성공 → (True, row_id).
    """
    now = _now()
    row = {
        "dedupe_key":    dedupe_key,
        "slot_utc":      slot_utc,
        "status_code":   status_code,
        "slack_payload": slack_payload,
        "status":        "PENDING",
        "created_at":    now,
        "updated_at":    now,
    }
    result = supabase.table(_TABLE).upsert(
        row,
        on_conflict="dedupe_key",
        ignore_duplicates=True,
    ).execute()
    if not result.data:
        log.info("[qa_monitor_outbox] 중복 dedupe_key=%s — 스킵", dedupe_key)
        return False, None
    row_id: str = result.data[0]["id"]
    log.info("[qa_monitor_outbox] PENDING 삽입 row_id=%s dedupe_key=%s", row_id, dedupe_key)
    return True, row_id


def _claim(supabase: Any, row_id: str) -> Optional[str]:
    """PENDING 행을 CLAIMED로 전이 (CAS). 성공 시 claim_token 반환, 실패 시 None."""
    token = str(uuid.uuid4())
    claim_expires = _future_sec(_LEASE_SECONDS)
    now = _now()
    result = supabase.table(_TABLE).update({
        "status":        "CLAIMED",
        "claim_token":   token,
        "claimed_at":    now,
        "claim_expires": claim_expires,
        "updated_at":    now,
    }).eq("id", row_id).eq("status", "PENDING").execute()
    if not result.data:
        return None
    return token


def _start_sending(supabase: Any, row_id: str, claim_token: str) -> bool:
    """CLAIMED → SENDING (claim_token + 상태 CAS)."""
    result = supabase.table(_TABLE).update({
        "status":             "SENDING",
        "dispatch_started_at": _now(),
        "updated_at":         _now(),
    }).eq("id", row_id).eq("claim_token", claim_token).eq("status", "CLAIMED").execute()
    return bool(result.data)


def _finish(
    supabase: Any,
    row_id: str,
    claim_token: str,
    new_status: str,
    **extra: Any,
) -> bool:
    """SENDING → (SENT | UNKNOWN | FAILED) (claim_token + 상태 CAS)."""
    result = supabase.table(_TABLE).update({
        "status": new_status,
        "updated_at": _now(),
        **extra,
    }).eq("id", row_id).eq("claim_token", claim_token).eq("status", "SENDING").execute()
    return bool(result.data)


async def send_monitor_notification(
    supabase: Any,
    row_id: str,
    slack_payload: Dict[str, Any],
) -> str:
    """단일 PENDING 행을 Claim → Send → Finish 처리.

    반환:
      "SENT"           — Slack 발송 성공 + DB 완료 기록 성공
      "SENT_DB_FAILED" — Slack 발송 성공, DB 완료 기록 실패 (감사 증거 불완전)
      "UNKNOWN"        — Slack 발송 실패 또는 결과 불명 (재발송 금지)
      "SKIPPED"        — Claim 실패 (다른 Worker가 처리 중)
    """
    claim_token = _claim(supabase, row_id)
    if claim_token is None:
        log.debug("[qa_monitor_outbox] Claim 실패 row_id=%s (경쟁 또는 비대상)", row_id)
        return "SKIPPED"

    if not _start_sending(supabase, row_id, claim_token):
        log.warning("[qa_monitor_outbox] SENDING 전이 실패 row_id=%s", row_id)
        return "SKIPPED"

    try:
        sent = await send_slack(
            event_type=slack_payload.get("event_type", "QA_WORKFLOW_MONITOR_ALERT"),
            severity=slack_payload.get("severity", "WARNING"),
            title=slack_payload.get("title", "QA Workflow Monitor Alert"),
            detail=slack_payload.get("detail", ""),
            blocks=slack_payload.get("blocks"),
        )
    except Exception as exc:
        log.warning("[qa_monitor_outbox] send_slack 예외 row_id=%s: %s", row_id, exc)
        _finish(supabase, row_id, claim_token, "UNKNOWN",
                error_detail=f"exception: {str(exc)[:200]}")
        return "UNKNOWN"

    if not sent:
        _finish(supabase, row_id, claim_token, "UNKNOWN",
                error_detail="send_slack returned False")
        log.warning("[qa_monitor_outbox] UNKNOWN row_id=%s (send_slack=False)", row_id)
        return "UNKNOWN"

    # Slack 발송 성공 — DB 완료 기록 (R1-04/R2-02: _finish 결과·예외 검증)
    # _finish() 예외 시 Slack은 이미 발송됨 → 재발송 금지, SENT_DB_FAILED 반환
    try:
        finished = _finish(supabase, row_id, claim_token, "SENT", sent_at=_now())
    except Exception:
        log.warning(
            "[qa_monitor_outbox] SENT_DB_FAILED row_id=%s (_finish 예외 — DB 장애)",
            row_id,
        )
        return "SENT_DB_FAILED"

    if finished:
        log.info("[qa_monitor_outbox] SENT row_id=%s", row_id)
        return "SENT"

    # Slack 발송 성공 + DB 기록 빈 결과 — 감사 증거 불완전, 재발송 금지
    log.warning(
        "[qa_monitor_outbox] SENT_DB_FAILED row_id=%s "
        "(Slack sent but DB _finish returned empty — possible CAS race)",
        row_id,
    )
    return "SENT_DB_FAILED"


def recover_stale_sending(supabase: Any) -> int:
    """오래된 SENDING 행을 UNKNOWN으로 복구 (Worker 재시작 후 stale 정리).

    CLAIMED → PENDING (lease 만료 기준).
    SENDING → UNKNOWN (stale 기준).
    """
    now = _now()
    stale_ts = _past_sec(_STALE_SENDING_SECONDS)

    r1 = supabase.table(_TABLE).update({
        "status":      "PENDING",
        "claim_token": None,
        "updated_at":  now,
        "error_detail": "stale_claimed_recovery",
    }).eq("status", "CLAIMED").or_(
        f"claim_expires.is.null,claim_expires.lt.{now}"
    ).execute()

    r2 = supabase.table(_TABLE).update({
        "status":      "UNKNOWN",
        "claim_token": None,
        "updated_at":  now,
        "error_detail": "stale_sending_recovery",
    }).eq("status", "SENDING").lt("updated_at", stale_ts).execute()

    recovered = len(r1.data or []) + len(r2.data or [])
    if recovered:
        log.info("[qa_monitor_outbox] stale 복구 %d건", recovered)
    return recovered
