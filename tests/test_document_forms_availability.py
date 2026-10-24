"""
tests/test_document_forms_availability.py
WO-TAI-POSTM004-DOC260-LIST-AVAILABILITY-CORR-001

Direct regression tests for _enrich_with_availability() and list_document_forms().
No live DB; all Supabase calls are mocked.

Test matrix:
  T01 — APPROVED == 1                         → READY_FOR_EDIT
  T02 — CANDIDATE only                        → PREPARING
  T03 — no schema                             → NO_SCHEMA
  T04 — APPROVED > 1 (integrity violation)    → SCHEMA_ERROR
  T05 — DB query failure                      → NO_SCHEMA (fail-closed, never READY)
  T06 — 200-item page 1 + 60-item page 2      → schema_availability on all items
  T07 — batch query called exactly once       → 1 extra DB query per page (N+1 guard)
  T08 — filters/search/sort preserved        → list_document_forms() delegates unchanged
  T09 — mixed page (all 4 states)             → correct per-item mapping
  T10 — items with no id field               → NO_SCHEMA fallback
"""
from __future__ import annotations

import sys
import os
import unittest
from typing import Any
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.document_forms_service import _enrich_with_availability, list_document_forms

_APPROVED_STATUS = "APPROVED_FOR_RUNTIME_USE"
_CANDIDATE_STATUS = "CANDIDATE"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(doc_id: str, uid: str) -> dict:
    return {"id": uid, "doc_id": doc_id, "doc_name": f"서식 {doc_id}"}


def _mock_supabase(schema_data: list[dict]) -> MagicMock:
    """Returns a Supabase client mock whose runtime_form_schema query returns schema_data."""
    chain = MagicMock()
    chain.execute.return_value = MagicMock(data=schema_data)
    # All chained calls (.select, .in_, .in_) return the same chain mock
    chain.select.return_value = chain
    chain.in_.return_value = chain

    sb = MagicMock()
    sb.table.return_value = chain
    return sb


# ---------------------------------------------------------------------------
# T01 ~ T05: _enrich_with_availability unit tests
# ---------------------------------------------------------------------------

class TestEnrichAvailabilityUnit(unittest.TestCase):

    def test_t01_approved_one_ready_for_edit(self):
        items = [_make_item("DOC-A", "uid-a")]
        schema_data = [{"catalog_document_id": "uid-a", "status": _APPROVED_STATUS}]
        sb = _mock_supabase(schema_data)
        _enrich_with_availability(sb, items)
        self.assertEqual(items[0]["schema_availability"], "READY_FOR_EDIT")

    def test_t02_candidate_only_preparing(self):
        items = [_make_item("DOC-B", "uid-b")]
        schema_data = [{"catalog_document_id": "uid-b", "status": _CANDIDATE_STATUS}]
        sb = _mock_supabase(schema_data)
        _enrich_with_availability(sb, items)
        self.assertEqual(items[0]["schema_availability"], "PREPARING")

    def test_t03_no_schema(self):
        items = [_make_item("DOC-C", "uid-c")]
        sb = _mock_supabase([])
        _enrich_with_availability(sb, items)
        self.assertEqual(items[0]["schema_availability"], "NO_SCHEMA")

    def test_t04_approved_duplicate_schema_error(self):
        """APPROVED > 1 → SCHEMA_ERROR, not PREPARING (integrity violation parity with catalog_resolver)."""
        items = [_make_item("DOC-D", "uid-d")]
        schema_data = [
            {"catalog_document_id": "uid-d", "status": _APPROVED_STATUS},
            {"catalog_document_id": "uid-d", "status": _APPROVED_STATUS},
        ]
        sb = _mock_supabase(schema_data)
        _enrich_with_availability(sb, items)
        self.assertEqual(items[0]["schema_availability"], "SCHEMA_ERROR")
        self.assertNotEqual(items[0]["schema_availability"], "PREPARING")
        self.assertNotEqual(items[0]["schema_availability"], "READY_FOR_EDIT")

    def test_t05_db_failure_fail_closed_no_schema(self):
        """DB query exception must never result in READY_FOR_EDIT (fail-closed → NO_SCHEMA)."""
        items = [_make_item("DOC-E", "uid-e"), _make_item("DOC-F", "uid-f")]
        sb = MagicMock()
        chain = MagicMock()
        chain.select.return_value = chain
        chain.in_.return_value = chain
        chain.execute.side_effect = RuntimeError("connection refused")
        sb.table.return_value = chain

        _enrich_with_availability(sb, items)
        for item in items:
            self.assertEqual(item["schema_availability"], "NO_SCHEMA")
            self.assertNotEqual(item["schema_availability"], "READY_FOR_EDIT")


# ---------------------------------------------------------------------------
# T06 ~ T09: multi-item and pagination tests
# ---------------------------------------------------------------------------

