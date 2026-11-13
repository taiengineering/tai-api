"""WO-TAI-DOC-SITE-CONTEXT-GUARD-001 — DSC-01 ~ DSC-09.

사업장별 문서 처리 권한 검증 단위 테스트.
FakeSB 사용 — 운영 DB 접근 없음.

DSC-01  ALL  — 회사·사업장 일치 시 허용
DSC-02  ALL  — 사업장이 지정 회사 소속 아니면 차단
DSC-03  COMPANY — 타사 company_id 차단
DSC-04  FACTORY — 다른 사업장 차단
DSC-05  FACTORY — 본인 사업장 허용
DSC-06  FACTORY — 사업장 미배정 차단
DSC-07  권한 조회 실패 시 차단
DSC-08  알 수 없는 권한 차단
DSC-09  기존 총어드민 업로드 경로 불변 확인
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from services.doc_site_context import SiteContextResult, resolve_document_site_context


# ── FakeSB ────────────────────────────────────────────────────────────────────

class _Exec:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, rows_by_table):
        self._rows = rows_by_table
        self._name = None
        self._filters: dict = {}

    def table(self, name):
        t = _FakeTable(self._rows)
        t._name = name
        return t

    def select(self, *a, **k):
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def limit(self, n):
        return self

    def execute(self):
        rows = list(self._rows.get(self._name, []))
        for col, val in self._filters.items():
            rows = [r for r in rows if r.get(col) == val]
        return _Exec(rows)


class _ErrorSB:
    """_scope() 호출 시 예외를 발생시키는 Fake."""
    def table(self, *a):
        raise RuntimeError("DB 연결 실패")


def _sb(scope_type: str, factories: list[dict] | None = None) -> _FakeTable:
    return _FakeTable({
        "role_data_scope": [{"role_code": "RC-TEST", "scope_type": scope_type}],
        "factories": factories or [],
    })


def _user(scope_label: str, company_id="C-OWN", factory_id="F-OWN") -> dict:
    return {"role_code": "RC-TEST", "company_id": company_id, "factory_id": factory_id}


# ── DSC-01 ────────────────────────────────────────────────────────────────────

def test_DSC_01_ALL_matching_factory_allowed():
    """ALL 권한: 사업장이 지정 회사에 소속 → SiteContextResult 반환."""
    sb = _sb("ALL", factories=[{"id": "F-X", "company_id": "C-X"}])
    cur = _user("ALL", company_id="C-OWN", factory_id="F-OWN")

    result = resolve_document_site_context(cur, "C-X", "F-X", sb)

    assert isinstance(result, SiteContextResult)
    assert result.company_id == "C-X"
    assert result.factory_id == "F-X"
    assert result.scope_type == "ALL"


# ── DSC-02 ────────────────────────────────────────────────────────────────────

def test_DSC_02_ALL_factory_wrong_company_blocked():
    """ALL 권한: 사업장이 지정 company_id 소속 아님 → 403."""
    sb = _sb("ALL", factories=[{"id": "F-X", "company_id": "C-OTHER"}])
    cur = _user("ALL")

    with pytest.raises(HTTPException) as exc:
        resolve_document_site_context(cur, "C-X", "F-X", sb)
    assert exc.value.status_code == 403


# ── DSC-03 ────────────────────────────────────────────────────────────────────

def test_DSC_03_COMPANY_other_company_blocked():
    """COMPANY 권한: 타사 company_id 지정 → 403."""
    sb = _sb("COMPANY", factories=[{"id": "F-B", "company_id": "C-OTHER"}])
    cur = _user("COMPANY", company_id="C-OWN")

    with pytest.raises(HTTPException) as exc:
        resolve_document_site_context(cur, "C-OTHER", "F-B", sb)
    assert exc.value.status_code == 403


# ── DSC-04 ────────────────────────────────────────────────────────────────────

def test_DSC_04_FACTORY_different_factory_blocked():
    """FACTORY 권한: 배정된 것과 다른 사업장 → 403."""
    sb = _sb("FACTORY", factories=[{"id": "F-OTHER", "company_id": "C-OWN"}])
    cur = _user("FACTORY", company_id="C-OWN", factory_id="F-OWN")

    with pytest.raises(HTTPException) as exc:
        resolve_document_site_context(cur, "C-OWN", "F-OTHER", sb)
    assert exc.value.status_code == 403


# ── DSC-05 ────────────────────────────────────────────────────────────────────

def test_DSC_05_FACTORY_own_factory_allowed():
    """FACTORY 권한: 본인 배정 사업장 → SiteContextResult 반환."""
    sb = _sb("FACTORY", factories=[{"id": "F-OWN", "company_id": "C-OWN"}])
    cur = _user("FACTORY", company_id="C-OWN", factory_id="F-OWN")

    result = resolve_document_site_context(cur, "C-OWN", "F-OWN", sb)

    assert result.factory_id == "F-OWN"
    assert result.scope_type == "FACTORY"


# ── DSC-06 ────────────────────────────────────────────────────────────────────

def test_DSC_06_FACTORY_no_factory_assigned_blocked():
    """FACTORY 권한: 사업장 미배정(factory_id=None) → 403."""
    sb = _sb("FACTORY")
    cur = {"role_code": "RC-TEST", "company_id": "C-OWN", "factory_id": None}

    with pytest.raises(HTTPException) as exc:
        resolve_document_site_context(cur, "C-OWN", "F-ANY", sb)
    assert exc.value.status_code == 403


# ── DSC-07 ────────────────────────────────────────────────────────────────────

def test_DSC_07_scope_query_failure_blocked():
    """권한 조회(_scope) 실패 → 403 차단."""
    cur = _user("ANY")

    with pytest.raises(HTTPException) as exc:
        resolve_document_site_context(cur, "C-X", "F-X", _ErrorSB())
    assert exc.value.status_code == 403


# ── DSC-08 ────────────────────────────────────────────────────────────────────

def test_DSC_08_unknown_scope_blocked():
    """알 수 없는 scope_type → 403 차단."""
    sb = _sb("UNKNOWN_TIER")
    cur = _user("UNKNOWN")

    with pytest.raises(HTTPException) as exc:
        resolve_document_site_context(cur, "C-X", "F-X", sb)
    assert exc.value.status_code == 403


# ── DSC-09 ────────────────────────────────────────────────────────────────────

def test_DSC_09_existing_admin_upload_route_unchanged():
    """기존 총어드민 업로드 경로 불변 확인.

    document_digitize.py의 _require_admin, _resolve_company_id, digitize_document가
    여전히 존재하고, 새 모듈을 import해도 기존 함수에 영향이 없음을 확인한다.
    """
    import routers.document_digitize as dd

    assert callable(getattr(dd, "_require_admin", None)), "_require_admin 삭제됨"
    assert callable(getattr(dd, "_resolve_company_id", None)), "_resolve_company_id 삭제됨"
    assert callable(getattr(dd, "digitize_document", None)), "digitize_document 삭제됨"

    # 새 모듈 import가 기존 모듈에 영향을 주지 않음
    from services.doc_site_context import resolve_document_site_context as guard
    assert callable(guard)
