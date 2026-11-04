"""tests/test_bizinfo_daily_sync.py — WO-TAI-BIZINFO-DAILY-SYNC-SLACK-001 단위 검증.

Production DB·API·Slack 호출 = 0 (전부 모의 주입).

커버리지:
  DS-01  실제 등록 SQL cron 표현식 → KST 13:00 검증
  DS-02  PROGRAM 수집 — 신규 공고 저장
  DS-03  EVENT 수집 — 신규 공고 저장
  DS-04  신규 OUT_OF_SCOPE → 알림 없음
  DS-05  신규 REVIEW_REQUIRED → 알림 없음
  DS-06  신규 IN_SCOPE → 알림 1회
  DS-07  기존 IN_SCOPE 상태 변화 없음 → 알림 없음
  DS-08  기존 IN_SCOPE 상태 변화 있음 → 알림 생성
  DS-09  행사 접수 종료와 행사 종료 구별
  DS-10  API 실패 → 상태 변경 없음
  DS-11  API 목록에서 기존 공고 미발견 → confirmed=0, 취소 판정 없음
  DS-12  기존 OUT_OF_SCOPE 판정 보호
  DS-13  동일 내용 재실행 → 중복 알림 없음 (content-based dedup)
  DS-14  Slack 접수 성공 → event_id 캡처됨 (재처리 가능)
  DS-15  기존 1,585건 데이터 보존 — sync가 기존 레코드를 삭제하지 않음
  DS-16  편집 승인·MKT 발행 기능에 영향 없음
  DS-17  같은 날 2회 실행 — 새 IN_SCOPE 발견 시 별도 알림 생성
  DS-18  기존 IN_SCOPE 모두 확인 후에도 뒤 페이지 계속 탐색
  DS-19  UTC/KST 날짜 경계 — KST 기준 prior_check 사용
  DS-20  프로세스 복구 한계 — DB 저장 후 중단 시 다음 실행 복구 불가 (별도 Gate)
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from services.bizinfo.daily_sync import (
    BizinfoDailySyncResult,
    NewInScopeEvent,
    StatusChangeEvent,
    build_slack_message,
    run_bizinfo_daily_sync,
)
from services.bizinfo.repository import InMemoryBizinfoRepository
from services.bizinfo.normalizer import DateRange, NormalizedSourceRecord
from services.bizinfo.status import ChangeRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TODAY = date(2026, 11, 5)
_NOW = datetime(2026, 11, 5, 4, 0, 0, tzinfo=timezone.utc)  # 13:00 KST


def _make_raw_program(
    key: str = "PBLN_TEST_001",
    title: str = "산업안전 지원사업",
    app_start: str = "2026-10-01",
    app_end: str = "2026-12-31",
) -> dict:
    return {
        "pblancId": key,
        "pblancNm": title,
        "pblancUrl": f"https://www.bizinfo.go.kr/web/lay1/program/{key}",
        "jrsdInsttNm": "고용노동부",
        "reqstBeginEndDe": f"{app_start} ~ {app_end}",
        "bsnsSumryCn": "산업안전관리시스템 도입 지원사업입니다.",
        "trgetNm": "50인 미만 사업장",
        "hashtags": "안전,지원",
        "totCnt": "1",
    }


def _make_raw_event(
    key: str = "EVEN_TEST_001",
    title: str = "산업안전 교육행사",
    evt_start: str = "20261101",
    evt_end: str = "20261130",
    rcp_start: str = "2026-10-01",
    rcp_end: str = "2026-10-31",
) -> dict:
    return {
        "eventInfoId": key,
        "nttNm": title,
        "bizinfoUrl": f"/web/lay1/event/{key}",
        "originOrg": "한국산업안전보건공단",
        "eventBeginEndDe": f"{evt_start} ~ {evt_end}",
        "rceptPd": f"{rcp_start} ~ {rcp_end}",
        "nttCn": "안전관리 전문인력 양성 교육행사입니다.",
        "hashtags": "안전,교육",
        "totCnt": "1",
    }


def _make_prior_program(
    key: str = "PBLN_PRIOR_001",
    title: str = "안전관리시스템 지원",
    app_start: date = date(2026, 11, 10),
    app_end: date = date(2026, 12, 31),
    retrieved_at: datetime = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
) -> NormalizedSourceRecord:
    return NormalizedSourceRecord(
        source_kind="PROGRAM",
        source_id="BIZINFO_PROGRAM",
        source_key=key,
        title=title,
        source_org="고용노동부",
        origin_url=None,
        bizinfo_url=f"https://www.bizinfo.go.kr/web/lay1/program/{key}",
        retrieved_at=retrieved_at,
        application_period=DateRange(start=app_start, end=app_end),
    )


def _make_prior_event(
    key: str = "EVEN_PRIOR_001",
    title: str = "안전관리 전문인력 교육",
    evt_start: date = date(2026, 11, 1),
    evt_end: date = date(2026, 11, 30),
    rcp_start: date = date(2026, 10, 1),
    rcp_end: date = date(2026, 10, 31),
    retrieved_at: datetime = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
) -> NormalizedSourceRecord:
    return NormalizedSourceRecord(
        source_kind="EVENT",
        source_id="BIZINFO_EVENT",
        source_key=key,
        title=title,
        source_org="KOSHA",
        origin_url=None,
        bizinfo_url=f"https://www.bizinfo.go.kr/web/lay1/event/{key}",
        retrieved_at=retrieved_at,
        event_period=DateRange(start=evt_start, end=evt_end),
        reception_period=DateRange(start=rcp_start, end=rcp_end),
    )


def _make_change(key: str, kind: str = "PROGRAM") -> ChangeRecord:
    return ChangeRecord(
        source_key=key,
        source_kind=kind,
        verdict="NO_CHANGE",
        changed_fields=(),
        checked_at=_NOW,
        source_updated_at=None,
    )


def _mock_get_fn_program(*raw_items: dict):
    """주어진 items를 page=1에서 반환, 그 이후는 EMPTY."""
    def _get(url, *, params, timeout):
        import json
        page = int(params.get("pageIndex", "1"))
        if page == 1 and raw_items:
            items_with_tot = [{**item, "totCnt": str(len(raw_items))} for item in raw_items]
            return 200, json.dumps({"jsonArray": items_with_tot})
        return 200, json.dumps({"jsonArray": []})
    return _get


def _mock_get_fn_event(*raw_items: dict):
    """EVENT API — page=1에서만 반환."""
    def _get(url, *, params, timeout):
        import json
        page = int(params.get("pageIndex", "1"))
        if page == 1 and raw_items:
            items_with_tot = [{**item, "totCnt": str(len(raw_items))} for item in raw_items]
            return 200, json.dumps({"jsonArray": items_with_tot})
        return 200, json.dumps({"jsonArray": []})
    return _get


def _mock_get_fn_error():
    """첫 페이지부터 HTTP 오류 반환."""
    def _get(url, *, params, timeout):
        return 500, "Internal Server Error"
    return _get


def _mock_get_fn_empty():
    """빈 응답 반환."""
    def _get(url, *, params, timeout):
        import json
        return 200, json.dumps({"jsonArray": []})
    return _get


def _make_slack_accept(accepted_events: Optional[list] = None, return_true: bool = True):
    """Slack accept 모의 함수 — 호출 기록 추적."""
    calls = accepted_events if accepted_events is not None else []

    def _accept(**kwargs):
        event_id = kwargs.get("event_id", "")
        if event_id in calls:
            return False  # 중복
        calls.append(event_id)
        return return_true

    return _accept, calls


def _get_fn_combined(program_items: list, event_items: list):
    """PROGRAM, EVENT URL 구분해 응답하는 통합 모의 함수."""
    def _get(url, *, params, timeout):
        import json
        page = int(params.get("pageIndex", "1"))
        if "EventApi" in url:
            items = event_items if page == 1 else []
        else:
            items = program_items if page == 1 else []
        if items:
            items_with_tot = [{**i, "totCnt": str(len(items))} for i in items]
        else:
            items_with_tot = []
        return 200, json.dumps({"jsonArray": items_with_tot})
    return _get


# ---------------------------------------------------------------------------
# DS-01: 매일 13:00 KST 시간 계산
# ---------------------------------------------------------------------------

def test_DS01_cron_expression_1pm_kst():
    """실제 등록 SQL의 cron 표현식을 읽어 KST 13:00 발화 검증.

    테스트와 배포 설정이 동일한 소스를 참조해 불일치를 방지한다.
    """
    from services.scheduler.cron_grammar import next_fire_at_or_after
    from zoneinfo import ZoneInfo

    sql_path = Path(__file__).parent.parent / "migrations" / "20261104_bizinfo_daily_sync_cron.sql"
    sql_text = sql_path.read_text(encoding="utf-8")

    # cron_job_master VALUES 블록에서 cron 표현식 추출
    match = re.search(r"'(\d+\s+\d+\s+\*\s+\*\s+\*)'", sql_text)
    assert match, "SQL에서 cron 표현식을 찾지 못했습니다"
    cron_expr = match.group(1)

    kst = ZoneInfo("Asia/Seoul")
    t0 = datetime(2026, 11, 5, 3, 59, 0, tzinfo=kst)
    next_fire = next_fire_at_or_after(cron_expr, t0)
    fire_kst = next_fire.astimezone(kst)
    assert fire_kst.hour == 13, f"KST 13:00이어야 함, 실제: {fire_kst.hour}:00 (cron='{cron_expr}')"
    assert fire_kst.minute == 0


# ---------------------------------------------------------------------------
# DS-02: PROGRAM 수집
# ---------------------------------------------------------------------------

def test_DS02_program_collection(monkeypatch):
    """PROGRAM API에서 신규 공고 2건을 정상 수집·저장한다."""
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    slack_fn, _ = _make_slack_accept()
    raw1 = _make_raw_program("PBLN_P001", "안전관리시스템 도입 지원")
    raw2 = _make_raw_program("PBLN_P002", "재해예방 장비 지원")
    gfn = _get_fn_combined(
        program_items=[raw1, raw2],
        event_items=[],
    )

    result = run_bizinfo_daily_sync(repo, slack_fn, as_of=_TODAY, get_fn=gfn)
    assert result.program.fetched == 2
    assert result.program.new_records_saved == 2
    assert repo.get_prior_record("PROGRAM", "PBLN_P001") is not None
    assert repo.get_prior_record("PROGRAM", "PBLN_P002") is not None


# ---------------------------------------------------------------------------
# DS-03: EVENT 수집
# ---------------------------------------------------------------------------

def test_DS03_event_collection(monkeypatch):
    """EVENT API에서 신규 공고 1건을 정상 수집·저장한다."""
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    slack_fn, _ = _make_slack_accept()
    raw_ev = _make_raw_event("EVEN_E001", "안전관리 전문인력 양성 교육")
    gfn = _get_fn_combined(program_items=[], event_items=[raw_ev])

    result = run_bizinfo_daily_sync(repo, slack_fn, as_of=_TODAY, get_fn=gfn)
    assert result.event.fetched == 1
    assert result.event.new_records_saved == 1
    assert repo.get_prior_record("EVENT", "EVEN_E001") is not None


# ---------------------------------------------------------------------------
# DS-04: 신규 OUT_OF_SCOPE → 알림 없음
# ---------------------------------------------------------------------------

def test_DS04_new_out_of_scope_no_alert(monkeypatch):
    """신규 공고가 OUT_OF_SCOPE로 판정되면 Slack 알림을 보내지 않는다."""
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    slack_fn, calls = _make_slack_accept()
    # 비안전 목적 공고 (판로개척)
    raw = _make_raw_program(
        "PBLN_MKT_001",
        "판로개척 마케팅 지원사업",
    )
    raw["bsnsSumryCn"] = "수출 판로 마케팅 지원 사업입니다."
    gfn = _get_fn_combined(program_items=[raw], event_items=[])

    result = run_bizinfo_daily_sync(repo, slack_fn, as_of=_TODAY, get_fn=gfn)
    assert result.total_new_in_scope == 0
    assert len(calls) == 0
    assert result.slack_skipped_reason in ("no_events", None) or not result.slack_event_accepted


# ---------------------------------------------------------------------------
# DS-05: 신규 REVIEW_REQUIRED → 알림 없음
# ---------------------------------------------------------------------------

def test_DS05_new_review_required_no_alert(monkeypatch):
    """신규 공고가 REVIEW_REQUIRED로 판정되면 Slack 알림을 보내지 않는다."""
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    slack_fn, calls = _make_slack_accept()
    # 모호한 공고 (스마트공장 — REVIEW_REQUIRED 예상)
    raw = _make_raw_program("PBLN_SF_001", "스마트공장 구축 지원")
    raw["bsnsSumryCn"] = "스마트공장 도입 비용을 지원합니다."
    gfn = _get_fn_combined(program_items=[raw], event_items=[])

    result = run_bizinfo_daily_sync(repo, slack_fn, as_of=_TODAY, get_fn=gfn)
    assert result.total_new_in_scope == 0
    assert len(calls) == 0


# ---------------------------------------------------------------------------
# DS-06: 신규 IN_SCOPE → 알림 1회
# ---------------------------------------------------------------------------

def test_DS06_new_in_scope_alert_once(monkeypatch):
    """신규 IN_SCOPE 확정 공고가 있으면 Slack accept가 정확히 1회 호출된다."""
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    slack_fn, calls = _make_slack_accept()
    # 직접 안전 키워드 포함 → IN_SCOPE 확정 예상
    raw = _make_raw_program("PBLN_SAF_001", "산업안전관리시스템 도입 지원")
    raw["bsnsSumryCn"] = "산업안전관리시스템 도입을 위한 비용을 지원합니다. 재해예방 목적."
    gfn = _get_fn_combined(program_items=[raw], event_items=[])

    result = run_bizinfo_daily_sync(repo, slack_fn, as_of=_TODAY, get_fn=gfn)
    assert result.total_new_in_scope == 1
    assert len(calls) == 1
    assert result.slack_event_accepted is True
    assert result.slack_event_id is not None
    assert result.slack_event_id.startswith(f"bizinfo_daily_sync_{_TODAY.isoformat()}_")


# ---------------------------------------------------------------------------
# DS-07: 기존 IN_SCOPE 상태 변화 없음 → 알림 없음
# ---------------------------------------------------------------------------

def test_DS07_existing_in_scope_no_status_change(monkeypatch):
    """기존 IN_SCOPE 공고가 재수집됐지만 상태 변화가 없으면 알림 없음."""
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    # 이미 IN_SCOPE이고 접수 중인 공고 (retrieved_at = 오늘)
    prior = _make_prior_program(
        key="PBLN_PRIOR_001",
        app_start=date(2026, 10, 1),
        app_end=date(2026, 12, 31),
        retrieved_at=datetime(2026, 11, 4, 0, 0, tzinfo=timezone.utc),  # 어제
    )
    repo.save_record(prior, _make_change("PBLN_PRIOR_001"))
    repo.save_relevance_verdict("PROGRAM", "PBLN_PRIOR_001", "IN_SCOPE")

    # 같은 날짜로 재수집 → today=11-05, app: 10-01~12-31 → OPEN (어제도 OPEN)
    raw = _make_raw_program("PBLN_PRIOR_001", "안전관리시스템 도입 지원",
                            app_start="2026-10-01", app_end="2026-12-31")
    gfn = _get_fn_combined(program_items=[raw], event_items=[])
    slack_fn, calls = _make_slack_accept()

    result = run_bizinfo_daily_sync(repo, slack_fn, as_of=_TODAY, get_fn=gfn)
    assert result.total_status_changes == 0
    assert len(calls) == 0


# ---------------------------------------------------------------------------
# DS-08: 기존 IN_SCOPE 상태 변화 있음 → 알림 생성
# ---------------------------------------------------------------------------

def test_DS08_existing_in_scope_status_change_alert(monkeypatch):
    """기존 IN_SCOPE 공고의 접수 상태가 UPCOMING→OPEN으로 전환되면 알림."""
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    # 이전 수집 시점(10/01)에서는 접수 예정(start=11/06, 오늘 11/05 기준 UPCOMING)
    # 오늘(11/05) 재수집하면 같은 날짜지만 as_of=11/05 → UPCOMING(11/06 아직 안됨)
    # → 실제 전환을 만들려면: 이전에 start=11/05이면 prior_check(=10/01) UPCOMING, 오늘 OPEN
    prior = _make_prior_program(
        key="PBLN_TRANS_001",
        app_start=date(2026, 11, 5),   # 오늘이 시작일
        app_end=date(2026, 12, 31),
        retrieved_at=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),  # 1달 전에 저장
    )
    repo.save_record(prior, _make_change("PBLN_TRANS_001"))
    repo.save_relevance_verdict("PROGRAM", "PBLN_TRANS_001", "IN_SCOPE")

    # 재수집 — 같은 날짜 유지
    raw = _make_raw_program("PBLN_TRANS_001", "안전관리시스템 지원",
                            app_start="2026-11-05", app_end="2026-12-31")
    gfn = _get_fn_combined(program_items=[raw], event_items=[])
    slack_fn, calls = _make_slack_accept()

    result = run_bizinfo_daily_sync(repo, slack_fn, as_of=_TODAY, get_fn=gfn)
    # prior_check=2026-10-01, start=2026-11-05 → UPCOMING
    # as_of=2026-11-05, start=2026-11-05 → OPEN
    assert result.total_status_changes == 1
    change_ev = result.program.status_changes[0]
    assert change_ev.old_status == "UPCOMING"
    assert change_ev.new_status == "OPEN"
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# DS-09: 행사 접수 종료와 행사 종료 구별
# ---------------------------------------------------------------------------

def test_DS09_event_reception_vs_progress_distinguished(monkeypatch):
    """EVENT: 접수 마감(CLOSED)과 행사 진행 중(ONGOING)은 독립 축으로 표시."""
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    # 이전: 접수 중(OPEN) + 행사 예정(UPCOMING)
    prior = _make_prior_event(
        key="EVEN_DUAL_001",
        evt_start=date(2026, 11, 5),  # 오늘 시작
        evt_end=date(2026, 11, 30),
        rcp_start=date(2026, 10, 1),
        rcp_end=date(2026, 10, 31),   # 접수 이미 마감
        retrieved_at=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    repo.save_record(prior, _make_change("EVEN_DUAL_001", "EVENT"))
    repo.save_relevance_verdict("EVENT", "EVEN_DUAL_001", "IN_SCOPE")

    raw_ev = _make_raw_event(
        "EVEN_DUAL_001",
        "안전관리 전문인력 교육",
        evt_start="20261105", evt_end="20261130",
        rcp_start="2026-10-01", rcp_end="2026-10-31",
    )
    gfn = _get_fn_combined(program_items=[], event_items=[raw_ev])
    slack_fn, calls = _make_slack_accept()

    result = run_bizinfo_daily_sync(repo, slack_fn, as_of=_TODAY, get_fn=gfn)
    assert result.total_status_changes == 1
    ev = result.event.status_changes[0]
    # 접수는 prior_check에서 OPEN → 오늘 CLOSED
    # 행사는 prior_check에서 UPCOMING → 오늘 ONGOING
    assert "접수:" in ev.new_status and "행사:" in ev.new_status
    assert "CLOSED" in ev.new_status
    assert "ONGOING" in ev.new_status


# ---------------------------------------------------------------------------
# DS-10: API 실패 → 상태 변경 없음
# ---------------------------------------------------------------------------

def test_DS10_api_failure_no_status_change(monkeypatch):
    """API 오류 발생 시 기존 공고의 상태 변경·신규 판정·Slack 발송 없음."""
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    prior = _make_prior_program(key="PBLN_SAFE_001")
    repo.save_record(prior, _make_change("PBLN_SAFE_001"))
    repo.save_relevance_verdict("PROGRAM", "PBLN_SAFE_001", "IN_SCOPE")

    gfn = _mock_get_fn_error()
    slack_fn, calls = _make_slack_accept()

    result = run_bizinfo_daily_sync(repo, slack_fn, as_of=_TODAY, get_fn=gfn)
    assert result.program.fetched == 0
    assert len(result.program.api_errors) > 0
    assert result.total_status_changes == 0
    assert len(calls) == 0


# ---------------------------------------------------------------------------
# DS-11: API 목록에서 기존 공고 미발견 → confirmed=0, 취소 판정 없음
# ---------------------------------------------------------------------------

def test_DS11_in_scope_not_found_unconfirmed(monkeypatch):
    """API 페이지에서 발견되지 않은 IN_SCOPE 공고는 취소/마감으로 판정하지 않는다."""
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    # 기존 IN_SCOPE이지만 API 응답에 포함되지 않는 공고
    prior = _make_prior_program(key="PBLN_MISSING_001")
    repo.save_record(prior, _make_change("PBLN_MISSING_001"))
    repo.save_relevance_verdict("PROGRAM", "PBLN_MISSING_001", "IN_SCOPE")

    # API에 없는 다른 공고만 반환
    raw = _make_raw_program("PBLN_OTHER_001", "다른 사업")
    gfn = _get_fn_combined(program_items=[raw], event_items=[])
    slack_fn, _ = _make_slack_accept()

    result = run_bizinfo_daily_sync(repo, slack_fn, as_of=_TODAY, get_fn=gfn)
    assert result.program.in_scope_confirmed == 0
    assert result.program.in_scope_total == 1
    # 기존 판정 보존 — 취소/마감 아님
    verdict = repo.get_relevance_verdict("PROGRAM", "PBLN_MISSING_001")
    assert verdict == "IN_SCOPE"


# ---------------------------------------------------------------------------
# DS-12: 기존 OUT_OF_SCOPE 판정 보호
# ---------------------------------------------------------------------------

def test_DS12_preserve_out_of_scope_verdict(monkeypatch):
    """재수집된 기존 OUT_OF_SCOPE 공고의 판정이 보존된다."""
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    prior = _make_prior_program(key="PBLN_OUT_001", title="판로개척 마케팅 지원")
    repo.save_record(prior, _make_change("PBLN_OUT_001"))
    repo.save_relevance_verdict("PROGRAM", "PBLN_OUT_001", "OUT_OF_SCOPE")

    # 재수집 — 같은 키, 안전 키워드 없는 raw
    raw = _make_raw_program("PBLN_OUT_001", "판로개척 마케팅 지원")
    raw["bsnsSumryCn"] = "수출 판로 마케팅을 지원합니다."
    gfn = _get_fn_combined(program_items=[raw], event_items=[])
    slack_fn, _ = _make_slack_accept()

    run_bizinfo_daily_sync(repo, slack_fn, as_of=_TODAY, get_fn=gfn)
    verdict = repo.get_relevance_verdict("PROGRAM", "PBLN_OUT_001")
    assert verdict == "OUT_OF_SCOPE", "OUT_OF_SCOPE 판정이 보존돼야 한다"


# ---------------------------------------------------------------------------
# DS-13: 동일 실행 재시도 → 중복 알림 없음
# ---------------------------------------------------------------------------

def test_DS13_no_duplicate_on_retry(monkeypatch):
    """같은 날 재실행 시 Slack accept가 2번째는 False를 반환해 중복 없음."""
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    raw = _make_raw_program("PBLN_SAF_DUP", "산업안전관리시스템 도입 지원")
    raw["bsnsSumryCn"] = "산업안전관리시스템 도입 비용 지원. 재해예방."
    gfn = _get_fn_combined(program_items=[raw], event_items=[])

    already_accepted: list = []

    def _dedup_slack(**kwargs):
        event_id = kwargs["event_id"]
        if event_id in already_accepted:
            return False
        already_accepted.append(event_id)
        return True

    # 1회 실행
    r1 = run_bizinfo_daily_sync(repo, _dedup_slack, as_of=_TODAY, get_fn=gfn)
    assert r1.slack_event_accepted is True
    first_event_id = r1.slack_event_id

    # 2회 실행 — 별도 repo로 동일 아이템이 다시 신규로 발견되지만
    # 같은 내용 → 같은 content_hash → 같은 event_id → duplicate_event_id
    repo2 = InMemoryBizinfoRepository()
    r2 = run_bizinfo_daily_sync(repo2, _dedup_slack, as_of=_TODAY, get_fn=gfn)
    assert r2.slack_event_accepted is False
    assert r2.slack_skipped_reason == "duplicate_event_id"
    assert r2.slack_event_id == first_event_id  # 동일 내용 → 동일 event_id


# ---------------------------------------------------------------------------
# DS-14: Slack 실패 → event_id 캡처됨 (재처리 가능)
# ---------------------------------------------------------------------------

def test_DS14_slack_event_id_captured_for_retry(monkeypatch):
    """Slack accept가 호출되면 event_id가 결과에 기록돼 재처리 경로가 존재한다."""
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    raw = _make_raw_program("PBLN_SAF_RETRY", "산업안전관리시스템 지원")
    raw["bsnsSumryCn"] = "산업안전관리시스템 도입 지원. 재해예방 장비."
    gfn = _get_fn_combined(program_items=[raw], event_items=[])

    # accept는 성공(True)하지만 실제 Slack 전송은 별도 worker가 담당
    slack_fn, calls = _make_slack_accept(return_true=True)

    result = run_bizinfo_daily_sync(repo, slack_fn, as_of=_TODAY, get_fn=gfn)
    # event_id = "bizinfo_daily_sync_{날짜}_{content_hash}" 형식
    assert result.slack_event_id is not None
    assert result.slack_event_id.startswith(f"bizinfo_daily_sync_{_TODAY.isoformat()}_")
    assert result.slack_event_id in calls  # relay 접수 확인


# ---------------------------------------------------------------------------
# DS-15: 기존 1,585건 데이터 보존
# ---------------------------------------------------------------------------

def test_DS15_existing_records_preserved(monkeypatch):
    """일일 동기화가 API에서 반환되지 않은 기존 레코드를 삭제하지 않는다."""
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    # 기존 레코드 3건 (API 응답에 없는 것들)
    for i in range(3):
        p = _make_prior_program(key=f"PBLN_EXISTING_{i:03d}")
        repo.save_record(p, _make_change(f"PBLN_EXISTING_{i:03d}"))
        repo.save_relevance_verdict("PROGRAM", f"PBLN_EXISTING_{i:03d}", "REVIEW_REQUIRED")

    # API는 완전히 다른 공고 1건 반환
    raw = _make_raw_program("PBLN_NEW_001", "신규 사업")
    gfn = _get_fn_combined(program_items=[raw], event_items=[])
    slack_fn, _ = _make_slack_accept()

    run_bizinfo_daily_sync(repo, slack_fn, as_of=_TODAY, get_fn=gfn)

    # 기존 레코드 3건 보존 확인
    for i in range(3):
        assert repo.get_prior_record("PROGRAM", f"PBLN_EXISTING_{i:03d}") is not None


# ---------------------------------------------------------------------------
# DS-16: 편집 승인·MKT 발행 기능에 영향 없음
# ---------------------------------------------------------------------------

def test_DS16_editorial_approval_unaffected(monkeypatch):
    """일일 동기화 실행 후 editorial·approval 데이터가 변경되지 않는다."""
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    from services.bizinfo.approval import EditorialContent, ContentApprovalRecord
    from datetime import datetime

    repo = InMemoryBizinfoRepository()
    prior = _make_prior_program(key="PBLN_EDIT_001", title="산업안전관리시스템 지원")
    repo.save_record(prior, _make_change("PBLN_EDIT_001"))
    repo.save_relevance_verdict("PROGRAM", "PBLN_EDIT_001", "IN_SCOPE")

    editorial = EditorialContent(
        source_key="PBLN_EDIT_001",
        source_kind="PROGRAM",
        explanation="TAI 해설 텍스트",
        guidance="실무 안내",
        authored_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        tai_link="/safety-search",
    )
    repo.seed_editorial(editorial)

    approval = ContentApprovalRecord(
        source_key="PBLN_EDIT_001",
        source_kind="PROGRAM",
        approved_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
        approved_by="approver-01",
    )
    repo.seed_approval(approval)

    raw = _make_raw_program("PBLN_EDIT_001", "산업안전관리시스템 지원")
    gfn = _get_fn_combined(program_items=[raw], event_items=[])
    slack_fn, _ = _make_slack_accept()

    run_bizinfo_daily_sync(repo, slack_fn, as_of=_TODAY, get_fn=gfn)

    # editorial·approval 불변 확인
    ed_after = repo.get_editorial("PROGRAM", "PBLN_EDIT_001")
    ap_after = repo.get_approval("PROGRAM", "PBLN_EDIT_001")
    assert ed_after is not None
    assert ed_after.explanation == "TAI 해설 텍스트"
    assert ap_after is not None
    assert ap_after.approved_by == "approver-01"


# ---------------------------------------------------------------------------
# DS-17: 같은 날 2회 실행 — 새 IN_SCOPE 발견 시 별도 알림 생성
# ---------------------------------------------------------------------------

def test_DS17_new_content_on_second_run_same_day(monkeypatch):
    """같은 날 2회 실행에서 새 IN_SCOPE 공고가 발견되면 다른 event_id로 별도 알림이 생성된다.

    content-based fingerprint 덕분에 같은 날 발견한 새 내용은 1회차 알림과 별개로 처리된다.
    """
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    accepted_ids: list = []

    def _dedup_slack(**kwargs):
        eid = kwargs["event_id"]
        if eid in accepted_ids:
            return False
        accepted_ids.append(eid)
        return True

    # 1회 실행: item A만 있음
    raw_a = _make_raw_program("PBLN_SAF_A", "산업안전관리시스템 지원")
    raw_a["bsnsSumryCn"] = "산업안전관리시스템 도입 지원. 재해예방."
    repo1 = InMemoryBizinfoRepository()
    r1 = run_bizinfo_daily_sync(
        repo1, _dedup_slack, as_of=_TODAY,
        get_fn=_get_fn_combined(program_items=[raw_a], event_items=[]),
    )
    assert r1.slack_event_accepted is True
    id_first = r1.slack_event_id

    # 2회 실행: item A + item B (신규)
    raw_b = _make_raw_program("PBLN_SAF_B", "재해예방 장비 지원")
    raw_b["bsnsSumryCn"] = "재해예방 장비 구입 비용 지원. 산업안전관리."
    repo2 = InMemoryBizinfoRepository()
    r2 = run_bizinfo_daily_sync(
        repo2, _dedup_slack, as_of=_TODAY,
        get_fn=_get_fn_combined(program_items=[raw_a, raw_b], event_items=[]),
    )
    assert r2.slack_event_accepted is True, "새 내용이 있으면 별도 알림이 허용돼야 한다"
    assert r2.slack_event_id != id_first, "다른 내용 → 다른 event_id"


# ---------------------------------------------------------------------------
# DS-18: 기존 IN_SCOPE 모두 확인 후에도 뒤 페이지 계속 탐색
# ---------------------------------------------------------------------------

def test_DS18_continues_scan_after_in_scope_confirmed(monkeypatch):
    """기존 IN_SCOPE 공고가 모두 발견돼도 max_pages까지 탐색을 계속해 신규 공고를 누락하지 않는다."""
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")
    # _PAGE_SIZE=1로 낮춰 각 페이지에 1건씩 반환
    monkeypatch.setattr("services.bizinfo.daily_sync._PAGE_SIZE", 1)

    repo = InMemoryBizinfoRepository()
    prior = _make_prior_program(key="PBLN_KNOWN_PAGE1")
    repo.save_record(prior, _make_change("PBLN_KNOWN_PAGE1"))
    repo.save_relevance_verdict("PROGRAM", "PBLN_KNOWN_PAGE1", "IN_SCOPE")

    # Page 1: known IN_SCOPE
    # Page 2: 중간 비IN_SCOPE 공고
    # Page 3: 신규 공고 (뒤 페이지에만 존재)
    p1 = _make_raw_program("PBLN_KNOWN_PAGE1", "안전관리시스템 지원")
    p2 = _make_raw_program("PBLN_MIDDLE_P2", "다른 분야 지원")
    p3 = _make_raw_program("PBLN_NEW_PAGE3", "재해예방 안전장비 지원")

    def _multipage_get(url, *, params, timeout):
        import json
        page = int(params.get("pageIndex", "1"))
        if "EventApi" in url:
            return 200, json.dumps({"jsonArray": []})
        # PAGE_SIZE=1이므로 totCnt를 실제 항목 수로 설정
        if page == 1:
            return 200, json.dumps({"jsonArray": [{**p1, "totCnt": "3"}]})
        elif page == 2:
            return 200, json.dumps({"jsonArray": [{**p2, "totCnt": "3"}]})
        elif page == 3:
            return 200, json.dumps({"jsonArray": [{**p3, "totCnt": "3"}]})
        return 200, json.dumps({"jsonArray": []})

    slack_fn, _ = _make_slack_accept()
    result = run_bizinfo_daily_sync(repo, slack_fn, as_of=_TODAY,
                                   get_fn=_multipage_get, max_pages=3)

    assert result.program.fetched == 3, "3페이지 모두 수집돼야 한다"
    assert repo.get_prior_record("PROGRAM", "PBLN_NEW_PAGE3") is not None, \
        "page 3의 신규 공고가 저장돼야 한다"


# ---------------------------------------------------------------------------
# DS-19: UTC/KST 날짜 경계 — KST 기준 prior_check 사용
# ---------------------------------------------------------------------------

def test_DS19_kst_date_boundary_prior_check(monkeypatch):
    """UTC 자정 전후 수집된 공고의 prior_check는 KST 날짜 기준이다.

    retrieved_at = 2026-11-04 15:30 UTC = 2026-11-05 00:30 KST
    KST 날짜 = 2026-11-05 (오늘, as_of 와 동일)
    app_start = 2026-11-05 → prior_check와 as_of 모두 KST 11-05 → 같은 상태 → 변경 없음

    UTC 날짜로 계산했다면 prior_check = 11-04 → UPCOMING vs as_of=11-05 → OPEN
    → 잘못된 상태 변경 경보가 발생한다.
    """
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()
    # UTC Nov 4 15:30 = KST Nov 5 00:30 (오늘 KST)
    prior = _make_prior_program(
        key="PBLN_KST_001",
        app_start=date(2026, 11, 5),   # 오늘 시작
        app_end=date(2026, 12, 31),
        retrieved_at=datetime(2026, 11, 4, 15, 30, 0, tzinfo=timezone.utc),
    )
    repo.save_record(prior, _make_change("PBLN_KST_001"))
    repo.save_relevance_verdict("PROGRAM", "PBLN_KST_001", "IN_SCOPE")

    raw = _make_raw_program("PBLN_KST_001", "안전관리시스템 지원",
                            app_start="2026-11-05", app_end="2026-12-31")
    gfn = _get_fn_combined(program_items=[raw], event_items=[])
    slack_fn, _ = _make_slack_accept()

    result = run_bizinfo_daily_sync(repo, slack_fn, as_of=_TODAY, get_fn=gfn)
    assert result.total_status_changes == 0, (
        "KST 같은 날 수집된 공고는 prior_check=as_of이므로 상태 변경으로 보고하지 않아야 한다"
    )


# ---------------------------------------------------------------------------
# DS-20: 프로세스 복구 한계 — DB 저장 후 중단 시 다음 실행에서 복구 불가
# ---------------------------------------------------------------------------

def test_DS20_process_crash_recovery_known_limitation(monkeypatch):
    """DB 저장 후 Slack 접수 전 프로세스 중단 시 다음 실행에서 알림 복구 불가.

    KNOWN_LIMITATION: at-least-once Slack 보장은 별도 Gate가 필요하다.
    현재 구현에서는 이미 저장된 공고를 "기존 공고"로 처리하므로
    재실행에서 신규 알림이 생성되지 않는다.
    """
    monkeypatch.setenv("BIZINFO_API_KEY", "test_key")
    monkeypatch.setenv("BIZINFO_EVENT_API_KEY", "test_event_key")

    repo = InMemoryBizinfoRepository()

    # 이전 실행에서 DB 저장은 성공했지만 Slack 접수 전 중단된 상황 시뮬레이션:
    # DB에는 IN_SCOPE로 저장돼 있지만 Slack 이벤트 미생성
    # prior와 raw 날짜를 동일하게 맞춰 상태 변경이 발생하지 않도록 함
    prior = _make_prior_program(
        key="PBLN_CRASH_001",
        title="산업안전관리시스템 지원",
        app_start=date(2026, 10, 1),
        app_end=date(2026, 12, 31),
        retrieved_at=datetime(2026, 11, 4, 0, 0, tzinfo=timezone.utc),  # 어제
    )
    repo.save_record(prior, _make_change("PBLN_CRASH_001"))
    repo.save_relevance_verdict("PROGRAM", "PBLN_CRASH_001", "IN_SCOPE")

    raw = _make_raw_program("PBLN_CRASH_001", "산업안전관리시스템 지원",
                            app_start="2026-10-01", app_end="2026-12-31")
    gfn = _get_fn_combined(program_items=[raw], event_items=[])
    slack_fn, calls = _make_slack_accept()

    result = run_bizinfo_daily_sync(repo, slack_fn, as_of=_TODAY, get_fn=gfn)

    # 이미 known_in_scope에 있고 상태 변경도 없으므로 알림이 생성되지 않음
    # → 이것이 현재의 known limitation
    assert result.total_new_in_scope == 0
    assert result.total_status_changes == 0
    assert result.slack_skipped_reason == "no_events"
    assert len(calls) == 0  # Slack 접수 없음 — 복구 불가 확인
