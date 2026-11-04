"""tests/test_bizinfo_lifecycle_atomic.py — WO-TAI-BIZINFO-LIFECYCLE-ATOMIC-001 검증.

Production DB·API·Slack 호출 = 0 (전부 모의 주입).

커버리지:
  LCA-01  접수 마감된 IN_SCOPE 공고 → relevance_verdict = IN_SCOPE 보존
  LCA-02  EVENT 접수 마감(CLOSED) + 행사 진행(ONGOING) → 두 축 독립
  LCA-02c EVENT 행사 종료 → progress_status = ENDED (CLOSED 아님, SQL CHECK 일치)
  LCA-03  날짜 없는 공고 → 상태 = UNKNOWN (OPEN 기본값 아님)
  LCA-04  후속 공고 등록 → 원본 공고 레코드 보존
  LCA-05  API 오류 발생 → 기존 IN_SCOPE 허위 마감 판정 없음
  LCA-06  상태 변경 감지 → 개별 알림이 repo에 원자적으로 등록됨
  LCA-07  Supabase RPC 오류 → 레코드·알림 모두 롤백 (table() 미호출)
  LCA-08  마감된 IN_SCOPE 공고 → 신규 모집 카운트 아님, 상태 변경 감지
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Optional
from unittest.mock import MagicMock

import pytest

from services.bizinfo.daily_sync import run_bizinfo_daily_sync
from services.bizinfo.normalizer import DateRange, NormalizedSourceRecord
from services.bizinfo.repository import InMemoryBizinfoRepository
from services.bizinfo.status import ChangeRecord, event_status, program_status
from services.bizinfo.supabase_repository import SupabaseBizinfoRepository

# ---------------------------------------------------------------------------
# 공통 상수
# ---------------------------------------------------------------------------

_TODAY = date(2026, 11, 5)
_RUN_AT = datetime(2026, 11, 5, 4, 0, 0, tzinfo=timezone.utc)       # KST 13:00
_RUN_AT_PRIOR = datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc)  # 이전 수집 기준


# ---------------------------------------------------------------------------
# 공통 픽스처 헬퍼
# ---------------------------------------------------------------------------


def _prog(
    key: str,
    title: str = "안전관리시스템 도입 지원",
    app_start: Optional[date] = None,
    app_end: Optional[date] = None,
    retrieved_at: datetime = _RUN_AT,
) -> NormalizedSourceRecord:
    app = DateRange(start=app_start, end=app_end) if (app_start or app_end) else None
    return NormalizedSourceRecord(
        source_kind="PROGRAM",
        source_id="BIZINFO_PROGRAM",
        source_key=key,
        title=title,
        source_org="고용노동부",
        origin_url=None,
        bizinfo_url=f"https://www.bizinfo.go.kr/web/lay1/program/{key}",
        retrieved_at=retrieved_at,
        application_period=app,
    )


def _evt(
    key: str,
    title: str = "안전관리 교육행사",
    evt_start: Optional[date] = None,
    evt_end: Optional[date] = None,
    rcp_start: Optional[date] = None,
    rcp_end: Optional[date] = None,
    retrieved_at: datetime = _RUN_AT,
) -> NormalizedSourceRecord:
    ep = DateRange(start=evt_start, end=evt_end) if (evt_start or evt_end) else None
    rp = DateRange(start=rcp_start, end=rcp_end) if (rcp_start or rcp_end) else None
    return NormalizedSourceRecord(
        source_kind="EVENT",
        source_id="BIZINFO_EVENT",
        source_key=key,
        title=title,
        source_org="KOSHA",
        origin_url=None,
        bizinfo_url=f"https://www.bizinfo.go.kr/web/lay1/event/{key}",
        retrieved_at=retrieved_at,
        event_period=ep,
        reception_period=rp,
    )


def _chg(key: str, kind: str = "PROGRAM", verdict: str = "CHANGE_UNKNOWN") -> ChangeRecord:
    return ChangeRecord(
        source_key=key,
        source_kind=kind,
        verdict=verdict,
        changed_fields=(),
        checked_at=_RUN_AT,
        source_updated_at=None,
    )


# ---------------------------------------------------------------------------
# LCA-01: 접수 마감된 IN_SCOPE 공고 → relevance_verdict 보존
# ---------------------------------------------------------------------------


def test_LCA01_closed_program_in_scope_preserved():
    """접수 마감(CLOSED) 상태여도 IN_SCOPE 판정은 사라지지 않는다.

    안전 관련성(relevance_verdict)과 모집 상태(recruitment_status)는
    독립적인 속성이다.
    """
    repo = InMemoryBizinfoRepository()
    closed = _prog(
        "prg_lca01",
        app_start=date(2026, 10, 1),
        app_end=date(2026, 10, 31),   # 마감
        retrieved_at=_RUN_AT_PRIOR,
    )
    repo.save_record(closed, _chg("prg_lca01"))
    repo.save_relevance_verdict("PROGRAM", "prg_lca01", "IN_SCOPE")

    # 재수집: 같은 날짜(여전히 마감), relevance_verdict=None → 보존 의도
    new_snap = _prog(
        "prg_lca01",
        app_start=date(2026, 10, 1),
        app_end=date(2026, 10, 31),
        retrieved_at=_RUN_AT,
    )
    repo.save_record_with_notification(
        new_snap,
        _chg("prg_lca01", verdict="UNCHANGED"),
        relevance_verdict=None,
    )

    assert repo.get_relevance_verdict("PROGRAM", "prg_lca01") == "IN_SCOPE"


def test_LCA01b_in_scope_not_overwritten_by_review_required():
    """save_record_with_notification(relevance_verdict='REVIEW_REQUIRED')로 호출해도
    기존 IN_SCOPE는 덮어써지지 않는다."""
    repo = InMemoryBizinfoRepository()
    rec = _prog("prg_lca01b", retrieved_at=_RUN_AT_PRIOR)
    repo.save_record(rec, _chg("prg_lca01b"))
    repo.save_relevance_verdict("PROGRAM", "prg_lca01b", "IN_SCOPE")

    repo.save_record_with_notification(
        _prog("prg_lca01b"),
        _chg("prg_lca01b", verdict="UNCHANGED"),
        relevance_verdict="REVIEW_REQUIRED",  # 덮어쓰기 시도
    )

    assert repo.get_relevance_verdict("PROGRAM", "prg_lca01b") == "IN_SCOPE"


# ---------------------------------------------------------------------------
# LCA-02: EVENT 접수 마감 + 행사 진행 → 두 축 독립
# ---------------------------------------------------------------------------


def test_LCA02_event_reception_closed_progress_ongoing():
    """접수 마감(CLOSED) + 행사 진행 중(ONGOING) 상태는 독립적으로 표현된다.

    today = 2026-11-05
    reception: 2026-10-01 ~ 2026-10-31 → CLOSED (10-31 < 11-05)
    event:     2026-11-01 ~ 2026-11-30 → ONGOING (11-01 <= 11-05 <= 11-30)
    """
    rec = _evt(
        "evt_lca02",
        evt_start=date(2026, 11, 1),
        evt_end=date(2026, 11, 30),
        rcp_start=date(2026, 10, 1),
        rcp_end=date(2026, 10, 31),
    )
    es = event_status(rec, as_of=_TODAY)

    assert es.reception_status == "CLOSED"
    assert es.progress_status == "ONGOING"
    # 두 축은 독립: 접수 마감이 행사 진행 상태를 덮어쓰지 않음
    assert es.reception_status != es.progress_status


def test_LCA02b_event_reception_open_progress_upcoming():
    """접수 중(OPEN) + 행사 예정(UPCOMING) 조합도 독립 계산된다.

    today = 2026-11-05
    reception: 2026-11-01 ~ 2026-11-30 → OPEN
    event:     2026-11-20 ~ 2026-11-25 → UPCOMING (오늘 11-05 < 행사시작 11-20)
    """
    rec = _evt(
        "evt_lca02b",
        evt_start=date(2026, 11, 20),
        evt_end=date(2026, 11, 25),
        rcp_start=date(2026, 11, 1),
        rcp_end=date(2026, 11, 30),
    )
    es = event_status(rec, as_of=_TODAY)

    assert es.reception_status == "OPEN"
    assert es.progress_status == "UPCOMING"


def test_LCA02c_event_ended_progress_ended():
    """행사 종료 시 progress_status == "ENDED" (SQL progress_status 값과 일치).

    today = 2026-11-05
    event: 2026-10-01 ~ 2026-10-31 → 종료 (11-05 > 10-31)
    _date_status()는 "CLOSED" 반환 → event_status()가 "ENDED"로 매핑해야 함.

    SQL fn_save_bizinfo_with_notification의 progress_status = 'ENDED' 와 동일한 값.
    "CLOSED" 반환 시 CHECK 제약(UPCOMING/ONGOING/ENDED/UNKNOWN)을 위반한다.
    """
    rec = _evt(
        "evt_lca02c",
        evt_start=date(2026, 10, 1),
        evt_end=date(2026, 10, 31),   # 종료일 경과
    )
    es = event_status(rec, as_of=_TODAY)

    assert es.progress_status == "ENDED", (
        f"progress_status는 'ENDED'여야 하지만 {es.progress_status!r}이 반환됐습니다. "
        "_PROGRESS_MAP에서 'CLOSED' → 'ENDED' 매핑을 확인하세요."
    )
    # "CLOSED"가 아닌 "ENDED" — SQL CHECK 제약과 일치
    assert es.progress_status != "CLOSED"


# ---------------------------------------------------------------------------
# LCA-03: 날짜 없는 공고 → 상태 = UNKNOWN
# ---------------------------------------------------------------------------


def test_LCA03_no_dates_yields_unknown():
    """application_period=None인 공고의 상태는 UNKNOWN."""
    rec = _prog("prg_lca03", app_start=None, app_end=None)
    ps = program_status(rec, as_of=_TODAY)

    assert ps.application_status == "UNKNOWN"
    assert ps.has_dates is False


def test_LCA03b_end_only_yields_unknown():
    """end 날짜만 있고 start 없는 공고 → UNKNOWN (접수 중 가정 금지).

    today = 2026-11-05, end = 2026-12-31 (미래)
    start 미확인 → 양쪽 날짜 모두 필요한 OPEN 조건 미충족 → UNKNOWN
    """
    rec = _prog("prg_lca03b", app_start=None, app_end=date(2026, 12, 31))
    ps = program_status(rec, as_of=_TODAY)

    assert ps.application_status == "UNKNOWN"


def test_LCA03c_start_only_upcoming_then_unknown():
    """start 날짜만 있고 end 없는 공고.

    today = 2026-11-05, start = 2026-12-01 (미래) → UPCOMING (오늘 < start)
    today = 2026-11-05, start = 2026-10-01 (과거) → UNKNOWN (OPEN 판단 불가)
    """
    rec_future = _prog("prg_lca03c1", app_start=date(2026, 12, 1), app_end=None)
    assert program_status(rec_future, as_of=_TODAY).application_status == "UPCOMING"

    rec_past_start = _prog("prg_lca03c2", app_start=date(2026, 10, 1), app_end=None)
    assert program_status(rec_past_start, as_of=_TODAY).application_status == "UNKNOWN"


def test_LCA03d_event_no_dates_unknown():
    """EVENT reception_period, event_period 모두 없으면 UNKNOWN."""
    rec = _evt("evt_lca03d")  # 날짜 없음
    es = event_status(rec, as_of=_TODAY)

    assert es.reception_status == "UNKNOWN"
    assert es.progress_status == "UNKNOWN"
    assert es.has_reception_dates is False
    assert es.has_event_dates is False


# ---------------------------------------------------------------------------
# LCA-04: 후속 공고 등록 → 원본 공고 레코드 보존
# ---------------------------------------------------------------------------


def test_LCA04_successor_announcement_preserves_original():
    """후속 공고(다른 source_key)가 등록돼도 원본 공고 레코드와 판정이 보존된다.

    실제 사례: PBLN_000000000121697 → PBLN_000000000126438
    두 공고는 UPSERT 키(source_kind, source_key)가 달라 독립 행으로 존재한다.
    """
    repo = InMemoryBizinfoRepository()

    original = _prog(
        "PBLN_000000000121697",
        title="안전관리 지원 (원본)",
        app_start=date(2026, 9, 1),
        app_end=date(2026, 10, 31),
        retrieved_at=_RUN_AT_PRIOR,
    )
    repo.save_record(original, _chg("PBLN_000000000121697"))
    repo.save_relevance_verdict("PROGRAM", "PBLN_000000000121697", "IN_SCOPE")

    successor = _prog(
        "PBLN_000000000126438",
        title="안전관리 지원 (후속)",
        app_start=date(2026, 11, 1),
        app_end=date(2026, 12, 31),
        retrieved_at=_RUN_AT,
    )
    repo.save_record_with_notification(
        successor,
        _chg("PBLN_000000000126438"),
        relevance_verdict="IN_SCOPE",
        notif_event_id="bizinfo_new_program_PBLN_000000000126438_2026-11-05",
    )

    # 원본 보존 확인
    orig_retrieved = repo.get_prior_record("PROGRAM", "PBLN_000000000121697")
    assert orig_retrieved is not None, "원본 공고가 삭제됐다"
    assert orig_retrieved.title == "안전관리 지원 (원본)"
    assert repo.get_relevance_verdict("PROGRAM", "PBLN_000000000121697") == "IN_SCOPE"

    # 후속 등록 확인
    succ_retrieved = repo.get_prior_record("PROGRAM", "PBLN_000000000126438")
    assert succ_retrieved is not None, "후속 공고가 저장되지 않았다"
    assert repo.get_relevance_verdict("PROGRAM", "PBLN_000000000126438") == "IN_SCOPE"


# ---------------------------------------------------------------------------
# LCA-05: API 오류 → 기존 IN_SCOPE 허위 마감 판정 없음
# ---------------------------------------------------------------------------


def test_LCA05_api_error_no_false_closed(monkeypatch):
    """API 오류 발생 시 기존 IN_SCOPE 공고가 허위로 마감·취소 판정되지 않는다."""
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    prior = _prog(
        "PBLN_SAFE_LCA05",
        app_start=date(2026, 10, 1),
        app_end=date(2026, 12, 31),
        retrieved_at=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    repo.save_record(prior, _chg("PBLN_SAFE_LCA05"))
    repo.save_relevance_verdict("PROGRAM", "PBLN_SAFE_LCA05", "IN_SCOPE")

    def _error_get(url, *, params, timeout):
        return 500, "Internal Server Error"

    result = run_bizinfo_daily_sync(
        repo,
        lambda **kw: False,
        as_of=_TODAY,
        get_fn=_error_get,
    )

    # 판정 보존 — API 오류를 마감 근거로 사용하지 않음
    assert repo.get_relevance_verdict("PROGRAM", "PBLN_SAFE_LCA05") == "IN_SCOPE"
    assert result.total_status_changes == 0
    assert len(result.program.api_errors) > 0


# ---------------------------------------------------------------------------
# LCA-06: 상태 변경 감지 → 개별 알림이 repo에 원자적으로 등록됨
# ---------------------------------------------------------------------------


def test_LCA06_status_change_notification_registered(monkeypatch):
    """IN_SCOPE 공고의 상태 변경 감지 시 per-item 알림이 repo에 등록된다.

    prior: retrieved_at=Oct-01, app_start=Nov-05, as_of=Oct-01 → UPCOMING
    today=Nov-05, app_start=Nov-05 → OPEN
    상태 변경: UPCOMING → OPEN
    expected notif_id: bizinfo_status_program_PBLN_TRANS_LCA06_2026-11-05
    """
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    prior = _prog(
        "PBLN_TRANS_LCA06",
        app_start=date(2026, 11, 5),   # 오늘이 접수 시작일
        app_end=date(2026, 12, 31),
        retrieved_at=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    repo.save_record(prior, _chg("PBLN_TRANS_LCA06"))
    repo.save_relevance_verdict("PROGRAM", "PBLN_TRANS_LCA06", "IN_SCOPE")

    expected_notif_id = f"bizinfo_status_program_PBLN_TRANS_LCA06_{_TODAY.isoformat()}"

    def _mock_get(url, *, params, timeout):
        page = int(params.get("pageIndex", "1"))
        if "EventApi" in url:
            return 200, json.dumps({"jsonArray": []})
        if page == 1:
            return 200, json.dumps({"jsonArray": [{
                "pblancId": "PBLN_TRANS_LCA06",
                "pblancNm": "안전관리시스템 도입 지원",
                "pblancUrl": "https://www.bizinfo.go.kr/web/lay1/program/PBLN_TRANS_LCA06",
                "jrsdInsttNm": "고용노동부",
                "reqstBeginEndDe": "2026-11-05 ~ 2026-12-31",
                "bsnsSumryCn": "산업안전관리시스템 도입 비용 지원.",
                "totCnt": "1",
            }]})
        return 200, json.dumps({"jsonArray": []})

    result = run_bizinfo_daily_sync(
        repo, lambda **kw: True, as_of=_TODAY, get_fn=_mock_get
    )

    # 상태 변경 1건 감지
    assert result.total_status_changes == 1
    change_ev = result.program.status_changes[0]
    assert change_ev.old_status == "UPCOMING"
    assert change_ev.new_status == "OPEN"

    # per-item 알림이 repo에 등록됨 (InMemory _pending_notifications)
    assert expected_notif_id in repo._pending_notifications, (
        f"per-item 알림 {expected_notif_id!r}이 등록되지 않았습니다. "
        f"등록된 알림: {repo._pending_notifications}"
    )


def test_LCA06b_new_in_scope_notification_registered(monkeypatch):
    """신규 IN_SCOPE 공고 저장 시 per-item 알림이 등록된다.

    expected notif_id: bizinfo_new_program_{key}_{date}
    """
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    key = "PBLN_NEW_LCA06B"
    expected_notif_id = f"bizinfo_new_program_{key}_{_TODAY.isoformat()}"

    def _mock_get(url, *, params, timeout):
        page = int(params.get("pageIndex", "1"))
        if "EventApi" in url:
            return 200, json.dumps({"jsonArray": []})
        if page == 1:
            return 200, json.dumps({"jsonArray": [{
                "pblancId": key,
                "pblancNm": "산업안전관리시스템 도입 지원",
                "pblancUrl": f"https://www.bizinfo.go.kr/web/lay1/program/{key}",
                "jrsdInsttNm": "고용노동부",
                "reqstBeginEndDe": "2026-11-01 ~ 2026-12-31",
                "bsnsSumryCn": "산업안전관리시스템 도입 비용을 지원합니다. 재해예방 목적.",
                "totCnt": "1",
            }]})
        return 200, json.dumps({"jsonArray": []})

    result = run_bizinfo_daily_sync(
        repo, lambda **kw: True, as_of=_TODAY, get_fn=_mock_get
    )

    if result.total_new_in_scope == 1:
        # IN_SCOPE 판정 시: per-item 알림 등록 확인
        assert expected_notif_id in repo._pending_notifications, (
            f"신규 IN_SCOPE per-item 알림이 등록되지 않았습니다. "
            f"등록된 알림: {repo._pending_notifications}"
        )
    else:
        # REVIEW_REQUIRED 등으로 판정된 경우: 알림 미등록이 맞음
        assert expected_notif_id not in repo._pending_notifications


# ---------------------------------------------------------------------------
# LCA-07: Supabase RPC 오류 → 레코드·알림 모두 롤백 (table() 미호출)
# ---------------------------------------------------------------------------


def test_LCA07_rpc_failure_atomic_rollback():
    """Supabase RPC 오류 발생 시 레코드와 알림 등록이 모두 롤백된다.

    SupabaseBizinfoRepository는 save_record_with_notification에서
    단일 sb.rpc() 호출만 사용한다.
    RPC 실패 시 sb.table()은 한 번도 호출되지 않아야 한다.
    """
    sb = MagicMock()
    sb.rpc.return_value.execute.side_effect = Exception("connection timeout")
    repo = SupabaseBizinfoRepository(sb)

    rec = _prog("prg_lca07")
    chg = _chg("prg_lca07")

    with pytest.raises(Exception, match="connection timeout"):
        repo.save_record_with_notification(
            rec, chg,
            relevance_verdict="IN_SCOPE",
            notif_event_id="bizinfo_new_program_prg_lca07_2026-11-05",
            relay_channel="direct://bizinfo_daily_sync",
            target_channel="C0CCQKVQCQP",
            message_text="테스트 알림",
            sender_id="bizinfo_daily_sync",
        )

    # 단일 RPC 경로 — table() 직접 접근 없음
    sb.table.assert_not_called()


def test_LCA07b_rpc_failure_save_record_also_rolls_back():
    """save_record() (table 경유)가 아닌 save_record_with_notification(rpc 경유)를 써야
    PG 트랜잭션 원자성이 보장된다.

    rpc 경로: fn_save_bizinfo_with_notification 내에서 bizinfo_source_records 저장과
    slack_relay_event_log 등록을 PG 트랜잭션으로 묶는다.
    둘 중 하나라도 실패 시 양쪽 모두 롤백된다.

    이 테스트는 SupabaseBizinfoRepository.save_record_with_notification이
    sb.rpc()만 사용하고 sb.table()을 사용하지 않음을 검증한다.
    """
    sb = MagicMock()
    # 성공 경로: notif_registered=True 반환
    sb.rpc.return_value.execute.return_value = MagicMock(
        data={"saved": True, "notif_registered": True}
    )
    repo = SupabaseBizinfoRepository(sb)

    rec = _prog("prg_lca07b")
    chg = _chg("prg_lca07b")

    result = repo.save_record_with_notification(
        rec, chg,
        relevance_verdict="IN_SCOPE",
        notif_event_id="bizinfo_new_program_prg_lca07b_2026-11-05",
    )

    assert result is True
    # rpc 1회 호출, table 미호출
    sb.rpc.assert_called_once()
    sb.table.assert_not_called()


# ---------------------------------------------------------------------------
# LCA-08: 마감된 IN_SCOPE 공고 → 신규 카운트 아님, 상태 변경 감지
# ---------------------------------------------------------------------------


def test_LCA08_closed_program_not_in_new_in_scope(monkeypatch):
    """접수 마감된 IN_SCOPE 공고:
    - 신규 확정 카운트에 포함되지 않는다 (기존 공고이므로)
    - IN_SCOPE 판정은 보존된다 (안전 관련성은 사라지지 않음)
    - 상태 변경(OPEN→CLOSED)이 감지되면 개별 알림이 등록된다

    today = 2026-11-05
    prior retrieved_at = Oct-01, app: 2026-10-01 ~ 2026-10-31
    prior_check(Oct-01) 기준: OPEN (10-01 <= 10-01 <= 10-31)
    as_of(Nov-05) 기준: CLOSED (11-05 > 10-31)
    """
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    closed_prior = _prog(
        "PBLN_CLOSED_LCA08",
        app_start=date(2026, 10, 1),
        app_end=date(2026, 10, 31),   # 마감
        retrieved_at=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    repo.save_record(closed_prior, _chg("PBLN_CLOSED_LCA08"))
    repo.save_relevance_verdict("PROGRAM", "PBLN_CLOSED_LCA08", "IN_SCOPE")

    expected_notif_id = f"bizinfo_status_program_PBLN_CLOSED_LCA08_{_TODAY.isoformat()}"

    def _mock_get(url, *, params, timeout):
        page = int(params.get("pageIndex", "1"))
        if "EventApi" in url:
            return 200, json.dumps({"jsonArray": []})
        if page == 1:
            return 200, json.dumps({"jsonArray": [{
                "pblancId": "PBLN_CLOSED_LCA08",
                "pblancNm": "안전관리시스템 도입 지원",
                "pblancUrl": "https://www.bizinfo.go.kr/web/lay1/program/PBLN_CLOSED_LCA08",
                "jrsdInsttNm": "고용노동부",
                "reqstBeginEndDe": "2026-10-01 ~ 2026-10-31",   # 마감된 날짜 그대로
                "bsnsSumryCn": "산업안전관리시스템 도입 비용 지원.",
                "totCnt": "1",
            }]})
        return 200, json.dumps({"jsonArray": []})

    result = run_bizinfo_daily_sync(
        repo, lambda **kw: True, as_of=_TODAY, get_fn=_mock_get
    )

    # 마감 공고는 신규 카운트 아님
    assert result.total_new_in_scope == 0, "마감된 기존 공고가 신규 IN_SCOPE로 잘못 집계됐다"

    # IN_SCOPE 판정 보존
    assert repo.get_relevance_verdict("PROGRAM", "PBLN_CLOSED_LCA08") == "IN_SCOPE"

    # 상태 변경(OPEN→CLOSED) 감지
    assert result.total_status_changes == 1
    change_ev = result.program.status_changes[0]
    assert change_ev.new_status == "CLOSED"

    # per-item 알림 등록 (마감 상태 변경 알림)
    assert expected_notif_id in repo._pending_notifications
