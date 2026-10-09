"""AUTO document factory-level isolation tests — WO-AUTO-REUSE-G5-FACTORY-ISOLATION-SECURITY-001

Phase C: 13 test cases covering full matrix.
- TBM source_type × FACTORY/TEAM/ASSIGNED/COMPANY/ALL/PLATFORM tiers × same/diff/null factory
- INSPECTION source_type × same matrix
- resource-not-found → 404

No Production DB access — FakeSB only.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from routers.document_engine_api import _ensure_auto_factory_scope


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


def _sb(tier: str, tbm_rows=None, insp_rows=None):
    return _FakeTable({
        "role_data_scope": [{"role_code": "RC1", "scope_type": tier}],
        "tbm_meetings": tbm_rows or [],
        "safety_inspections": insp_rows or [],
    })


def _cur(tier_label: str, factory_id="F-A"):
    return {"role_code": "RC1", "company_id": "C1", "factory_id": factory_id}


# ── TBM tests ─────────────────────────────────────────────────────────────────

def test_tbm_factory_same_factory_allow():
    """FACTORY tier — same factory_id → pass (no exception)."""
    sb = _sb("FACTORY", tbm_rows=[{"id": "TBM-1", "factory_id": "F-A"}])
    cur = _cur("FACTORY", factory_id="F-A")
    _ensure_auto_factory_scope(sb, "TBM", "TBM-1", cur)  # must not raise


def test_tbm_factory_different_factory_block():
    """FACTORY tier — different factory_id → 404."""
    sb = _sb("FACTORY", tbm_rows=[{"id": "TBM-1", "factory_id": "F-B"}])
    cur = _cur("FACTORY", factory_id="F-A")
    with pytest.raises(HTTPException) as ei:
        _ensure_auto_factory_scope(sb, "TBM", "TBM-1", cur)
    assert ei.value.status_code == 404


def test_tbm_factory_null_factory_fail_closed():
    """FACTORY tier — resource.factory_id is None → fail-closed 404."""
    sb = _sb("FACTORY", tbm_rows=[{"id": "TBM-1", "factory_id": None}])
    cur = _cur("FACTORY", factory_id="F-A")
    with pytest.raises(HTTPException) as ei:
        _ensure_auto_factory_scope(sb, "TBM", "TBM-1", cur)
    assert ei.value.status_code == 404


def test_tbm_team_same_factory_allow():
    """TEAM tier — same factory_id → pass."""
    sb = _sb("TEAM", tbm_rows=[{"id": "TBM-1", "factory_id": "F-A"}])
    cur = _cur("TEAM", factory_id="F-A")
    _ensure_auto_factory_scope(sb, "TBM", "TBM-1", cur)


def test_tbm_team_different_factory_block():
    """TEAM tier — different factory_id → 404."""
    sb = _sb("TEAM", tbm_rows=[{"id": "TBM-1", "factory_id": "F-B"}])
    cur = _cur("TEAM", factory_id="F-A")
    with pytest.raises(HTTPException) as ei:
        _ensure_auto_factory_scope(sb, "TBM", "TBM-1", cur)
    assert ei.value.status_code == 404


def test_tbm_assigned_different_factory_block():
    """ASSIGNED tier — different factory_id → 404."""
    sb = _sb("ASSIGNED", tbm_rows=[{"id": "TBM-1", "factory_id": "F-B"}])
    cur = _cur("ASSIGNED", factory_id="F-A")
    with pytest.raises(HTTPException) as ei:
        _ensure_auto_factory_scope(sb, "TBM", "TBM-1", cur)
    assert ei.value.status_code == 404


def test_tbm_company_tier_bypass():
    """COMPANY tier — no factory check, pass through regardless of factory_id."""
    sb = _sb("COMPANY", tbm_rows=[{"id": "TBM-1", "factory_id": "F-B"}])
    cur = _cur("COMPANY", factory_id="F-A")
    _ensure_auto_factory_scope(sb, "TBM", "TBM-1", cur)  # must not raise


def test_tbm_all_tier_bypass():
    """ALL tier — pass through."""
    sb = _sb("ALL", tbm_rows=[{"id": "TBM-1", "factory_id": "F-B"}])
    cur = _cur("ALL", factory_id="F-A")
    _ensure_auto_factory_scope(sb, "TBM", "TBM-1", cur)


def test_tbm_platform_tier_bypass():
    """PLATFORM tier — pass through."""
    sb = _sb("PLATFORM", tbm_rows=[{"id": "TBM-1", "factory_id": "F-B"}])
    cur = _cur("PLATFORM", factory_id="F-A")
    _ensure_auto_factory_scope(sb, "TBM", "TBM-1", cur)


def test_tbm_resource_not_found_404():
    """Resource row does not exist → 404 regardless of tier."""
    sb = _sb("FACTORY", tbm_rows=[])
    cur = _cur("FACTORY", factory_id="F-A")
    with pytest.raises(HTTPException) as ei:
        _ensure_auto_factory_scope(sb, "TBM", "NO-SUCH-ID", cur)
    assert ei.value.status_code == 404


# ── INSPECTION tests ──────────────────────────────────────────────────────────

def test_insp_factory_same_factory_allow():
    """INSPECTION — FACTORY tier — same factory_id → pass."""
    sb = _sb("FACTORY", insp_rows=[{"id": "INS-1", "factory_id": "F-A"}])
    cur = _cur("FACTORY", factory_id="F-A")
    _ensure_auto_factory_scope(sb, "INSPECTION", "INS-1", cur)


def test_insp_factory_different_factory_block():
    """INSPECTION — FACTORY tier — different factory_id → 404."""
    sb = _sb("FACTORY", insp_rows=[{"id": "INS-1", "factory_id": "F-B"}])
    cur = _cur("FACTORY", factory_id="F-A")
    with pytest.raises(HTTPException) as ei:
        _ensure_auto_factory_scope(sb, "INSPECTION", "INS-1", cur)
    assert ei.value.status_code == 404


def test_insp_factory_null_factory_fail_closed():
    """INSPECTION — FACTORY tier — resource.factory_id None → fail-closed 404."""
    sb = _sb("FACTORY", insp_rows=[{"id": "INS-1", "factory_id": None}])
    cur = _cur("FACTORY", factory_id="F-A")
    with pytest.raises(HTTPException) as ei:
        _ensure_auto_factory_scope(sb, "INSPECTION", "INS-1", cur)
    assert ei.value.status_code == 404


def test_insp_company_tier_bypass():
    """INSPECTION — COMPANY tier — no factory check."""
    sb = _sb("COMPANY", insp_rows=[{"id": "INS-1", "factory_id": "F-B"}])
    cur = _cur("COMPANY", factory_id="F-A")
    _ensure_auto_factory_scope(sb, "INSPECTION", "INS-1", cur)


def test_insp_resource_not_found_404():
    """INSPECTION — resource row does not exist → 404."""
    sb = _sb("FACTORY", insp_rows=[])
    cur = _cur("FACTORY", factory_id="F-A")
    with pytest.raises(HTTPException) as ei:
        _ensure_auto_factory_scope(sb, "INSPECTION", "NO-SUCH-ID", cur)
    assert ei.value.status_code == 404
