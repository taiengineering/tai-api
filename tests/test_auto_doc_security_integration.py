"""AUTO document security integration tests — WO-AUTO-REUSE-G5-FACTORY-ISOLATION-SECURITY-002

Tests call actual endpoint functions with _ensure_auto_factory_scope live (NOT mocked).
Company/owner guards and status checks may be mocked since they are tested separately.

ASSIGNED policy finding (services/company_scope.py L151-168):
  ASSIGNED is an E-3 stub. With factory_id column present in scoped_filter, ASSIGNED
  acts like FACTORY (requires factory_id match). In _ensure_own_company it receives
  only company-level check (not in FACTORY/TEAM branch). For AUTO docs (safety-critical),
  treating ASSIGNED with factory_id match (same as FACTORY) is consistent with list
  scope behaviour and more secure than _ensure_own_company. No policy conflict.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from routers.document_engine_api import auto_document_pdf, auto_document_preview


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


def _make_sb(tier: str, tbm_fid="F-A", insp_fid="F-A", *, tbm_missing=False, insp_missing=False):
    tbm_rows = [] if tbm_missing else [{"id": "TBM-1", "factory_id": tbm_fid}]
    insp_rows = [] if insp_missing else [{"id": "INS-1", "factory_id": insp_fid}]
    return _FakeTable({
        "role_data_scope": [{"role_code": "RC1", "scope_type": tier}],
        "tbm_meetings": tbm_rows,
        "safety_inspections": insp_rows,
    })


def _cur(factory_id="F-A"):
    return {"role_code": "RC1", "company_id": "C1", "factory_id": factory_id}


def _noop(*a, **k):
    pass


_NOOP_PATCHES = [
    "routers.document_engine_api._ensure_tbm_own",
    "routers.document_engine_api._ensure_inspection_own",
    "routers.document_engine_api._require_auto_tbm_ready",
    "routers.document_engine_api._require_auto_inspection_ready",
]


# ── INSPECTION Preview ────────────────────────────────────────────────────────

def test_SI1_insp_preview_cross_factory_404_render_not_called():
    """FACTORY user → different factory INSPECTION Preview → 404, render never called."""
    sb = _make_sb("FACTORY", insp_fid="F-A")  # resource is F-A
    cur = _cur(factory_id="F-B")              # user is F-B

    with patch("routers.document_engine_api._render_html", new_callable=AsyncMock) as rdr:
        with patch("routers.document_engine_api.get_supabase", return_value=sb):
            for p in _NOOP_PATCHES:
                patch(p, side_effect=_noop).start()
            with pytest.raises(HTTPException) as ei:
                asyncio.run(auto_document_preview("INSPECTION", "INS-1", cur))
            assert ei.value.status_code == 404
            rdr.assert_not_called()
    patch.stopall()


def test_SI2_insp_preview_same_factory_render_called():
    """FACTORY user → same factory INSPECTION Preview → render called."""
    sb = _make_sb("FACTORY", insp_fid="F-A")
    cur = _cur(factory_id="F-A")

    with patch("routers.document_engine_api._render_html", new_callable=AsyncMock, return_value="<html>") as rdr:
        with patch("routers.document_engine_api.get_supabase", return_value=sb):
            for p in _NOOP_PATCHES:
                patch(p, side_effect=_noop).start()
            asyncio.run(auto_document_preview("INSPECTION", "INS-1", cur))
            rdr.assert_called_once()
    patch.stopall()


# ── INSPECTION PDF ────────────────────────────────────────────────────────────

def test_SI3_insp_pdf_cross_factory_404_render_not_called():
    """FACTORY user → different factory INSPECTION PDF → 404, render never called."""
    sb = _make_sb("FACTORY", insp_fid="F-A")
    cur = _cur(factory_id="F-B")

    with patch("routers.document_engine_api._render_pdf", new_callable=AsyncMock) as rdr:
        with patch("routers.document_engine_api.get_supabase", return_value=sb):
            for p in _NOOP_PATCHES:
                patch(p, side_effect=_noop).start()
            with pytest.raises(HTTPException) as ei:
                asyncio.run(auto_document_pdf("INSPECTION", "INS-1", cur))
            assert ei.value.status_code == 404
            rdr.assert_not_called()
    patch.stopall()


def test_SI4_insp_pdf_same_factory_render_called():
    """FACTORY user → same factory INSPECTION PDF → render called."""
    sb = _make_sb("FACTORY", insp_fid="F-A")
    cur = _cur(factory_id="F-A")

    with patch("routers.document_engine_api._render_pdf", new_callable=AsyncMock, return_value=b"%PDF") as rdr:
        with patch("routers.document_engine_api.get_supabase", return_value=sb):
            for p in _NOOP_PATCHES:
                patch(p, side_effect=_noop).start()
            asyncio.run(auto_document_pdf("INSPECTION", "INS-1", cur))
            rdr.assert_called_once()
    patch.stopall()


# ── TBM Preview ───────────────────────────────────────────────────────────────

def test_ST1_tbm_preview_cross_factory_404_render_not_called():
    """FACTORY user → different factory TBM Preview → 404, render never called."""
    sb = _make_sb("FACTORY", tbm_fid="F-A")
    cur = _cur(factory_id="F-B")

    with patch("routers.document_engine_api._render_html", new_callable=AsyncMock) as rdr:
        with patch("routers.document_engine_api.get_supabase", return_value=sb):
            for p in _NOOP_PATCHES:
                patch(p, side_effect=_noop).start()
            with pytest.raises(HTTPException) as ei:
                asyncio.run(auto_document_preview("TBM", "TBM-1", cur))
            assert ei.value.status_code == 404
            rdr.assert_not_called()
    patch.stopall()


def test_ST2_tbm_preview_same_factory_render_called():
    """FACTORY user → same factory TBM Preview → render called."""
    sb = _make_sb("FACTORY", tbm_fid="F-A")
    cur = _cur(factory_id="F-A")

    with patch("routers.document_engine_api._render_html", new_callable=AsyncMock, return_value="<html>") as rdr:
        with patch("routers.document_engine_api.get_supabase", return_value=sb):
            for p in _NOOP_PATCHES:
                patch(p, side_effect=_noop).start()
            asyncio.run(auto_document_preview("TBM", "TBM-1", cur))
            rdr.assert_called_once()
    patch.stopall()


# ── TBM PDF ───────────────────────────────────────────────────────────────────

def test_ST3_tbm_pdf_cross_factory_404_render_not_called():
    """FACTORY user → different factory TBM PDF → 404, render never called."""
    sb = _make_sb("FACTORY", tbm_fid="F-A")
    cur = _cur(factory_id="F-B")

    with patch("routers.document_engine_api._render_pdf", new_callable=AsyncMock) as rdr:
        with patch("routers.document_engine_api.get_supabase", return_value=sb):
            for p in _NOOP_PATCHES:
                patch(p, side_effect=_noop).start()
            with pytest.raises(HTTPException) as ei:
                asyncio.run(auto_document_pdf("TBM", "TBM-1", cur))
            assert ei.value.status_code == 404
            rdr.assert_not_called()
    patch.stopall()


def test_ST4_tbm_pdf_same_factory_render_called():
    """FACTORY user → same factory TBM PDF → render called."""
    sb = _make_sb("FACTORY", tbm_fid="F-A")
    cur = _cur(factory_id="F-A")

    with patch("routers.document_engine_api._render_pdf", new_callable=AsyncMock, return_value=b"%PDF") as rdr:
        with patch("routers.document_engine_api.get_supabase", return_value=sb):
            for p in _NOOP_PATCHES:
                patch(p, side_effect=_noop).start()
            asyncio.run(auto_document_pdf("TBM", "TBM-1", cur))
            rdr.assert_called_once()
    patch.stopall()


# ── Tier policy ───────────────────────────────────────────────────────────────

def test_SP1_company_tier_bypass_render_called():
    """COMPANY tier → factory check skipped, render called."""
    sb = _make_sb("COMPANY", insp_fid="F-A")
    cur = _cur(factory_id="F-B")  # different factory — irrelevant for COMPANY

    with patch("routers.document_engine_api._render_html", new_callable=AsyncMock, return_value="<html>") as rdr:
        with patch("routers.document_engine_api.get_supabase", return_value=sb):
            for p in _NOOP_PATCHES:
                patch(p, side_effect=_noop).start()
            asyncio.run(auto_document_preview("INSPECTION", "INS-1", cur))
            rdr.assert_called_once()
    patch.stopall()


def test_SP2_all_tier_bypass_render_called():
    """ALL tier → factory check skipped, render called."""
    sb = _make_sb("ALL", tbm_fid="F-A")
    cur = _cur(factory_id="F-B")

    with patch("routers.document_engine_api._render_html", new_callable=AsyncMock, return_value="<html>") as rdr:
        with patch("routers.document_engine_api.get_supabase", return_value=sb):
            for p in _NOOP_PATCHES:
                patch(p, side_effect=_noop).start()
            asyncio.run(auto_document_preview("TBM", "TBM-1", cur))
            rdr.assert_called_once()
    patch.stopall()


def test_SP3_team_cross_factory_404_render_not_called():
    """TEAM tier → different factory → 404, render not called."""
    sb = _make_sb("TEAM", insp_fid="F-A")
    cur = _cur(factory_id="F-B")

    with patch("routers.document_engine_api._render_html", new_callable=AsyncMock) as rdr:
        with patch("routers.document_engine_api.get_supabase", return_value=sb):
            for p in _NOOP_PATCHES:
                patch(p, side_effect=_noop).start()
            with pytest.raises(HTTPException) as ei:
                asyncio.run(auto_document_preview("INSPECTION", "INS-1", cur))
            assert ei.value.status_code == 404
            rdr.assert_not_called()
    patch.stopall()


def test_SP4_assigned_cross_factory_404_render_not_called():
    """ASSIGNED tier (E-3 stub, acts like FACTORY) → different factory → 404.

    Consistent with scoped_filter ASSIGNED behaviour (factory_id col present → factory filter).
    """
    sb = _make_sb("ASSIGNED", tbm_fid="F-A")
    cur = _cur(factory_id="F-B")

    with patch("routers.document_engine_api._render_html", new_callable=AsyncMock) as rdr:
        with patch("routers.document_engine_api.get_supabase", return_value=sb):
            for p in _NOOP_PATCHES:
                patch(p, side_effect=_noop).start()
            with pytest.raises(HTTPException) as ei:
                asyncio.run(auto_document_preview("TBM", "TBM-1", cur))
            assert ei.value.status_code == 404
            rdr.assert_not_called()
    patch.stopall()


# ── Fail-closed ───────────────────────────────────────────────────────────────

def test_SF1_null_resource_factory_id_fail_closed():
    """FACTORY user, resource.factory_id=None → fail-closed 404, render not called."""
    sb = _make_sb("FACTORY", insp_fid=None)
    cur = _cur(factory_id="F-A")

    with patch("routers.document_engine_api._render_html", new_callable=AsyncMock) as rdr:
        with patch("routers.document_engine_api.get_supabase", return_value=sb):
            for p in _NOOP_PATCHES:
                patch(p, side_effect=_noop).start()
            with pytest.raises(HTTPException) as ei:
                asyncio.run(auto_document_preview("INSPECTION", "INS-1", cur))
            assert ei.value.status_code == 404
            rdr.assert_not_called()
    patch.stopall()


def test_SF2_missing_resource_row_404_render_not_called():
    """FACTORY user, resource row not found → 404, render not called."""
    sb = _make_sb("FACTORY", insp_missing=True)
    cur = _cur(factory_id="F-A")

    with patch("routers.document_engine_api._render_pdf", new_callable=AsyncMock) as rdr:
        with patch("routers.document_engine_api.get_supabase", return_value=sb):
            for p in _NOOP_PATCHES:
                patch(p, side_effect=_noop).start()
            with pytest.raises(HTTPException) as ei:
                asyncio.run(auto_document_pdf("INSPECTION", "INS-1", cur))
            assert ei.value.status_code == 404
            rdr.assert_not_called()
    patch.stopall()
