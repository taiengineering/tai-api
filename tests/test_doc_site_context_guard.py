"""WO-TAI-DOC-SITE-CONTEXT-GUARD-001-R1 — DSC-01 ~ DSC-09, DSC-R1-01 ~ DSC-R1-06.

사업장별 문서 처리 권한 검증 단위 테스트.
FakeSB 사용 — 운영 DB 접근 없음.

DSC-01    ALL  — 회사·사업장 일치 시 허용
DSC-02    ALL  — 사업장이 지정 회사 소속 아니면 차단
DSC-03    COMPANY — 타사 company_id 차단
DSC-04    FACTORY — 다른 사업장 차단
DSC-05    FACTORY — 본인 사업장 허용 (R1-02: DB 소속 확인 포함)
DSC-06    FACTORY — 사업장 미배정 차단
DSC-07    권한 조회(_strict_scope) DB 오류 시 차단
DSC-08    알 수 없는 권한 차단
DSC-09    기존 총어드민 업로드 경로 불변 확인

DSC-R1-01 권한 조회 DB 오류, 회사·사업장 요청값이 사용자 정보와 일치해도 차단
DSC-R1-02 role_code 누락 또는 미등록 → 차단
DSC-R1-03 FACTORY 사용자 사업장 ID 일치, 실제 DB에 사업장 없음 → 차단
DSC-R1-04 FACTORY 사용자 사업장 ID 일치, 실제 DB 소속 회사 다름 → 차단
DSC-R1-05 TEAM 사용자 사업장 ID 일치, 실제 DB 소속 회사 다름 → 차단
DSC-R1-06 FACTORY·TEAM 정상 소속 (DB 확인 포함) → 허용
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


class _AllTablesErrorSB:
    """모든 테이블 접근 시 예외를 발생시키는 Fake."""
    def table(self, *a):
        raise RuntimeError("DB 연결 실패")


class _ScopeQueryErrorSB:
    """role_data_scope 조회 시에만 예외. factories는 정상 처리."""
    def __init__(self, factories=None):
        self._factories = factories or []

    def table(self, name):
        if name == "role_data_scope":
            raise RuntimeError("role_data_scope DB 오류")
        return _FakeTable({"factories": self._factories}).table(name)


def _sb(scope_type: str, factories: list[dict] | None = None) -> _FakeTable:
    return _FakeTable({
        "role_data_scope": [{"role_code": "RC-TEST", "scope_type": scope_type}],
        "factories": factories or [],
    })


def _user(scope_label: str = "", company_id="C-OWN", factory_id="F-OWN") -> dict:
    return {"role_code": "RC-TEST", "company_id": company_id, "factory_id": factory_id}


# ── DSC-01 ────────────────────────────────────────────────────────────────────

def test_DSC_01_ALL_matching_factory_allowed():
    """ALL 권한: 사업장이 지정 회사에 소속 → SiteContextResult 반환."""
    sb = _sb("ALL", factories=[{"id": "F-X", "company_id": "C-X"}])
    cur = _user(company_id="C-OWN", factory_id="F-OWN")

    result = resolve_document_site_context(cur, "C-X", "F-X", sb)

    assert isinstance(result, SiteContextResult)
    assert result.company_id == "C-X"
    assert result.factory_id == "F-X"
    assert result.scope_type == "ALL"


# ── DSC-02 ────────────────────────────────────────────────────────────────────

def test_DSC_02_ALL_factory_wrong_company_blocked():
    """ALL 권한: 사업장이 지정 company_id 소속 아님 → 403."""
    sb = _sb("ALL", factories=[{"id": "F-X", "company_id": "C-OTHER"}])
    cur = _user()

    with pytest.raises(HTTPException) as exc:
        resolve_document_site_context(cur, "C-X", "F-X", sb)
    assert exc.value.status_code == 403


# ── DSC-03 ────────────────────────────────────────────────────────────────────

def test_DSC_03_COMPANY_other_company_blocked():
    """COMPANY 권한: 타사 company_id 지정 → 403."""
    sb = _sb("COMPANY", factories=[{"id": "F-B", "company_id": "C-OTHER"}])
    cur = _user(company_id="C-OWN")

    with pytest.raises(HTTPException) as exc:
        resolve_document_site_context(cur, "C-OTHER", "F-B", sb)
    assert exc.value.status_code == 403


# ── DSC-04 ────────────────────────────────────────────────────────────────────

def test_DSC_04_FACTORY_different_factory_blocked():
    """FACTORY 권한: 배정된 것과 다른 사업장 → 403."""
    sb = _sb("FACTORY", factories=[{"id": "F-OTHER", "company_id": "C-OWN"}])
    cur = _user(company_id="C-OWN", factory_id="F-OWN")

    with pytest.raises(HTTPException) as exc:
        resolve_document_site_context(cur, "C-OWN", "F-OTHER", sb)
    assert exc.value.status_code == 403


# ── DSC-05 ────────────────────────────────────────────────────────────────────

def test_DSC_05_FACTORY_own_factory_allowed():
    """FACTORY 권한: 본인 배정 사업장 + DB 소속 일치 → SiteContextResult 반환."""
    sb = _sb("FACTORY", factories=[{"id": "F-OWN", "company_id": "C-OWN"}])
    cur = _user(company_id="C-OWN", factory_id="F-OWN")

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
    """_strict_scope: DB 연결 실패(모든 테이블) → 403 차단."""
    cur = _user()

    with pytest.raises(HTTPException) as exc:
        resolve_document_site_context(cur, "C-X", "F-X", _AllTablesErrorSB())
    assert exc.value.status_code == 403


# ── DSC-08 ────────────────────────────────────────────────────────────────────

def test_DSC_08_unknown_scope_blocked():
    """알 수 없는 scope_type → 403 차단."""
    sb = _sb("UNKNOWN_TIER")
    cur = _user()

    with pytest.raises(HTTPException) as exc:
        resolve_document_site_context(cur, "C-X", "F-X", sb)
    assert exc.value.status_code == 403


# ── DSC-09 ────────────────────────────────────────────────────────────────────

def test_DSC_09_existing_admin_upload_route_unchanged():
    """관리자(role_code=001) 업로드 경로 불변 확인.

    Gate D 이후 _require_admin() 제거됨 — 대신 is_admin 인라인 판별 사용.
    핵심 함수·라우트·guard 연결이 유지됨을 확인한다.
    실제 HTTP 요청 회귀 검증은 아님 (GD-07 커버).
    """
    import routers.document_digitize as dd

    assert callable(getattr(dd, "_resolve_company_id", None)), "_resolve_company_id 삭제됨"
    assert callable(getattr(dd, "digitize_document", None)), "digitize_document 삭제됨"
    assert callable(getattr(dd, "get_digitize_result", None)), "get_digitize_result 삭제됨"

    from services.doc_site_context import resolve_document_site_context as guard
    assert callable(guard)


# ── DSC-R1-01 ────────────────────────────────────────────────────────────────

def test_DSC_R1_01_scope_db_error_matching_credentials_blocked():
    """R1-01: role_data_scope DB 오류 — 회사·사업장이 사용자와 일치해도 차단.

    구 코드에서는 _scope()가 'TEAM'을 반환하여 접근이 허용됐음.
    _strict_scope()는 DB 오류 시 403을 발생시켜 반드시 차단한다.
    """
    factories = [{"id": "F-OWN", "company_id": "C-OWN"}]
    sb = _ScopeQueryErrorSB(factories=factories)
    cur = _user(company_id="C-OWN", factory_id="F-OWN")

    with pytest.raises(HTTPException) as exc:
        resolve_document_site_context(cur, "C-OWN", "F-OWN", sb)
    assert exc.value.status_code == 403


# ── DSC-R1-02 ────────────────────────────────────────────────────────────────

def test_DSC_R1_02_missing_or_unregistered_role_blocked():
    """R1-01: role_code 누락 또는 role_data_scope 미등록 → 403."""
    sb = _sb("FACTORY", factories=[{"id": "F-OWN", "company_id": "C-OWN"}])

    # role_code=None
    cur_none = {"role_code": None, "company_id": "C-OWN", "factory_id": "F-OWN"}
    with pytest.raises(HTTPException) as exc_none:
        resolve_document_site_context(cur_none, "C-OWN", "F-OWN", sb)
    assert exc_none.value.status_code == 403

    # role_code가 role_data_scope에 없음
    cur_unreg = {"role_code": "RC-UNREGISTERED", "company_id": "C-OWN", "factory_id": "F-OWN"}
    with pytest.raises(HTTPException) as exc_unreg:
        resolve_document_site_context(cur_unreg, "C-OWN", "F-OWN", sb)
    assert exc_unreg.value.status_code == 403


# ── DSC-R1-03 ────────────────────────────────────────────────────────────────

def test_DSC_R1_03_FACTORY_factory_not_in_db_blocked():
    """R1-02: FACTORY 사용자 사업장 ID 일치, 실제 DB에 사업장 없음 → 차단."""
    sb = _sb("FACTORY", factories=[])  # factories 테이블 비어 있음
    cur = _user(company_id="C-OWN", factory_id="F-OWN")

    with pytest.raises(HTTPException) as exc:
        resolve_document_site_context(cur, "C-OWN", "F-OWN", sb)
    # _ensure_factory_company_match: 사업장 없음 → 404
    assert exc.value.status_code in {403, 404}


# ── DSC-R1-04 ────────────────────────────────────────────────────────────────

def test_DSC_R1_04_FACTORY_factory_wrong_company_blocked():
    """R1-02: FACTORY 사용자 사업장 ID 일치, DB 소속 회사 다름 → 403."""
    sb = _sb("FACTORY", factories=[{"id": "F-OWN", "company_id": "C-OTHER"}])
    cur = _user(company_id="C-OWN", factory_id="F-OWN")

    with pytest.raises(HTTPException) as exc:
        resolve_document_site_context(cur, "C-OWN", "F-OWN", sb)
    assert exc.value.status_code == 403


# ── DSC-R1-05 ────────────────────────────────────────────────────────────────

def test_DSC_R1_05_TEAM_factory_wrong_company_blocked():
    """R1-02: TEAM 사용자 사업장 ID 일치, DB 소속 회사 다름 → 403."""
    sb = _sb("TEAM", factories=[{"id": "F-OWN", "company_id": "C-OTHER"}])
    cur = _user(company_id="C-OWN", factory_id="F-OWN")

    with pytest.raises(HTTPException) as exc:
        resolve_document_site_context(cur, "C-OWN", "F-OWN", sb)
    assert exc.value.status_code == 403


# ── DSC-R1-06 ────────────────────────────────────────────────────────────────

def test_DSC_R1_06_FACTORY_TEAM_db_verified_allowed():
    """R1-02: FACTORY·TEAM 사용자 — DB 소속 관계 확인 후 정상 허용."""
    for scope_label in ("FACTORY", "TEAM"):
        sb = _sb(scope_label, factories=[{"id": "F-OWN", "company_id": "C-OWN"}])
        cur = _user(company_id="C-OWN", factory_id="F-OWN")

        result = resolve_document_site_context(cur, "C-OWN", "F-OWN", sb)

        assert result.company_id == "C-OWN"
        assert result.factory_id == "F-OWN"
        assert result.scope_type == scope_label
