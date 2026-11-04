"""tests/test_bizinfo_notification_atomic.py — 원자적 알림 계약 검증.

WO-TAI-BIZINFO-NOTIFICATION-ATOMIC-GATE-001 R1
Production DB·Slack 호출 = 0 (전부 모의 주입).

분석 결론 (CODE_ONLY — DB 적용 미승인):
  기존 slack_relay_event_log 테이블 재사용 가능 (신규 테이블 불필요).
  fn_save_bizinfo_with_notification PG 함수로 단일 트랜잭션 원자성 확보.
  릴레이 복구(run_relay_recovery_once)는 수동 엔드포인트만 존재 → GATE-RECOVERY 별도.
  기존 Relay 코드(accept_relay_event / process_relay_event) 변경 없음.

커버리지 — 기존:
  NAT-01  PENDING 등록 후 프로세스 중단 → Recovery Worker가 접수 (복구 경로 확인)
  NAT-02  동일 event_id 이중 접수 → 두 번째 접수 차단 (idempotent)
  NAT-03  Slack HTTP 500 → RETRY 상태 보존 (알림 유실 없음)

커버리지 — R1 추가 (원자적 저장 계약):
  A1  RPC 실패 → 공고 저장·알림 등록 모두 발생하지 않음 (all-or-nothing)
  A2  save_record_with_notification → 공고+알림 동시 등록 확인 (InMemory)
  A3  동일 source_key 재처리 → 중복 알림 event_id 차단 (idempotent)
  A4  기존 IN_SCOPE 공고 상태 변경 → 변경 알림 원자적 등록 + 기존 판정 보존
  A5  동일 notif_event_id 동시 처리 → RPC ON CONFLICT DO NOTHING → 중복 없음
  A6  승인되지 않은 역할 RPC 호출 → 예외 전파 (무시되지 않음)
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.slack_relay_svc as relay_mod
from services.bizinfo.normalizer import NormalizedSourceRecord
from services.bizinfo.repository import InMemoryBizinfoRepository
from services.bizinfo.status import ChangeRecord
from services.bizinfo.supabase_repository import SupabaseBizinfoRepository
from services.slack_relay_svc import (
    accept_relay_event,
    process_relay_event,
    run_relay_recovery_once,
)

# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

_RUN_AT   = datetime(2026, 11, 5, 4, 0, 0, tzinfo=timezone.utc)
_RUN_DATE = date(2026, 11, 5)


def _record(source_key: str = "prg001") -> NormalizedSourceRecord:
    return NormalizedSourceRecord(
        source_kind="PROGRAM",
        source_id="BIZINFO_PROGRAM",
        source_key=source_key,
        title="산업안전 지원사업",
        source_org="고용노동부",
        origin_url=None,
        bizinfo_url=f"https://www.bizinfo.go.kr/web/lay1/program/{source_key}",
        retrieved_at=_RUN_AT,
    )


def _change(source_key: str = "prg001") -> ChangeRecord:
    return ChangeRecord(
        source_key=source_key,
        source_kind="PROGRAM",
        verdict="NO_CHANGE",
        changed_fields=(),
        checked_at=_RUN_AT,
        source_updated_at=None,
    )


_NOTIF_KWARGS = dict(
    relay_channel="direct://bizinfo_daily_sync",
    target_channel="C0CCQKVQCQP",
    message_text="[TAI 기업마당] 신규 공고: 산업안전 지원사업",
    sender_id="bizinfo_daily_sync",
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


# ---------------------------------------------------------------------------
# A1: RPC 실패 → 공고 저장·알림 등록 모두 발생하지 않음 (all-or-nothing)
# ---------------------------------------------------------------------------

def test_A1_rpc_failure_is_all_or_nothing():
    """fn_save_bizinfo_with_notification RPC 실패 → 단독 테이블 쓰기 발생하지 않음.

    검증 목적: 단일 RPC 경로를 사용하므로 PG 함수가 실패하면
    bizinfo_source_records와 slack_relay_event_log 양쪽이 함께 롤백된다.
    별도 table().upsert() 경로가 없으므로 RPC 예외 후 테이블 호출이 없음을 확인.
    """
    sb = MagicMock()
    sb.rpc.return_value.execute.side_effect = RuntimeError("DB connection failed")

    repo = SupabaseBizinfoRepository(sb)
    with pytest.raises(RuntimeError, match="DB connection failed"):
        repo.save_record_with_notification(
            _record(), _change(),
            relevance_verdict="IN_SCOPE",
            notif_event_id="bizinfo_new_program_prg001_2026-11-05",
            **_NOTIF_KWARGS,
        )

    # RPC 사용 → 별도 table 접근 없음 (all-or-nothing at PG level)
    sb.table.assert_not_called()


# ---------------------------------------------------------------------------
# A2: save_record_with_notification → 공고 + 알림 동시 등록 확인
# ---------------------------------------------------------------------------

def test_A2_record_and_notification_registered_together():
    """save_record_with_notification 한 번 호출로 공고 저장 + 알림 등록이 함께 완료.

    검증 목적: 단일 호출로 record, verdict, notification_id가 모두 등록돼
    프로세스 중단 시에도 복구 가능한 PENDING 상태가 보장됨을 확인한다.
    """
    repo = InMemoryBizinfoRepository()
    event_id = "bizinfo_new_program_prg001_2026-11-05"

    registered = repo.save_record_with_notification(
        _record(), _change(),
        relevance_verdict="IN_SCOPE",
        notif_event_id=event_id,
        **_NOTIF_KWARGS,
    )

    assert registered is True, "알림 신규 등록 성공"
    assert repo.get_prior_record("PROGRAM", "prg001") is not None, "공고 저장됨"
    assert repo.get_relevance_verdict("PROGRAM", "prg001") == "IN_SCOPE", "판정 저장됨"
    assert event_id in repo._pending_notifications, "알림 event_id 등록됨"


# ---------------------------------------------------------------------------
# A3: 동일 source_key 재처리 → 중복 알림 event_id 차단
# ---------------------------------------------------------------------------

def test_A3_same_record_no_duplicate_notification():
    """동일 source_key + run_date → 동일 notif_event_id → 두 번째 접수 차단.

    검증 목적: 같은 날 동일 공고가 재처리될 때 알림이 중복 등록되지 않는다.
    """
    repo = InMemoryBizinfoRepository()
    event_id = "bizinfo_new_program_prg001_2026-11-05"

    first = repo.save_record_with_notification(
        _record(), _change(),
        relevance_verdict="IN_SCOPE",
        notif_event_id=event_id,
        **_NOTIF_KWARGS,
    )
    second = repo.save_record_with_notification(
        _record(), _change(),
        relevance_verdict="IN_SCOPE",
        notif_event_id=event_id,
        **_NOTIF_KWARGS,
    )

    assert first is True,  "첫 번째: 등록 성공"
    assert second is False, "두 번째: 중복 차단 (동일 event_id)"


# ---------------------------------------------------------------------------
# A4: 기존 IN_SCOPE 공고 상태 변경 → 변경 알림 등록 + 판정 보존
# ---------------------------------------------------------------------------

def test_A4_status_change_atomic_notification_preserves_verdict():
    """기존 IN_SCOPE 공고 상태 변경 → save_record_with_notification으로 원자적 등록.

    검증 목적: 기존 IN_SCOPE 판정은 보존되고, 변경 알림만 새로 등록된다.
    """
    repo = InMemoryBizinfoRepository()

    # 기존 IN_SCOPE 공고 사전 등록
    repo.seed_record(_record(), _change())
    repo.seed_relevance("PROGRAM", "prg001", "IN_SCOPE")

    status_change_event_id = "bizinfo_status_program_prg001_2026-11-05"

    # 상태 변경 발생 — relevance_verdict 미제공 (보존 테스트)
    registered = repo.save_record_with_notification(
        _record(), _change(),
        notif_event_id=status_change_event_id,
        relay_channel="direct://bizinfo_daily_sync",
        target_channel="C0CCQKVQCQP",
        message_text="[TAI 기업마당] 상태 변경: UPCOMING → OPEN",
        sender_id="bizinfo_daily_sync",
    )

    assert registered is True, "상태 변경 알림 등록 성공"
    assert repo.get_relevance_verdict("PROGRAM", "prg001") == "IN_SCOPE", \
        "기존 IN_SCOPE 판정이 보존되어야 한다"
    assert status_change_event_id in repo._pending_notifications


# ---------------------------------------------------------------------------
# A5: 동일 notif_event_id 동시 처리 → RPC ON CONFLICT DO NOTHING → 중복 없음
# ---------------------------------------------------------------------------

def test_A5_concurrent_rpc_no_duplicate_notification():
    """동시 RPC 호출: 두 번째 호출은 notif_registered=False → 중복 알림 없음.

    검증 목적: PG ON CONFLICT DO NOTHING이 동시 실행에서 중복 알림을 차단함을
    Supabase 모의 응답으로 확인한다.
    """
    call_count = [0]

    def _mock_execute():
        call_count[0] += 1
        if call_count[0] == 1:
            return MagicMock(data={"saved": True, "notif_registered": True})
        return MagicMock(data={"saved": True, "notif_registered": False})

    sb = MagicMock()
    sb.rpc.return_value.execute.side_effect = _mock_execute

    repo = SupabaseBizinfoRepository(sb)
    r1 = repo.save_record_with_notification(
        _record(), _change(),
        notif_event_id="bizinfo_new_program_prg001_2026-11-05",
        **_NOTIF_KWARGS,
    )
    r2 = repo.save_record_with_notification(
        _record(), _change(),
        notif_event_id="bizinfo_new_program_prg001_2026-11-05",
        **_NOTIF_KWARGS,
    )

    assert r1 is True,  "첫 번째: 알림 등록 성공"
    assert r2 is False, "두 번째: ON CONFLICT DO NOTHING → 중복 차단"
    assert call_count[0] == 2, "RPC 2회 호출"
    sb.table.assert_not_called()  # 별도 table 접근 없음


# ---------------------------------------------------------------------------
# A6: 승인되지 않은 역할 RPC 호출 → 예외 전파 (무시되지 않음)
# ---------------------------------------------------------------------------

def test_A6_unauthorized_role_raises():
    """anon/authenticated 역할이 fn_save_bizinfo_with_notification 호출 시 예외 전파.

    검증 목적: REVOKE EXECUTE ... FROM anon, authenticated SQL 설정에 의해
    권한 없는 역할의 호출이 차단되고 예외가 무시되지 않음을 확인한다.
    """
    sb = MagicMock()
    sb.rpc.return_value.execute.side_effect = Exception(
        "permission denied for function fn_save_bizinfo_with_notification"
    )

    repo = SupabaseBizinfoRepository(sb)
    with pytest.raises(Exception, match="permission denied"):
        repo.save_record_with_notification(
            _record(), _change(),
            notif_event_id="bizinfo_new_program_prg001_2026-11-05",
            **_NOTIF_KWARGS,
        )

    # 권한 오류는 무시되지 않고 전파됨
    sb.table.assert_not_called()
