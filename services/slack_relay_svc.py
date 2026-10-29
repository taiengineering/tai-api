"""Slack Events Relay Worker — WO-TAI-SLACK-BOT-UNIFIED-001-R3.

상태 머신: PENDING → CLAIMED → SENDING → SENT
실패 경로: → RETRY / UNKNOWN / FAILED_PERMANENT

claim_token CAS 펜싱으로 동시 Worker 충돌·stale 갱신 방지.
BackgroundTask는 즉시 전송 최적화 경로. 영속 복구는 run_relay_recovery_once().
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger("slack_relay_svc")

_MAX_RETRY = 3
_RETRY_DELAYS_SECONDS = [60, 300, 900]   # 1분, 5분, 15분 (초 단위)
_STALE_CLAIMED_SECONDS = 300             # 5분
_STALE_SENDING_SECONDS = 600             # 10분
_RECOVERY_BATCH = 10
_LEASE_SECONDS = 120                     # claim_expires = now + 2분


def _now_dt() -> datetime:
    return datetime.now(tz=timezone.utc)


def _now() -> str:
    return _now_dt().isoformat()


def _future_sec(seconds: int) -> str:
    return (_now_dt() + timedelta(seconds=seconds)).isoformat()


def _past_sec(seconds: int) -> str:
    return (_now_dt() - timedelta(seconds=seconds)).isoformat()


def _get_supabase():
    from db.supabase_client import get_supabase
    return get_supabase()


def _get_bot_token() -> str:
    """COR-06: SLACK_BOT_TOKEN1만 사용. 구형 SLACK_BOT_TOKEN 폴백 없음."""
    return os.environ.get("SLACK_BOT_TOKEN1", "").strip()


# ─────────────────────────────────────────────────────────────────────────────
# Public: 이벤트 접수
# ─────────────────────────────────────────────────────────────────────────────

def accept_relay_event(
    *,
    event_id: str,
    relay_channel: str,
    target_channel: str,
    message_text: str,
    sender_id: str,
    source_message_ts: Optional[str],
) -> bool:
    """이벤트를 DB에 PENDING으로 원자적 삽입.

    중복(event_id 충돌) 시 ON CONFLICT DO NOTHING → False.
    신규 삽입 시 True.
    """
    sb = _get_supabase()
    row = {
        "event_id": event_id,
        "relay_channel": relay_channel,
        "target_channel": target_channel,
        "message_text": message_text[:4000],
        "sender_id": sender_id,
        "source_message_ts": source_message_ts,
        "status": "PENDING",
    }
    result = sb.table("slack_relay_event_log").upsert(
        row, on_conflict="event_id", ignore_duplicates=True
    ).execute()
    inserted = bool(result.data)
    if not inserted:
        logger.info("[RELAY] 중복 event_id=%s — 스킵", event_id)
    return inserted


# ─────────────────────────────────────────────────────────────────────────────
# Internal: 상태 전이 (claim_token CAS)
# ─────────────────────────────────────────────────────────────────────────────

def _claim(event_id: str) -> Optional[tuple[str, str]]:
    """PENDING 또는 재시도 시각이 도래한 RETRY → CLAIMED.
    (row_id, claim_token) 반환; 경쟁 실패 또는 비대상 시 None.

    COR-02: RETRY도 Claim 허용.
    COR-03: PENDING은 next_attempt_at 무관. RETRY는 도래 시각만.
    COR-04: claim_expires 설정.
    """
    sb = _get_supabase()
    now = _now()
    row_res = sb.table("slack_relay_event_log").select("id, status, next_attempt_at").eq(
        "event_id", event_id
    ).in_("status", ["PENDING", "RETRY"]).limit(1).execute()

    if not row_res.data:
        return None

    row = row_res.data[0]
    row_id = row["id"]
    row_status = row["status"]
    next_attempt = row.get("next_attempt_at")

    # RETRY: next_attempt_at이 도래하지 않은 경우 스킵
    if row_status == "RETRY" and next_attempt is not None and next_attempt > now:
        return None

    token = str(uuid.uuid4())
    claim_expires = _future_sec(_LEASE_SECONDS)
    result = sb.table("slack_relay_event_log").update({
        "status": "CLAIMED",
        "claim_token": token,
        "claimed_at": now,
        "claim_expires": claim_expires,
        "updated_at": now,
    }).eq("id", row_id).in_("status", ["PENDING", "RETRY"]).execute()

    if not result.data:
        return None
    return row_id, token


def _start_sending(row_id: str, claim_token: str) -> bool:
    """CLAIMED → SENDING (claim_token CAS 펜싱)."""
    sb = _get_supabase()
    result = sb.table("slack_relay_event_log").update({
        "status": "SENDING",
        "dispatch_started_at": _now(),
        "updated_at": _now(),
    }).eq("id", row_id).eq("claim_token", claim_token).execute()
    return bool(result.data)


def _finish(row_id: str, claim_token: str, new_status: str, **extra) -> bool:
    """SENDING → (SENT|RETRY|UNKNOWN|FAILED_PERMANENT) (claim_token CAS 펜싱)."""
    sb = _get_supabase()
    update_data = {"status": new_status, "updated_at": _now(), **extra}
    result = sb.table("slack_relay_event_log").update(update_data).eq(
        "id", row_id
    ).eq("claim_token", claim_token).execute()
    return bool(result.data)


def _load_row(event_id: str) -> Optional[dict]:
    sb = _get_supabase()
    result = sb.table("slack_relay_event_log").select(
        "id, event_id, target_channel, message_text, claim_token, status, retry_count"
    ).eq("event_id", event_id).limit(1).execute()
    return result.data[0] if result.data else None


# ─────────────────────────────────────────────────────────────────────────────
# Public: 이벤트 처리 (BackgroundTask 경로)
# ─────────────────────────────────────────────────────────────────────────────

async def process_relay_event(event_id: str) -> None:
    """단일 이벤트 처리. BackgroundTask 및 Recovery Worker 공용."""
    claimed = _claim(event_id)
    if claimed is None:
        logger.debug("[RELAY] claim 실패(경쟁 또는 비대상) event_id=%s", event_id)
        return
    row_id, claim_token = claimed

    row = _load_row(event_id)
    if not row:
        logger.error("[RELAY] DB 행 조회 실패 event_id=%s", event_id)
        return

    target_channel = row["target_channel"]
    message_text = row["message_text"]
    retry_count = row.get("retry_count", 0)

    if not _start_sending(row_id, claim_token):
        logger.warning("[RELAY] SENDING 전이 실패(stale claim_token?) row_id=%s", row_id)
        return

    token = _get_bot_token()
    if not token:
        logger.error("[RELAY] SLACK_BOT_TOKEN1 미설정 — RETRY row_id=%s", row_id)
        _finish(row_id, claim_token, "RETRY",
                retry_count=retry_count + 1,
                next_attempt_at=_future_sec(_retry_delay_sec(retry_count)),
                error_detail="SLACK_BOT_TOKEN1 not configured")
        return

    await _send_to_slack(row_id, claim_token, target_channel, message_text, retry_count, token)


async def _send_to_slack(
    row_id: str, claim_token: str,
    target_channel: str, message_text: str,
    retry_count: int, token: str,
) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://slack.com/api/chat.postMessage",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
                json={"channel": target_channel, "text": message_text},
            )
    except httpx.TimeoutException as e:
        logger.warning("[RELAY] Slack API timeout row_id=%s: %s", row_id, e)
        _finish(row_id, claim_token, "UNKNOWN", error_detail=f"timeout: {e}"[:500])
        return
    except Exception as e:
        logger.exception("[RELAY] Slack API 네트워크 오류 row_id=%s", row_id)
        _finish(row_id, claim_token, "UNKNOWN", error_detail=f"network: {e}"[:500])
        return

    if resp.status_code == 200:
        try:
            body = resp.json()
        except Exception:
            _finish(row_id, claim_token, "UNKNOWN", error_detail="response parse error")
            return

        if body.get("ok"):
            slack_ts = (body.get("message") or {}).get("ts")
            _finish(row_id, claim_token, "SENT", sent_at=_now(), slack_ts=slack_ts, claim_token=None)
            logger.info("[RELAY] SENT row_id=%s ts=%s", row_id, slack_ts)
            return

        error_code = body.get("error", "")
        if error_code in ("channel_not_found", "not_in_channel", "is_archived",
                          "invalid_auth", "account_inactive", "token_revoked"):
            _finish(row_id, claim_token, "FAILED_PERMANENT",
                    error_detail=f"slack_error:{error_code}")
            logger.error("[RELAY] FAILED_PERMANENT row_id=%s error=%s", row_id, error_code)
            return

        if retry_count >= _MAX_RETRY:
            _finish(row_id, claim_token, "FAILED_PERMANENT",
                    error_detail=f"max_retry:{error_code}")
        else:
            _finish(row_id, claim_token, "RETRY",
                    retry_count=retry_count + 1,
                    next_attempt_at=_future_sec(_retry_delay_sec(retry_count)),
                    error_detail=f"slack_error:{error_code}")
        return

    if resp.status_code == 429:
        # COR-07: Retry-After는 초 단위로 정확히 반영 (분 내림 없음)
        retry_after_sec = int(resp.headers.get("Retry-After", "60"))
        retry_after_sec = max(retry_after_sec, 10)
        if retry_count >= _MAX_RETRY:
            _finish(row_id, claim_token, "FAILED_PERMANENT",
                    error_detail="rate_limit_max_retry")
        else:
            _finish(row_id, claim_token, "RETRY",
                    retry_count=retry_count + 1,
                    next_attempt_at=_future_sec(retry_after_sec),
                    error_detail=f"rate_limited retry_after={retry_after_sec}s")
        return

    if resp.status_code >= 500:
        if retry_count >= _MAX_RETRY:
            _finish(row_id, claim_token, "FAILED_PERMANENT",
                    error_detail=f"http_{resp.status_code}_max")
        else:
            _finish(row_id, claim_token, "RETRY",
                    retry_count=retry_count + 1,
                    next_attempt_at=_future_sec(_retry_delay_sec(retry_count)),
                    error_detail=f"http_{resp.status_code}")
        return

    _finish(row_id, claim_token, "FAILED_PERMANENT",
            error_detail=f"http_{resp.status_code}")


def _retry_delay_sec(retry_count: int) -> int:
    idx = min(retry_count, len(_RETRY_DELAYS_SECONDS) - 1)
    return _RETRY_DELAYS_SECONDS[idx]


# ─────────────────────────────────────────────────────────────────────────────
# Public: 복구 Worker
# ─────────────────────────────────────────────────────────────────────────────

def recover_stale_claimed() -> int:
    """오래된 CLAIMED/SENDING 행 복구. 재시작 후 stale Worker 정리.

    CLAIMED → RETRY, SENDING → UNKNOWN.
    """
    sb = _get_supabase()
    stale_claimed_ts = _past_sec(_STALE_CLAIMED_SECONDS)
    stale_sending_ts = _past_sec(_STALE_SENDING_SECONDS)

    r1 = sb.table("slack_relay_event_log").update({
        "status": "RETRY",
        "claim_token": None,
        "next_attempt_at": _future_sec(60),
        "error_detail": "stale_claimed_recovery",
        "updated_at": _now(),
    }).eq("status", "CLAIMED").lt("updated_at", stale_claimed_ts).execute()

    r2 = sb.table("slack_relay_event_log").update({
        "status": "UNKNOWN",
        "claim_token": None,
        "error_detail": "stale_sending_recovery",
        "updated_at": _now(),
    }).eq("status", "SENDING").lt("updated_at", stale_sending_ts).execute()

    recovered = len(r1.data or []) + len(r2.data or [])
    if recovered:
        logger.info("[RELAY] stale 복구 %d건", recovered)
    return recovered


async def run_relay_recovery_once() -> int:
    """PENDING/RETRY 행 일괄 재처리.

    COR-03: PENDING(next_attempt_at NULL 포함)과 RETRY(도래 시각)를 별도 조회.
    운영 스케줄러 등록은 이번 범위 제외. POST /internal/slack-relay/recover 또는 수동 호출.
    """
    recover_stale_claimed()

    sb = _get_supabase()
    now = _now()

    # COR-03: PENDING은 next_attempt_at 무관 (NULL 포함 전체 대상)
    pending_res = sb.table("slack_relay_event_log").select(
        "event_id"
    ).eq("status", "PENDING").order("created_at").limit(_RECOVERY_BATCH).execute()

    # COR-03: RETRY는 next_attempt_at이 NULL이거나 도래한 경우만
    retry_res = sb.table("slack_relay_event_log").select(
        "event_id"
    ).eq("status", "RETRY").or_(
        f"next_attempt_at.is.null,next_attempt_at.lte.{now}"
    ).order("created_at").limit(_RECOVERY_BATCH).execute()

    pending_ids = [r["event_id"] for r in (pending_res.data or [])]
    retry_ids = [
        r["event_id"] for r in (retry_res.data or [])
        if r["event_id"] not in pending_ids
    ]
    all_ids = (pending_ids + retry_ids)[:_RECOVERY_BATCH]

    processed = 0
    for event_id in all_ids:
        try:
            await process_relay_event(event_id)
            processed += 1
        except Exception:
            logger.exception("[RELAY] recovery 처리 실패 event_id=%s", event_id)

    if processed:
        logger.info("[RELAY] recovery 처리 %d건", processed)
    return processed
