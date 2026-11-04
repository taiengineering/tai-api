"""tests/test_bizinfo_notification_atomic.py — 원자적 알림 계약 가능성 검증.

WO-TAI-BIZINFO-NOTIFICATION-ATOMIC-GATE-001
Production DB·Slack 호출 = 0 (전부 모의 주입).

분석 결론 (CODE_ONLY — DB 적용 미승인):
  기존 slack_relay_event_log 테이블 재사용 가능 (신규 테이블 불필요).
  완전한 원자성(DB 저장 + 알림 등록 단일 트랜잭션)은 PG 함수 필요 → Owner DB Gate.
  기존 Relay Recovery Worker(run_relay_recovery_once)로 PENDING 복구 가능.
  기존 Relay 코드(accept_relay_event / process_relay_event) 변경 없음.

커버리지:
  NAT-01  PENDING 등록 후 프로세스 중단 → Recovery Worker가 접수 (복구 경로 확인)
  NAT-02  동일 event_id 이중 접수 → 두 번째 접수 차단 (idempotent)
  NAT-03  Slack HTTP 500 → RETRY 상태 보존 (알림 유실 없음)
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import services.slack_relay_svc as relay_mod
from services.slack_relay_svc import (
    accept_relay_event,
    process_relay_event,
    run_relay_recovery_once,
)

_EVENT_ID = "bizinfo_daily_sync_2026-11-05_ab12cd34"
_RELAY_KWARGS = dict(
    event_id=_EVENT_ID,
    relay_channel="direct://bizinfo_daily_sync",
    target_channel="C0CCQKVQCQP",
    message_text="[TAI 기업마당] 신규 안전 공고 1건",
    sender_id="bizinfo_daily_sync",
    source_message_ts=None,
)


# ---------------------------------------------------------------------------
# NAT-01: PENDING 등록 후 프로세스 중단 → Recovery Worker가 접수
# ---------------------------------------------------------------------------

def test_NAT01_pending_recovery():
    """accept_relay_event → PENDING 등록 → 프로세스 중단 시뮬레이션
    → run_relay_recovery_once 실행 → process_relay_event 호출 확인.

    검증 목적: 원자적 DB 함수로 PENDING이 등록된 경우,
    프로세스가 중단되어도 Recovery Worker가 알림을 복구할 수 있음을 확인한다.
    """
    # Phase 1: 알림 등록 성공 (accept_relay_event → PENDING 삽입)
    sb_accept = MagicMock()
    sb_accept.table.return_value.upsert.return_value.execute.return_value.data = [
        {"event_id": _EVENT_ID}
    ]
    with patch("services.slack_relay_svc._get_supabase", return_value=sb_accept):
        accepted = accept_relay_event(**_RELAY_KWARGS)
    assert accepted is True

    # Phase 2: 프로세스 중단 시뮬레이션 (process_relay_event 미호출)

    # Phase 3: Recovery Worker 실행 → PENDING 이벤트 발견 → process_relay_event 호출
    processed_ids: list[str] = []

    async def _mock_process(event_id: str) -> None:
        processed_ids.append(event_id)

    sb_recovery = MagicMock()
    # PENDING SELECT (run_relay_recovery_once 경로)
    sb_recovery.table.return_value.select.return_value.eq.return_value\
        .order.return_value.limit.return_value.execute.return_value.data = [
        {"event_id": _EVENT_ID}
    ]
    # RETRY SELECT → 없음
    sb_recovery.table.return_value.select.return_value.eq.return_value\
        .or_.return_value.order.return_value.limit.return_value.execute.return_value.data = []
    # stale recovery UPDATE → no-op
    sb_recovery.table.return_value.update.return_value.eq.return_value\
        .or_.return_value.execute.return_value.data = []
    sb_recovery.table.return_value.update.return_value.eq.return_value\
        .lt.return_value.execute.return_value.data = []

    with patch("services.slack_relay_svc._get_supabase", return_value=sb_recovery):
        with patch("services.slack_relay_svc.process_relay_event", side_effect=_mock_process):
            count = asyncio.run(run_relay_recovery_once())

    assert _EVENT_ID in processed_ids, \
        f"Recovery Worker가 PENDING 이벤트를 처리해야 한다 (실제 처리: {processed_ids})"
    assert count == 1


# ---------------------------------------------------------------------------
# NAT-02: 동일 event_id 이중 접수 → 두 번째 접수 차단
# ---------------------------------------------------------------------------

def test_NAT02_duplicate_event_id_blocked():
    """동일 event_id로 accept_relay_event 두 번 호출 — 두 번째는 False 반환.

    검증 목적: 같은 날 같은 내용의 재실행(ON CONFLICT DO NOTHING)에서
    중복 Slack 발송이 차단됨을 확인한다.
    """
    call_count = [0]

    def _get_sb():
        call_count[0] += 1
        sb = MagicMock()
        if call_count[0] == 1:
            # 첫 접수: 삽입 성공
            sb.table.return_value.upsert.return_value.execute.return_value.data = [
                {"event_id": _EVENT_ID}
            ]
        else:
            # 중복 접수: ON CONFLICT DO NOTHING → 빈 data
            sb.table.return_value.upsert.return_value.execute.return_value.data = []
        return sb

    with patch("services.slack_relay_svc._get_supabase", side_effect=_get_sb):
        first = accept_relay_event(**_RELAY_KWARGS)
        second = accept_relay_event(**_RELAY_KWARGS)

    assert first is True,  "첫 번째 접수: 성공이어야 한다"
    assert second is False, "두 번째 접수: 중복 차단이어야 한다"


# ---------------------------------------------------------------------------
# NAT-03: Slack HTTP 500 → RETRY 상태 보존
# ---------------------------------------------------------------------------

def test_NAT03_slack_http500_preserved():
    """Slack API HTTP 500 응답 → RETRY 전이 확인 — 알림 유실 없음.

    검증 목적: Slack 전송 실패 시 이벤트가 RETRY 상태로 보존되어
    Recovery Worker가 재시도할 수 있음을 확인한다.
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 500

    with patch("services.slack_relay_svc._claim", return_value=("row-nat03", "tok-nat03")):
        with patch("services.slack_relay_svc._load_row", return_value={
            "id": "row-nat03",
            "event_id": _EVENT_ID,
            "target_channel": "C0CCQKVQCQP",
            "message_text": "[TAI 기업마당] 신규 안전 공고 1건",
            "claim_token": "tok-nat03",
            "status": "CLAIMED",
            "retry_count": 0,
        }):
            with patch("services.slack_relay_svc._start_sending", return_value=True):
                with patch("services.slack_relay_svc._get_bot_token", return_value="xoxb-fake-token"):
                    with patch("httpx.AsyncClient") as mock_client_cls:
                        mock_ctx = AsyncMock()
                        mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
                        mock_ctx.__aexit__ = AsyncMock(return_value=False)
                        mock_ctx.post = AsyncMock(return_value=mock_resp)
                        mock_client_cls.return_value = mock_ctx
                        with patch("services.slack_relay_svc._finish") as mock_finish:
                            asyncio.run(process_relay_event(_EVENT_ID))

    mock_finish.assert_called_once()
    finished_status = mock_finish.call_args[0][2]
    assert finished_status == "RETRY", \
        f"HTTP 500 → RETRY 예상, 실제: {finished_status}"
