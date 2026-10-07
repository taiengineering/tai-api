"""AUTO-REUSE-01: Auto document discovery tests.

Backend contract:
  L1-L8:  list_auto_documents() unit tests (mock DB)
  I1-I4:  identity / document_key format
  R1-R4:  render delegation (mock generator)
  M1-M3:  mutation guard (zero persistence assertions)
  S1-S2:  scope / cross-company guard
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.company_scope import DENY
from services.document_engine.auto_source_readmodel import (
    _build_insp_document_key,
    _build_tbm_document_key,
    list_auto_documents,
)


# ── test doubles ──────────────────────────────────────────────────────────────

def _make_sb(insp_rows=None, tbm_rows=None):
    """Mock supabase client returning provided row sets."""
    insp_rows = insp_rows or []
    tbm_rows = tbm_rows or []

    class _FakeResult:
        def __init__(self, data, count=None):
            self.data = data
            self.count = count or len(data)

    class _FakeQuery:
        def __init__(self, data):
            self._data = data
            self._status_filter = None

        def select(self, *a, **kw): return self
        def in_(self, col, vals): return self
        def eq(self, col, val):
            if col == "status_code":
                self._status_filter = val
            return self
        def order(self, *a, **kw): return self
        def limit(self, *a, **kw): return self
        def range(self, *a, **kw): return self
        def gte(self, *a, **kw): return self
        def lte(self, *a, **kw): return self

        def execute(self):
            return _FakeResult(self._data)

    class _FakeSB:
        def table(self, name):
            if name == "safety_inspections":
                return _FakeQuery(insp_rows)
            if name == "tbm_meetings":
                return _FakeQuery(tbm_rows)
            return _FakeQuery([])

    return _FakeSB()


def _insp_row(id="insp-001", status="COMPLETED", factory_id="fac-1"):
    return {
        "id": id,
        "status_code": status,
        "inspection_date": "2026-10-08T10:00:00+09:00",
        "factory_id": factory_id,
        "work_schedules": {"summary": "전기설비 정기점검", "company_id": "co-1", "factory_id": factory_id},
    }


def _tbm_row(id="tbm-001", status="COMPLETED", factory_id="fac-1"):
    return {
        "id": id,
        "status_code": status,
        "work_date": "2026-10-08",
        "completed_at": "2026-10-08T09:00:00+09:00",
        "meeting_title": "작업 전 안전교육",
        "factory_id": factory_id,
        "company_id": "co-1",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# I: Identity / document_key
# ═══════════════════════════════════════════════════════════════════════════════

def test_I1_insp_document_key_format():
    key = _build_insp_document_key("uuid-123")
    assert key == "auto:v1:INSPECTION:uuid-123:INSP:-"


def test_I2_tbm_document_key_format():
    key = _build_tbm_document_key("uuid-456")
    assert key == "auto:v1:TBM:uuid-456:TBM:-"


def test_I3_insp_item_has_correct_channel_and_doc_type():
    sb = _make_sb(insp_rows=[_insp_row()])
    result = list_auto_documents(sb, {}, source_type="INSPECTION")
    item = result["items"][0]
    assert item["channel"] == "AUTO_SOURCE"
    assert item["doc_type"] == "INSP"
    assert item["source_type"] == "INSPECTION"


def test_I4_tbm_item_has_correct_channel_and_doc_type():
    sb = _make_sb(tbm_rows=[_tbm_row()])
    result = list_auto_documents(sb, {}, source_type="TBM")
    item = result["items"][0]
    assert item["channel"] == "AUTO_SOURCE"
    assert item["doc_type"] == "TBM"
    assert item["source_type"] == "TBM"


# ═══════════════════════════════════════════════════════════════════════════════
# L: list_auto_documents unit tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_L1_completed_inspection_included():
    sb = _make_sb(insp_rows=[_insp_row(status="COMPLETED")])
    result = list_auto_documents(sb, {}, source_type="INSPECTION")
    assert result["total"] == 1
    assert result["items"][0]["source_id"] == "insp-001"


def test_L2_completed_tbm_included():
    sb = _make_sb(tbm_rows=[_tbm_row(status="COMPLETED")])
    result = list_auto_documents(sb, {}, source_type="TBM")
    assert result["total"] == 1
    assert result["items"][0]["source_id"] == "tbm-001"


def test_L3_all_source_merges_both():
    sb = _make_sb(insp_rows=[_insp_row()], tbm_rows=[_tbm_row()])
    result = list_auto_documents(sb, {}, source_type="ALL")
    types = {i["source_type"] for i in result["items"]}
    assert types == {"INSPECTION", "TBM"}
    assert result["total"] == 2


def test_L4_deny_scope_returns_empty():
    sb = _make_sb(insp_rows=[_insp_row()], tbm_rows=[_tbm_row()])
    result = list_auto_documents(sb, DENY, source_type="ALL")
    assert result["items"] == []
    assert result["total"] == 0


def test_L5_inspection_title_from_work_schedule_summary():
    sb = _make_sb(insp_rows=[_insp_row()])
    result = list_auto_documents(sb, {}, source_type="INSPECTION")
    assert result["items"][0]["title"] == "전기설비 정기점검"


def test_L6_inspection_title_fallback_when_no_summary():
    row = _insp_row()
    row["work_schedules"] = {}
    sb = _make_sb(insp_rows=[row])
    result = list_auto_documents(sb, {}, source_type="INSPECTION")
    assert result["items"][0]["title"] == "점검 기록"


def test_L7_tbm_title_from_meeting_title():
    sb = _make_sb(tbm_rows=[_tbm_row()])
    result = list_auto_documents(sb, {}, source_type="TBM")
    assert result["items"][0]["title"] == "작업 전 안전교육"


def test_L8_tbm_title_fallback_when_no_meeting_title():
    row = _tbm_row()
    row["meeting_title"] = None
    sb = _make_sb(tbm_rows=[row])
    result = list_auto_documents(sb, {}, source_type="TBM")
    assert result["items"][0]["title"].startswith("TBM ")


# ═══════════════════════════════════════════════════════════════════════════════
# L: Pagination
# ═══════════════════════════════════════════════════════════════════════════════

def test_L9_pagination_slices_correctly():
    rows = [_insp_row(id=f"insp-{i:03d}") for i in range(10)]
    sb = _make_sb(insp_rows=rows)
    result = list_auto_documents(sb, {}, source_type="INSPECTION", page=2, page_size=3)
    assert len(result["items"]) == 3
    assert result["total"] == 10
    assert result["page"] == 2
    assert result["total_pages"] == 4


def test_L10_can_preview_and_pdf_always_true():
    sb = _make_sb(insp_rows=[_insp_row()], tbm_rows=[_tbm_row()])
    result = list_auto_documents(sb, {}, source_type="ALL")
    for item in result["items"]:
        assert item["can_preview"] is True
        assert item["can_pdf"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# R: Render delegation (mock generator)
# ═══════════════════════════════════════════════════════════════════════════════

def test_R1_inspection_preview_delegates_to_render_html():
    with patch(
        "routers.document_engine_api._render_html",
        new_callable=AsyncMock,
        return_value="<html>inspection</html>",
    ) as mock_render:
        from routers.document_engine_api import auto_document_preview

        with patch("routers.document_engine_api._ensure_inspection_own"):
            with patch("routers.document_engine_api.get_supabase"):
                asyncio.run(auto_document_preview("INSPECTION", "insp-uuid", {}))
                mock_render.assert_called_once_with("INSP", {"inspection_id": "insp-uuid"})


def test_R2_tbm_preview_delegates_to_render_html():
    with patch(
        "routers.document_engine_api._render_html",
        new_callable=AsyncMock,
        return_value="<html>tbm</html>",
    ) as mock_render:
        from routers.document_engine_api import auto_document_preview

        with patch("routers.document_engine_api._ensure_tbm_own"):
            with patch("routers.document_engine_api.get_supabase"):
                asyncio.run(auto_document_preview("TBM", "tbm-uuid", {}))
                mock_render.assert_called_once_with("TBM", {"meeting_id": "tbm-uuid"})


def test_R3_inspection_pdf_delegates_to_render_pdf():
    with patch(
        "routers.document_engine_api._render_pdf",
        new_callable=AsyncMock,
        return_value=b"%PDF-test",
    ) as mock_render:
        from routers.document_engine_api import auto_document_pdf

        with patch("routers.document_engine_api._ensure_inspection_own"):
            with patch("routers.document_engine_api.get_supabase"):
                resp = asyncio.run(auto_document_pdf("INSPECTION", "insp-uuid", {}))
                mock_render.assert_called_once_with("INSP", {"inspection_id": "insp-uuid"})
                assert resp.media_type == "application/pdf"


def test_R4_tbm_pdf_delegates_to_render_pdf():
    with patch(
        "routers.document_engine_api._render_pdf",
        new_callable=AsyncMock,
        return_value=b"%PDF-test",
    ) as mock_render:
        from routers.document_engine_api import auto_document_pdf

        with patch("routers.document_engine_api._ensure_tbm_own"):
            with patch("routers.document_engine_api.get_supabase"):
                asyncio.run(auto_document_pdf("TBM", "tbm-uuid", {}))
                mock_render.assert_called_once_with("TBM", {"meeting_id": "tbm-uuid"})


# ═══════════════════════════════════════════════════════════════════════════════
# M: Mutation guard
# ═══════════════════════════════════════════════════════════════════════════════

def test_M1_list_does_not_call_insert(monkeypatch):
    insert_calls = []
    sb = _make_sb(insp_rows=[_insp_row()], tbm_rows=[_tbm_row()])

    original_table = sb.table

    def tracking_table(name):
        q = original_table(name)
        orig_execute = q.execute

        def tracked_execute():
            # ensure we never see an insert method called
            assert not hasattr(q, "_insert_called"), "INSERT must not be called"
            return orig_execute()

        q.execute = tracked_execute
        q.insert = lambda *a, **kw: (_ for _ in ()).throw(AssertionError("INSERT must not be called"))
        return q

    sb.table = tracking_table
    result = list_auto_documents(sb, {}, source_type="ALL")
    assert result["total"] >= 0  # just ensure it ran without insert


def test_M2_list_has_no_migration_files():
    """No new migration should exist for this WO."""
    import pathlib
    migrations = list(pathlib.Path("supabase/migrations").glob("*auto_reuse*"))
    assert migrations == [], f"No auto-reuse migration expected; found: {migrations}"


def test_M3_no_auto_projection_selector_files_on_main():
    """02B selector/resolver files must not exist on main branch."""
    import pathlib
    selector = pathlib.Path("services/document_engine/auto_source_projection_selector.py")
    resolver = pathlib.Path("services/document_engine/equipment_projection_resolver.py")
    assert not selector.exists(), "auto_source_projection_selector must not exist on main"
    assert not resolver.exists(), "equipment_projection_resolver must not exist on main"


# ═══════════════════════════════════════════════════════════════════════════════
# S: Scope / cross-company
# ═══════════════════════════════════════════════════════════════════════════════

def test_S1_deny_scope_returns_zero_items():
    sb = _make_sb(insp_rows=[_insp_row()], tbm_rows=[_tbm_row()])
    result = list_auto_documents(sb, DENY)
    assert result["items"] == []
    assert result["total"] == 0


def test_S2_empty_scope_filter_passes_through():
    sb = _make_sb(insp_rows=[_insp_row()], tbm_rows=[_tbm_row()])
    result = list_auto_documents(sb, {}, source_type="ALL")
    assert result["total"] == 2