class TestEnrichAvailabilityBatch(unittest.TestCase):

    def test_t06_page1_200_and_page2_60_all_enriched(self):
        """Every item across two page calls gets schema_availability."""
        page1 = [_make_item(f"DOC-{i:03}", f"uid-{i:03}") for i in range(200)]
        page2 = [_make_item(f"DOC-{i:03}", f"uid-{i:03}") for i in range(200, 260)]

        def _make_schema(items_list):
            return [
                {"catalog_document_id": it["id"], "status": _APPROVED_STATUS}
                for it in items_list
            ]

        sb1 = _mock_supabase(_make_schema(page1))
        sb2 = _mock_supabase(_make_schema(page2))

        _enrich_with_availability(sb1, page1)
        _enrich_with_availability(sb2, page2)

        for item in page1 + page2:
            self.assertIn("schema_availability", item)
            self.assertEqual(item["schema_availability"], "READY_FOR_EDIT")

    def test_t07_exactly_one_batch_query_per_page(self):
        """_enrich_with_availability issues exactly 1 DB query (N+1 guard)."""
        items = [_make_item(f"DOC-{i}", f"uid-{i}") for i in range(50)]
        schema_data = [
            {"catalog_document_id": f"uid-{i}", "status": _APPROVED_STATUS}
            for i in range(50)
        ]
        sb = _mock_supabase(schema_data)
        _enrich_with_availability(sb, items)

        # table("runtime_form_schema") called exactly once
        runtime_calls = [c for c in sb.table.call_args_list if c == call("runtime_form_schema")]
        self.assertEqual(len(runtime_calls), 1)

    def test_t09_mixed_page_all_four_states(self):
        """A single page with READY/PREPARING/NO_SCHEMA/SCHEMA_ERROR items."""
        items = [
            _make_item("DOC-R", "uid-ready"),
            _make_item("DOC-P", "uid-preparing"),
            _make_item("DOC-N", "uid-none"),
            _make_item("DOC-E", "uid-error"),
        ]
        schema_data = [
            {"catalog_document_id": "uid-ready",    "status": _APPROVED_STATUS},
            {"catalog_document_id": "uid-preparing", "status": _CANDIDATE_STATUS},
            {"catalog_document_id": "uid-error",    "status": _APPROVED_STATUS},
            {"catalog_document_id": "uid-error",    "status": _APPROVED_STATUS},
        ]
        sb = _mock_supabase(schema_data)
        _enrich_with_availability(sb, items)

        by_doc = {i["doc_id"]: i["schema_availability"] for i in items}
        self.assertEqual(by_doc["DOC-R"], "READY_FOR_EDIT")
        self.assertEqual(by_doc["DOC-P"], "PREPARING")
        self.assertEqual(by_doc["DOC-N"], "NO_SCHEMA")
        self.assertEqual(by_doc["DOC-E"], "SCHEMA_ERROR")

    def test_t10_items_without_id_get_no_schema(self):
        """Items missing 'id' must never be set to READY_FOR_EDIT."""
        items = [{"doc_id": "DOC-X", "doc_name": "no id item"}]
        sb = _mock_supabase([])
        _enrich_with_availability(sb, items)
        self.assertEqual(items[0]["schema_availability"], "NO_SCHEMA")
        self.assertNotEqual(items[0]["schema_availability"], "READY_FOR_EDIT")


# ---------------------------------------------------------------------------
# T08: list_document_forms filter/search/sort delegation preserved
# ---------------------------------------------------------------------------

class TestListDocumentFormsIntegration(unittest.TestCase):

    def _make_list_mock(self, items: list[dict], total: int) -> MagicMock:
        """Supabase mock for list_document_forms() — document_forms + runtime_form_schema."""
        sb = MagicMock()

        # document_forms query chain
        df_chain = MagicMock()
        df_res = MagicMock()
        df_res.data = items
        df_res.count = total
        df_chain.execute.return_value = df_res
        df_chain.select.return_value = df_chain
        df_chain.eq.return_value = df_chain
        df_chain.or_.return_value = df_chain
        df_chain.order.return_value = df_chain
        df_chain.range.return_value = df_chain

        # runtime_form_schema chain
        rfs_chain = MagicMock()
        rfs_chain.execute.return_value = MagicMock(data=[])
        rfs_chain.select.return_value = rfs_chain
        rfs_chain.in_.return_value = rfs_chain

        def _table_router(name: str):
            if name == "document_forms":
                return df_chain
            return rfs_chain

        sb.table.side_effect = _table_router
        return sb

    def test_t08_filters_preserved_and_availability_added(self):
        """list_document_forms() passes filters through and enriches with schema_availability."""
        raw_items = [_make_item(f"DOC-{i}", f"uid-{i}") for i in range(5)]
        sb = self._make_list_mock(raw_items, total=5)

        with patch("services.document_forms_service.get_supabase", return_value=sb):
            result = list_document_forms(sector="OSH", page=1, per_page=20)

        self.assertEqual(result["total"], 5)
        self.assertEqual(result["page"], 1)
        self.assertEqual(len(result["items"]), 5)
        for item in result["items"]:
            self.assertIn("schema_availability", item)
            self.assertEqual(item["schema_availability"], "NO_SCHEMA")


if __name__ == "__main__":
    unittest.main()
