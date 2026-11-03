"""OBJ-BZI-002 Bizinfo Normalizer unit tests.

WO-TAI-BIZINFO-OBJ-002-CODE-001.
No DB / no network / no API calls.

Test IDs follow design contract:
  P-xx = PROGRAM cases
  E-xx = EVENT cases
  C-xx = common / cross-cutting cases
"""
from __future__ import annotations

import pytest
from datetime import date, datetime, timezone

from services.bizinfo.normalizer import (
    DateRange,
    NormalizedSourceRecord,
    ParseFailure,
    normalize_bizinfo_record,
)

_NOW = datetime(2026, 11, 3, 9, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prog(**kwargs) -> dict:
    base = {
        "pblancId": "P001",
        "pblancNm": "산업재해 예방 설비 지원사업",
        "pblancUrl": "https://www.bizinfo.go.kr/portal/bid/P001",
        "reqstBeginEndDe": "2026-10-01 ~ 2026-11-30",
        "jrsdInsttNm": "고용노동부",
    }
    base.update(kwargs)
    return base


def _event(**kwargs) -> dict:
    base = {
        "eventInfoId": "E001",
        "nttNm": "산업안전보건 박람회",
        "bizinfoUrl": "/portal/event/E001",
        "eventBeginEndDe": "20261101 ~ 20261103",
        "rceptPd": "2026-10-01 ~ 2026-10-31",
        "originOrg": "안전보건공단",
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# PROGRAM tests
# ---------------------------------------------------------------------------


def test_P01_program_normal():
    """P-01: PROGRAM 정상 응답."""
    rec = normalize_bizinfo_record("PROGRAM", _prog(), _NOW)
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.source_kind == "PROGRAM"
    assert rec.source_key == "P001"
    assert rec.title == "산업재해 예방 설비 지원사업"
    assert rec.application_period == DateRange(
        date(2026, 10, 1), date(2026, 11, 30)
    )
    assert rec.source_updated_at is None
    assert rec.retrieved_at == _NOW


def test_P02_program_empty_application_period():
    """P-02: reqstBeginEndDe 공백 → application_period=None, parse_errors에 기록."""
    rec = normalize_bizinfo_record("PROGRAM", _prog(reqstBeginEndDe=""), _NOW)
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.application_period is None
    # R1-02: empty period must be recorded, not silently dropped
    assert any("reqstBeginEndDe" in e for e in rec.parse_errors)


def test_P03_program_missing_id():
    """P-03: pblancId 없음 → ParseFailure."""
    raw = _prog()
    del raw["pblancId"]
    result = normalize_bizinfo_record("PROGRAM", raw, _NOW)
    assert isinstance(result, ParseFailure)
    assert any("pblancId" in r for r in result.reasons)


def test_P04_program_bizinfo_absolute_url():
    """P-04: pblancUrl 절대경로 정상 처리."""
    rec = normalize_bizinfo_record(
        "PROGRAM",
        _prog(pblancUrl="https://www.bizinfo.go.kr/portal/bid/P001"),
        _NOW,
    )
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.bizinfo_url == "https://www.bizinfo.go.kr/portal/bid/P001"
    assert not any("bizinfo_url" in e for e in rec.parse_errors)


def test_P05_program_no_origin_url():
    """P-05: 원공고 URL 필드 없음 → origin_url=None, evidence_pending 기록."""
    raw = _prog()
    raw.pop("orginlUrlAdres", None)
    raw.pop("originUrl", None)
    rec = normalize_bizinfo_record("PROGRAM", raw, _NOW)
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.origin_url is None
    assert any("origin_url" in ep for ep in rec.evidence_pending)


def test_P06_program_reversed_dates():
    """P-06: 날짜 역전 (종료 < 시작)."""
    rec = normalize_bizinfo_record(
        "PROGRAM",
        _prog(reqstBeginEndDe="2026-12-31 ~ 2026-01-01"),
        _NOW,
    )
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.application_period is not None
    assert rec.application_period.parse_note == "date_reversed"


def test_P07_program_impossible_date():
    """P-07: 존재하지 않는 날짜 (2월 30일)."""
    rec = normalize_bizinfo_record(
        "PROGRAM",
        _prog(reqstBeginEndDe="2026-02-30 ~ 2026-03-01"),
        _NOW,
    )
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.application_period is not None
    assert rec.application_period.parse_note == "format_error"


# ---------------------------------------------------------------------------
# EVENT tests
# ---------------------------------------------------------------------------


def test_E01_event_normal():
    """E-01: EVENT 정상 응답."""
    rec = normalize_bizinfo_record("EVENT", _event(), _NOW)
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.source_kind == "EVENT"
    assert rec.source_key == "E001"
    assert rec.event_period == DateRange(date(2026, 11, 1), date(2026, 11, 3))
    assert rec.reception_period == DateRange(date(2026, 10, 1), date(2026, 10, 31))
    assert rec.source_updated_at is None


def test_E02_event_reception_start_missing():
    """E-02: rceptPd 시작일 없음 ('~ 2026-11-25')."""
    rec = normalize_bizinfo_record(
        "EVENT", _event(rceptPd="~ 2026-11-25"), _NOW
    )
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.reception_period is not None
    assert rec.reception_period.start is None
    assert rec.reception_period.end == date(2026, 11, 25)
    assert rec.reception_period.parse_note == "start_missing"


def test_E03_event_no_reception_period():
    """E-03: rceptPd 필드 없음 → reception_period=None."""
    raw = _event()
    del raw["rceptPd"]
    rec = normalize_bizinfo_record("EVENT", raw, _NOW)
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.reception_period is None


def test_E04_event_period_uses_compact_parser():
    """E-04: eventBeginEndDe는 YYYYMMDD 형식(파서 B) 전용."""
    # 하이픈 있는 형식은 파싱 실패해야 함
    rec = normalize_bizinfo_record(
        "EVENT",
        _event(eventBeginEndDe="2026-11-01 ~ 2026-11-03"),
        _NOW,
    )
    assert isinstance(rec, NormalizedSourceRecord)
    # hyphened format should fail compact parser
    assert rec.event_period is not None
    assert rec.event_period.parse_note == "format_error"


def test_E05_event_missing_id():
    """E-05: eventInfoId 없음 → ParseFailure."""
    raw = _event()
    del raw["eventInfoId"]
    result = normalize_bizinfo_record("EVENT", raw, _NOW)
    assert isinstance(result, ParseFailure)
    assert any("eventInfoId" in r for r in result.reasons)


def test_E06_event_reversed_dates():
    """E-06: 행사기간 역전."""
    rec = normalize_bizinfo_record(
        "EVENT",
        _event(eventBeginEndDe="20261231 ~ 20261101"),
        _NOW,
    )
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.event_period is not None
    assert rec.event_period.parse_note == "date_reversed"


# ---------------------------------------------------------------------------
# Common / cross-cutting tests
# ---------------------------------------------------------------------------


def test_C03_no_source_updated_at():
    """C-03: source_updated_at 필드 없음 → None, evidence_pending 기록."""
    rec = normalize_bizinfo_record("PROGRAM", _prog(), _NOW)
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.source_updated_at is None
    assert any("source_updated_at" in ep for ep in rec.evidence_pending)


def test_C04_auth_key_not_in_output():
    """C-04: raw에 인증키가 포함되어도 정규화 결과에 노출되지 않음."""
    secret = "LEAKED_API_KEY_VALUE_12345"
    raw = _prog(crtfcKey=secret)
    rec = normalize_bizinfo_record("PROGRAM", raw, _NOW)
    assert isinstance(rec, NormalizedSourceRecord)
    result_str = str(rec)
    assert secret not in result_str
    # parse_errors나 evidence_pending에도 없어야 함
    for item in rec.parse_errors + rec.evidence_pending:
        assert secret not in item


def test_C05_non_bizinfo_url_rejected():
    """C-05: 다른 도메인 URL → bizinfo_url=None, parse_errors에 기록."""
    rec = normalize_bizinfo_record(
        "PROGRAM",
        _prog(pblancUrl="https://evil.example.com/path"),
        _NOW,
    )
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.bizinfo_url is None
    assert any("bizinfo_url" in e for e in rec.parse_errors)
    # 오류 메시지에 원본 URL 없음
    for e in rec.parse_errors:
        assert "evil.example.com" not in e


def test_C06_empty_title_returns_failure():
    """C-06: title 공백 → ParseFailure."""
    result = normalize_bizinfo_record("PROGRAM", _prog(pblancNm=""), _NOW)
    assert isinstance(result, ParseFailure)
    assert any("pblancNm" in r for r in result.reasons)


def test_C07_bizinfo_lookalike_domain_rejected():
    """C-07: 기업마당 도메인 위장 URL 차단."""
    lookalikes = [
        "https://www.bizinfo.go.kr.evil.example/path",
        "https://www.bizinfo.go.kr@evil.example/path",
        "http://www.bizinfo.go.kr/portal/bid/P001",
    ]
    for url in lookalikes:
        rec = normalize_bizinfo_record("PROGRAM", _prog(pblancUrl=url), _NOW)
        assert isinstance(rec, NormalizedSourceRecord), f"should be record for {url}"
        assert rec.bizinfo_url is None, f"should reject {url}"
        # 오류 메시지에 원본 URL 없음
        for e in rec.parse_errors:
            assert url not in e


def test_C08_event_relative_url_converted():
    """C-08: 행사 bizinfoUrl 상대경로 → 절대경로 변환."""
    rec = normalize_bizinfo_record(
        "EVENT", _event(bizinfoUrl="/portal/event/E999"), _NOW
    )
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.bizinfo_url == "https://www.bizinfo.go.kr/portal/event/E999"


def test_C09_external_url_http_allowed():
    """C-09: 외부 원공고 URL은 http도 허용."""
    rec = normalize_bizinfo_record(
        "EVENT",
        _event(orginlUrlAdres="http://www.moel.go.kr/notice/detail"),
        _NOW,
    )
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.origin_url == "http://www.moel.go.kr/notice/detail"


def test_C10_external_url_with_userinfo_rejected():
    """C-10: 사용자정보 포함 외부 URL 차단."""
    rec = normalize_bizinfo_record(
        "EVENT",
        _event(orginlUrlAdres="https://user:pass@moel.go.kr/notice"),
        _NOW,
    )
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.origin_url is None
    for e in rec.parse_errors:
        # 비밀번호 노출 없음
        assert "pass" not in e


def test_C11_event_and_program_periods_independent():
    """C-11: EVENT 필드가 PROGRAM에 혼입되지 않음."""
    rec = normalize_bizinfo_record("PROGRAM", _prog(), _NOW)
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.event_period is None
    assert rec.reception_period is None

    rec2 = normalize_bizinfo_record("EVENT", _event(), _NOW)
    assert isinstance(rec2, NormalizedSourceRecord)
    assert rec2.application_period is None


# ---------------------------------------------------------------------------
# R1 보정 테스트
# ---------------------------------------------------------------------------


def test_C12_invalid_kind_returns_failure():
    """C-12: PROGRAM·EVENT 이외의 kind → ParseFailure (EVENT로 자동 전환 금지)."""
    result = normalize_bizinfo_record("INVALID_KIND", _prog(), _NOW)  # type: ignore[arg-type]
    assert isinstance(result, ParseFailure)
    assert any("invalid_source_kind" in r for r in result.reasons)


def test_C13_malformed_bizinfo_url_safe():
    """C-13: 파싱 불가 bizinfo URL → bizinfo_url=None, 예외 없이 처리."""
    malformed_urls = [
        "https://[invalid-ipv6",       # broken IPv6
        "https://\x00evil.com/path",   # null byte
    ]
    for url in malformed_urls:
        rec = normalize_bizinfo_record("PROGRAM", _prog(pblancUrl=url), _NOW)
        assert isinstance(rec, NormalizedSourceRecord), f"must not raise for {repr(url)}"
        assert rec.bizinfo_url is None
        for e in rec.parse_errors:
            assert url not in e


def test_C14_hostless_external_url_rejected():
    """C-14: 호스트 없는 외부 URL 거부."""
    no_host_urls = [
        "https:///path/only",   # no host
        "http://localhost/test",  # no dot — not a real domain
    ]
    for url in no_host_urls:
        rec = normalize_bizinfo_record(
            "EVENT", _event(orginlUrlAdres=url), _NOW
        )
        assert isinstance(rec, NormalizedSourceRecord), f"must not raise for {repr(url)}"
        assert rec.origin_url is None
        for e in rec.parse_errors:
            assert url not in e


def test_P08_date_short_digits_rejected():
    """P-08: YYYY-MM-DD 자릿수 부족 (2026-11-1) → format_error."""
    rec = normalize_bizinfo_record(
        "PROGRAM",
        _prog(reqstBeginEndDe="2026-11-1 ~ 2026-11-30"),
        _NOW,
    )
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.application_period is not None
    assert rec.application_period.parse_note == "format_error"


def test_E07_compact_date_short_digits_rejected():
    """E-07: YYYYMMDD 7자리 (2026111) → format_error (Python strptime 허용값 차단)."""
    rec = normalize_bizinfo_record(
        "EVENT",
        _event(eventBeginEndDe="2026111 ~ 20261103"),
        _NOW,
    )
    assert isinstance(rec, NormalizedSourceRecord)
    assert rec.event_period is not None
    assert rec.event_period.parse_note == "format_error"
