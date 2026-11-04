"""tests/test_bizinfo_supabase_repository.py — SupabaseBizinfoRepository 계약 테스트.

STORAGE_GATE OBJ-BZI-004/005 — Supabase 구현 단위 검증.

Production DB 호출 = 0 (mock 전용).

커버리지:
  SR-01  get_prior_record — 존재하는 PROGRAM 반환
  SR-02  get_prior_record — 존재하지 않는 key → None
  SR-03  save_record — UPSERT 호출 확인 (변경 추적 포함)
  SR-04  get_editorial — 존재하는 행 반환
  SR-05  get_editorial — 행 없음 → None
  SR-06  get_editorial — authored_at NULL → None
  SR-07  get_rights — rights_basis 있음 → RightsRecord
  SR-08  get_rights — rights_basis NULL → None
  SR-09  get_approval — approved_at 있음 → ContentApprovalRecord
  SR-10  get_approval — approved_at NULL → None
  SR-11  get_relevance_verdict — 판정값 반환
  SR-12  get_relevance_verdict — 행 없음 → None
  SR-13  list_eligible_keys — approved_at 있는 행만 반환 (PROGRAM)
  SR-14  list_eligible_keys — EVENT 필터링
  SR-15  list_eligible_keys — 빈 결과 → []
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from services.bizinfo.supabase_repository import SupabaseBizinfoRepository
from services.bizinfo.normalizer import DateRange, NormalizedSourceRecord
from services.bizinfo.approval import (
    ContentApprovalRecord,
    EditorialContent,
    RightsRecord,
)
from services.bizinfo.status import ChangeRecord


# ---------------------------------------------------------------------------
# Mock helpers — PostgREST 체인 시뮬레이터
# ---------------------------------------------------------------------------

class _Q:
    """PostgREST 쿼리 빌더 최소 모의 객체."""

    def __init__(self, rows: list[dict] | None = None):
        self._rows: list[dict] = rows or []
        self.last_upsert: Optional[dict] = None

    def select(self, *a, **k):   return self
    def eq(self, *a, **k):       return self
    def not_(self):              return self
    def is_(self, *a, **k):      return self
    def limit(self, *a, **k):    return self
    def order(self, *a, **k):    return self
    def range(self, *a, **k):    return self

    def upsert(self, row, **k):
        self.last_upsert = row
        return self

    def execute(self):
        return type("R", (), {"data": list(self._rows)})()


class _Q_not:
    """not_ 체이닝 지원 — .not_.is_() 호출 처리."""

    def __init__(self, q: _Q):
        self._q = q

    def is_(self, *a, **k):
        return self._q


class _Supabase:
    """table() 호출을 테이블 이름 → _Q 로 라우팅한다."""

    def __init__(self, tables: dict[str, _Q]):
        self._tables = tables

    def table(self, name: str) -> _Q:
        q = self._tables.get(name, _Q())
        q.not_ = _Q_not(q)
        return q


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime(2026, 11, 4, 12, 0, 0, tzinfo=timezone.utc)


def _src_row(**overrides) -> dict:
    base = {
        "source_kind":        "PROGRAM",
        "source_key":         "PBLN_TEST_001",
        "title":              "테스트 지원사업",
        "source_org":         "테스트 기관",
        "origin_url":         None,
        "bizinfo_url":        "https://www.bizinfo.go.kr/web/lay1/program/PBLN_TEST_001",
        "retrieved_at":       "2026-11-04T12:00:00+00:00",
        "source_updated_at":  None,
        "summary":            None,
        "support_target":     "50인 미만 사업장",
        "hashtags":           ["안전", "지원"],
        "parse_errors":       [],
        "evidence_pending":   [],
        "application_start":  "2026-10-01",
        "application_end":    "2026-12-31",
        "event_start":        None,
        "event_end":          None,
        "reception_start":    None,
        "reception_end":      None,
        "relevance_verdict":  "INCLUDE",
        "change_verdict":     "CHANGE_UNKNOWN",
        "changed_fields":     [],
    }
    base.update(overrides)
    return base


def _edit_row(**overrides) -> dict:
    base = {
        "source_kind":          "PROGRAM",
        "source_key":           "PBLN_TEST_001",
        "explanation":          "TAI 해설 텍스트",
        "guidance":             "실무 안내 텍스트",
        "authored_at":          "2026-11-04T10:00:00+00:00",
        "tai_link":             "/safety-search",
        "rights_basis":         "공공저작물 자유이용허락 (KOGL 제1유형)",
        "rights_confirmed_at":  "2026-11-04T10:00:00+00:00",
        "rights_confirmed_by":  "reviewer-01",
        "approved_at":          "2026-11-04T11:00:00+00:00",
        "approved_by":          "approver-01",
    }
    base.update(overrides)
    return base


def _make_record() -> NormalizedSourceRecord:
    return NormalizedSourceRecord(
        source_kind="PROGRAM",
        source_id="BIZINFO_PROGRAM",
        source_key="PBLN_TEST_001",
        title="테스트 지원사업",
        source_org="테스트 기관",
        origin_url=None,
        bizinfo_url="https://www.bizinfo.go.kr/web/lay1/program/PBLN_TEST_001",
        retrieved_at=_now(),
        support_target="50인 미만 사업장",
        application_period=DateRange(
            start=date(2026, 10, 1),
            end=date(2026, 12, 31),
        ),
    )


def _make_change() -> ChangeRecord:
    return ChangeRecord(
        source_key="PBLN_TEST_001",
        source_kind="PROGRAM",
        verdict="NO_CHANGE",
        changed_fields=(),
        checked_at=_now(),
        source_updated_at=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_SR01_get_prior_record_found():
    sb = _Supabase({"bizinfo_source_records": _Q([_src_row()])})
    repo = SupabaseBizinfoRepository(sb)
    result = repo.get_prior_record("PROGRAM", "PBLN_TEST_001")
    assert result is not None
    assert result.source_key == "PBLN_TEST_001"
    assert result.source_kind == "PROGRAM"
    assert result.title == "테스트 지원사업"
    assert result.support_target == "50인 미만 사업장"
    ap = result.application_period
    assert ap is not None
    assert ap.start == date(2026, 10, 1)
    assert ap.end == date(2026, 12, 31)


def test_SR02_get_prior_record_not_found():
    sb = _Supabase({"bizinfo_source_records": _Q([])})
    repo = SupabaseBizinfoRepository(sb)
    result = repo.get_prior_record("PROGRAM", "DOES_NOT_EXIST")
    assert result is None


def test_SR03_save_record_calls_upsert():
    q = _Q([])
    sb = _Supabase({"bizinfo_source_records": q})
    repo = SupabaseBizinfoRepository(sb)
    record = _make_record()
    change = _make_change()
    repo.save_record(record, change)
    assert q.last_upsert is not None
    assert q.last_upsert["source_kind"] == "PROGRAM"
    assert q.last_upsert["source_key"] == "PBLN_TEST_001"
    assert q.last_upsert["title"] == "테스트 지원사업"
    assert q.last_upsert["application_start"] == "2026-10-01"
    assert q.last_upsert["application_end"] == "2026-12-31"
    assert q.last_upsert["change_verdict"] == "NO_CHANGE"


def test_SR04_get_editorial_found():
    sb = _Supabase({"bizinfo_editorial_content": _Q([_edit_row()])})
    repo = SupabaseBizinfoRepository(sb)
    result = repo.get_editorial("PROGRAM", "PBLN_TEST_001")
    assert result is not None
    assert isinstance(result, EditorialContent)
    assert result.source_key == "PBLN_TEST_001"
    assert result.explanation == "TAI 해설 텍스트"
    assert result.guidance == "실무 안내 텍스트"
    assert result.tai_link == "/safety-search"


def test_SR05_get_editorial_not_found():
    sb = _Supabase({"bizinfo_editorial_content": _Q([])})
    repo = SupabaseBizinfoRepository(sb)
    result = repo.get_editorial("PROGRAM", "PBLN_TEST_001")
    assert result is None


def test_SR06_get_editorial_authored_at_null_returns_none():
    sb = _Supabase({"bizinfo_editorial_content": _Q([_edit_row(authored_at=None)])})
    repo = SupabaseBizinfoRepository(sb)
    result = repo.get_editorial("PROGRAM", "PBLN_TEST_001")
    assert result is None


def test_SR07_get_rights_found():
    sb = _Supabase({"bizinfo_editorial_content": _Q([_edit_row()])})
    repo = SupabaseBizinfoRepository(sb)
    result = repo.get_rights("PROGRAM", "PBLN_TEST_001")
    assert result is not None
    assert isinstance(result, RightsRecord)
    assert result.source_key == "PBLN_TEST_001"
    assert "KOGL" in result.rights_basis
    assert result.confirmed_by == "reviewer-01"


def test_SR08_get_rights_basis_null_returns_none():
    sb = _Supabase({"bizinfo_editorial_content": _Q([_edit_row(rights_basis=None)])})
    repo = SupabaseBizinfoRepository(sb)
    result = repo.get_rights("PROGRAM", "PBLN_TEST_001")
    assert result is None


def test_SR09_get_approval_found():
    sb = _Supabase({"bizinfo_editorial_content": _Q([_edit_row()])})
    repo = SupabaseBizinfoRepository(sb)
    result = repo.get_approval("PROGRAM", "PBLN_TEST_001")
    assert result is not None
    assert isinstance(result, ContentApprovalRecord)
    assert result.source_key == "PBLN_TEST_001"
    assert result.source_kind == "PROGRAM"
    assert result.approved_by == "approver-01"


def test_SR10_get_approval_approved_at_null_returns_none():
    sb = _Supabase({"bizinfo_editorial_content": _Q([_edit_row(approved_at=None)])})
    repo = SupabaseBizinfoRepository(sb)
    result = repo.get_approval("PROGRAM", "PBLN_TEST_001")
    assert result is None


def test_SR11_get_relevance_verdict_found():
    sb = _Supabase({"bizinfo_source_records": _Q([_src_row(relevance_verdict="INCLUDE")])})
    repo = SupabaseBizinfoRepository(sb)
    result = repo.get_relevance_verdict("PROGRAM", "PBLN_TEST_001")
    assert result == "INCLUDE"


def test_SR12_get_relevance_verdict_not_found():
    sb = _Supabase({"bizinfo_source_records": _Q([])})
    repo = SupabaseBizinfoRepository(sb)
    result = repo.get_relevance_verdict("PROGRAM", "DOES_NOT_EXIST")
    assert result is None


def test_SR13_list_eligible_keys_program():
    rows = [
        {"source_key": "PBLN_001"},
        {"source_key": "PBLN_002"},
    ]
    sb = _Supabase({"bizinfo_editorial_content": _Q(rows)})
    repo = SupabaseBizinfoRepository(sb)
    result = repo.list_eligible_keys("PROGRAM", limit=10, offset=0)
    assert result == ["PBLN_001", "PBLN_002"]


def test_SR14_list_eligible_keys_event():
    rows = [{"source_key": "EVEN_001"}]
    sb = _Supabase({"bizinfo_editorial_content": _Q(rows)})
    repo = SupabaseBizinfoRepository(sb)
    result = repo.list_eligible_keys("EVENT", limit=10, offset=0)
    assert result == ["EVEN_001"]


def test_SR15_list_eligible_keys_empty():
    sb = _Supabase({"bizinfo_editorial_content": _Q([])})
    repo = SupabaseBizinfoRepository(sb)
    result = repo.list_eligible_keys("PROGRAM")
    assert result == []


# ---------------------------------------------------------------------------
# R1 보정 테스트
# ---------------------------------------------------------------------------


def test_SR16_save_relevance_verdict_calls_update():
    """save_relevance_verdict가 UPDATE를 호출하고 verdict 값을 전달한다."""
    q = _Q([])
    # update() 호출 추적을 위해 _Q에 last_update 추가
    q.last_update = None

    class _QWithUpdate(_Q):
        def update(self, data, **k):
            self.last_update = data
            return self

    q2 = _QWithUpdate([])
    sb = _Supabase({"bizinfo_source_records": q2})
    repo = SupabaseBizinfoRepository(sb)
    repo.save_relevance_verdict("PROGRAM", "PBLN_TEST_001", "INCLUDE")
    assert q2.last_update is not None
    assert q2.last_update["relevance_verdict"] == "INCLUDE"
    assert "updated_at" in q2.last_update


def test_SR17_updated_at_is_real_timestamp_not_string_function():
    """save_record의 updated_at이 ISO 타임스탬프 문자열이다 — 'now()' 금지."""
    q = _Q([])
    sb = _Supabase({"bizinfo_source_records": q})
    repo = SupabaseBizinfoRepository(sb)
    repo.save_record(_make_record(), _make_change())
    assert q.last_upsert is not None
    updated_at = q.last_upsert.get("updated_at")
    assert updated_at != "now()", "updated_at은 SQL 함수 문자열이 아닌 실제 타임스탬프여야 한다"
    # ISO 형식 검증 (datetime.fromisoformat으로 파싱 가능해야 함)
    from datetime import datetime
    parsed = datetime.fromisoformat(updated_at)
    assert parsed is not None


def test_SR18_bizinfo_storage_enabled_zero_does_not_activate(monkeypatch):
    """BIZINFO_STORAGE_ENABLED=0은 비활성 — 정확히 '1'일 때만 활성화."""
    monkeypatch.setenv("BIZINFO_STORAGE_ENABLED", "0")
    from routers.bizinfo_public import _build_repository
    result = _build_repository()
    assert result is None


def test_SR19_bizinfo_storage_enabled_empty_string_does_not_activate(monkeypatch):
    """BIZINFO_STORAGE_ENABLED='' (빈 문자열)은 비활성."""
    monkeypatch.setenv("BIZINFO_STORAGE_ENABLED", "")
    from routers.bizinfo_public import _build_repository
    result = _build_repository()
    assert result is None
