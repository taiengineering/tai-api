"""E-1 company_scope 5단 필터 단위 테스트 — DB 없이 FakeSB."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from services.company_scope import (
    DENY,
    _ensure_own_company,
    _tier,
    require_scope_ids,
    scoped_filter,
    scoped_list_company,
)


class _FakeExec:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, rows_by_table):
        self._rows_by_table = rows_by_table
        self._name = None
        self._filters = {}

    def table(self, name):
        t = _FakeTable(self._rows_by_table)
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
        rows = list(self._rows_by_table.get(self._name, []))
        for col, val in self._filters.items():
            rows = [r for r in rows if r.get(col) == val]
        return _FakeExec(rows)


def _sb(role_scope_map, factories=None):
    """role_code → scope_type. factories optional list of {id, company_id}."""
    rows = [
        {"role_code": rc, "scope_type": st}
        for rc, st in role_scope_map.items()
    ]
    return _FakeTable({
        "role_data_scope": rows,
        "factories": factories or [],
    })


COLS_CO = {"company_id"}
COLS_CF = {"company_id", "factory_id"}
COLS_CFT = {"company_id", "factory_id", "team_id"}


def test_tier_reads_role_data_scope():
    sb = _sb({"001": "ALL", "012": "FACTORY", "013": "TEAM"})
    assert _tier(sb, "001") == "ALL"
    assert _tier(sb, "012") == "FACTORY"
    assert _tier(sb, "013") == "TEAM"
    assert _tier(sb, None) == "TEAM"
    assert _tier(sb, "999") == "TEAM"


def test_all_no_filter():
    sb = _sb({"001": "ALL"})
    cur = {"role_code": "001", "company_id": "C1", "factory_id": "F1"}
    assert scoped_filter(cur, sb, COLS_CF) == {}


def test_company_filter():
    sb = _sb({"002": "COMPANY"})
    cur = {"role_code": "002", "company_id": "C1", "factory_id": "F1"}
    assert scoped_filter(cur, sb, COLS_CF) == {"company_id": "C1"}


def test_factory_filter_with_fid():
    sb = _sb({"012": "FACTORY"})
    cur = {"role_code": "012", "company_id": "C1", "factory_id": "F1"}
    assert scoped_filter(cur, sb, COLS_CF) == {"factory_id": "F1", "company_id": "C1"}


def test_factory_deny_without_fid():
    sb = _sb({"012": "FACTORY"})
    cur = {"role_code": "012", "company_id": "C1", "factory_id": None}
    assert scoped_filter(cur, sb, COLS_CF) is DENY


def test_factory_falls_back_to_company_without_factory_col():
    sb = _sb({"012": "FACTORY"})
    cur = {"role_code": "012", "company_id": "C1", "factory_id": "F1"}
    # factory_id 컬럼 없음 → COMPANY 폴백
    assert scoped_filter(cur, sb, COLS_CO) == {"company_id": "C1"}


def test_team_with_team_col():
    sb = _sb({"013": "TEAM"})
    cur = {"role_code": "013", "company_id": "C1", "factory_id": "F1", "team_id": "T1"}
    assert scoped_filter(cur, sb, COLS_CFT) == {"team_id": "T1", "company_id": "C1"}


def test_team_falls_back_to_factory_without_team_col():
    sb = _sb({"013": "TEAM"})
    cur = {"role_code": "013", "company_id": "C1", "factory_id": "F1", "team_id": "T1"}
    assert scoped_filter(cur, sb, COLS_CF) == {"factory_id": "F1", "company_id": "C1"}


def test_scoped_list_company_keeps_factory_as_company():
    """하위호환: scoped_list_company 는 company_id only → FACTORY 도 COMPANY."""
    sb = _sb({"012": "FACTORY"})
    cur = {"role_code": "012", "company_id": "C1", "factory_id": "F1"}
    cid, deny = scoped_list_company(cur, sb, None)
    assert deny is False
    assert cid == "C1"


def test_ensure_own_company_factory_mismatch():
    sb = _sb({"012": "FACTORY"})
    cur = {"role_code": "012", "company_id": "C1", "factory_id": "F1"}
    _ensure_own_company("C1", cur, sb, "nf", resource_factory_id="F1")  # ok
    with pytest.raises(HTTPException) as ei:
        _ensure_own_company("C1", cur, sb, "nf", resource_factory_id="F2")
    assert ei.value.status_code == 404


def test_require_scope_ids_factory():
    sb = _sb({"012": "FACTORY"})
    cur = {"role_code": "012", "company_id": "C1", "factory_id": "F1"}
    assert require_scope_ids(cur, sb, COLS_CF) == {
        "company_id": "C1",
        "factory_id": "F1",
    }
    cur2 = {"role_code": "012", "company_id": "C1", "factory_id": None}
    with pytest.raises(HTTPException) as ei:
        require_scope_ids(cur2, sb, COLS_CF)
    assert ei.value.status_code == 403
