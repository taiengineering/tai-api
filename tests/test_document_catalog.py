"""
tests/test_document_catalog.py
WO-TAI-DOC-UNIFIED-CATALOG-IMPLEMENT-001 — Phase 1

Contract tests for services/catalog_aggregator.py and routers/document_catalog.py.
No live DB; all REST calls are mocked.

Production schema contract:
  document_forms:             doc_id, doc_name, is_active=true
  runtime_form_schema:        catalog_document_id, status
  reference_form_public_view: canonical_slug, title, qa_pass_files (JSONB)
"""

from __future__ import annotations

import sys
import os
import unittest
from typing import Any
from unittest.mock import MagicMock

# ─── ensure services/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.catalog_aggregator import (
    CatalogPage,
    CatalogItem,
    SupabaseRestClient,
    compute_channel_state,
    get_unified_catalog,
    get_document_detail,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_saas_row(
    doc_id: str = "DOC-OSH-058",
    doc_name: str = "산업안전보건위원회 회의록",
    file_url: str | None = "https://www.law.go.kr/LSW/flDownload.do?flSeq=123",
    schema_status: str = "CANDIDATE",
    doc_format: str = "DIGITAL_OK",
) -> dict[str, Any]:
    return {
        "id": f"uuid-{doc_id}",
        "doc_id": doc_id,
        "doc_name": doc_name,
        "sector": "COMMON",
        "category": "회의",
        "is_active": True,
        "doc_format": doc_format,
        "file_url": file_url,
        "schema_status": schema_status,
    }


def _make_ref_row(
    slug: str = "ref-gov-01",
    title: str = "산업안전보건위원회 회의록",
    file_count: int = 1,
) -> dict[str, Any]:
    qa_pass_files = [
        {"file_id": f"uuid-file-{i}", "sha256": "abc123", "format": "pdf", "has_preview": False}
        for i in range(file_count)
    ]
    return {
        "id": f"uuid-{slug}",
        "canonical_slug": slug,
        "title": title,
        "qa_pass_files": qa_pass_files,
    }


def _make_mock_client(saas_rows=None, ref_rows=None, schema_rows=None):
    client = MagicMock(spec=SupabaseRestClient)

    def _select(table, columns="*", filters=None, order=None, limit=None, offset=None):
        filters = filters or {}
        if table == "document_forms":
            return saas_rows or []
        if table == "reference_form_public_view":
            return ref_rows or []
        if table == "runtime_form_schema":
            return schema_rows or []
        return []

    client.select.side_effect = _select
    return client


# ---------------------------------------------------------------------------
# T1: SAAS CANDIDATE schema → WEB_EDIT=BLOCKED
# ---------------------------------------------------------------------------

class T1_SaasCandidateSchemaWebEditBlocked(unittest.TestCase):
    def test(self):
        channels = compute_channel_state(
            record_type="SAAS",
            schema_status="CANDIDATE",
            file_count=0,
            file_url=None,
            rights_state="DIGITAL_OK",
        )
        self.assertEqual(channels.WEB_EDIT.state, "BLOCKED")
        self.assertIn("CANDIDATE", channels.WEB_EDIT.reason)


# ---------------------------------------------------------------------------
# T2: REF form with QA_PASS files → REFERENCE_DOWNLOAD=READY
# ---------------------------------------------------------------------------

class T2_RefFormWithFilesReferenceDownloadReady(unittest.TestCase):
    def test(self):
        channels = compute_channel_state(
            record_type="REFERENCE_CMS",
            schema_status=None,
            file_count=3,
            file_url=None,
            rights_state=None,
        )
        self.assertEqual(channels.REFERENCE_DOWNLOAD.state, "READY")


# ---------------------------------------------------------------------------
# T3: file_url with flDownload.do → OFFICIAL_ORIGINAL=UNVERIFIED
# ---------------------------------------------------------------------------

class T3_LawGoKrUrlOfficialOriginalUnverified(unittest.TestCase):
    def test(self):
        channels = compute_channel_state(
            record_type="SAAS",
            schema_status="CANDIDATE",
            file_count=0,
            file_url="https://www.law.go.kr/LSW/flDownload.do?flSeq=456",
            rights_state="DIGITAL_OK",
        )
        self.assertEqual(channels.OFFICIAL_ORIGINAL.state, "UNVERIFIED")
        self.assertIn("binary not fetched", channels.OFFICIAL_ORIGINAL.reason)


# ---------------------------------------------------------------------------
# T4: no file_url → OFFICIAL_ORIGINAL=BLOCKED (SAAS) or NOT_APPLICABLE (REF)
# ---------------------------------------------------------------------------

class T4_NoFileUrl(unittest.TestCase):
    def test_saas_no_file_url_blocked(self):
        channels = compute_channel_state(
            record_type="SAAS",
            schema_status="CANDIDATE",
            file_count=0,
            file_url=None,
            rights_state=None,
        )
        self.assertEqual(channels.OFFICIAL_ORIGINAL.state, "BLOCKED")

    def test_ref_no_file_url_not_applicable(self):
        channels = compute_channel_state(
            record_type="REFERENCE_CMS",
            schema_status=None,
            file_count=0,
            file_url=None,
            rights_state=None,
        )
        self.assertEqual(channels.OFFICIAL_ORIGINAL.state, "NOT_APPLICABLE")


# ---------------------------------------------------------------------------
# T5: SAAS_AUTO_FILL always BLOCKED
# ---------------------------------------------------------------------------

class T5_AutoFillAlwaysBlocked(unittest.TestCase):
    def test_saas(self):
        channels = compute_channel_state(
            record_type="SAAS",
            schema_status="APPROVED_FOR_RUNTIME_USE",
            file_count=0,
            file_url=None,
            rights_state="DIGITAL_OK",
        )
        self.assertEqual(channels.SAAS_AUTO_FILL.state, "BLOCKED")

    def test_ref(self):
        channels = compute_channel_state(
            record_type="REFERENCE_CMS",
            schema_status=None,
            file_count=1,
            file_url=None,
            rights_state=None,
        )
        self.assertEqual(channels.SAAS_AUTO_FILL.state, "NOT_APPLICABLE")


# ---------------------------------------------------------------------------
# T6: get_document_detail resolves DOC: key → SAAS record
# ---------------------------------------------------------------------------

class T6_DocKeyResolvesSaasRecord(unittest.TestCase):
    def test(self):
        client = _make_mock_client(
            saas_rows=[_make_saas_row("DOC-OSH-058")],
            schema_rows=[{"catalog_document_id": "uuid-DOC-OSH-058", "status": "CANDIDATE"}],
        )
        item = get_document_detail(client, "DOC:DOC-OSH-058")
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.provisional_key, "DOC:DOC-OSH-058")
        self.assertEqual(item.source_system, "SAAS")


# ---------------------------------------------------------------------------
# T7: get_document_detail resolves REF: key → REFERENCE_CMS record
# ---------------------------------------------------------------------------

class T7_RefKeyResolvesRefRecord(unittest.TestCase):
    def test(self):
        client = _make_mock_client(ref_rows=[_make_ref_row("ref-gov-01")])
        item = get_document_detail(client, "REF:ref-gov-01")
        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item.provisional_key, "REF:ref-gov-01")
        self.assertEqual(item.source_system, "REFERENCE_CMS")


# ---------------------------------------------------------------------------
# T8: pagination respects page + per_page
# ---------------------------------------------------------------------------

class T8_PaginationRespected(unittest.TestCase):
    def test(self):
        saas_rows = [_make_saas_row(f"DOC-{i:03d}") for i in range(10)]
        client = _make_mock_client(saas_rows=saas_rows, schema_rows=[])
        result = get_unified_catalog(client, page=2, per_page=3, source_system="SAAS")
        self.assertEqual(result.total, 10)
        self.assertEqual(result.page, 2)
        self.assertEqual(len(result.items), 3)
        self.assertEqual(result.items[0].source_code, "DOC-003")


# ---------------------------------------------------------------------------
# T9: APPROVED_FOR_RUNTIME_USE → WEB_EDIT=READY
# ---------------------------------------------------------------------------

class T9_SaasApprovedSchemaWebEditReady(unittest.TestCase):
    def test(self):
        channels = compute_channel_state(
            record_type="SAAS",
            schema_status="APPROVED_FOR_RUNTIME_USE",
            file_count=0,
            file_url=None,
            rights_state="DIGITAL_OK",
        )
        self.assertEqual(channels.WEB_EDIT.state, "READY")
        self.assertEqual(channels.SAAS_EXPORT.state, "READY")


# ---------------------------------------------------------------------------
# T10: REF form no QA_PASS files → REFERENCE_DOWNLOAD=BLOCKED
# ---------------------------------------------------------------------------

class T10_RefFormNoFilesBlocked(unittest.TestCase):
    def test(self):
        client = _make_mock_client(ref_rows=[_make_ref_row("ref-empty", file_count=0)])
        result = get_unified_catalog(client, source_system="REFERENCE_CMS")
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].channels.REFERENCE_DOWNLOAD.state, "BLOCKED")


# ---------------------------------------------------------------------------
# T11 (DB contract): SAAS query uses is_active=true filter
# ---------------------------------------------------------------------------

class T11_SaasQueryUsesIsActiveFilter(unittest.TestCase):
    def test(self):
        calls: list[dict] = []

        def _select(table, columns="*", filters=None, **_):
            if table == "document_forms":
                calls.append({"filters": dict(filters) if filters else {}})
            return []

        client = MagicMock(spec=SupabaseRestClient)
        client.select.side_effect = _select
        get_unified_catalog(client, source_system="SAAS")

        self.assertTrue(len(calls) >= 1)
        self.assertEqual(calls[0]["filters"].get("is_active"), "eq.true",
                         "document_forms query must filter is_active=true")


# ---------------------------------------------------------------------------
# T12 (DB contract): SAAS query selects correct columns (no 'title' column)
# ---------------------------------------------------------------------------

class T12_SaasQuerySelectsCorrectColumns(unittest.TestCase):
    def test(self):
        call_columns: list[str] = []

        def _select(table, columns="*", filters=None, **_):
            if table == "document_forms":
                call_columns.append(columns)
            return []

        client = MagicMock(spec=SupabaseRestClient)
        client.select.side_effect = _select
        get_unified_catalog(client, source_system="SAAS")

        self.assertTrue(len(call_columns) >= 1)
        saas_call = {"columns": call_columns[0]}
        self.assertIn("doc_id", saas_call["columns"])
        self.assertIn("doc_name", saas_call["columns"])
        self.assertNotIn("title,", saas_call["columns"] + ",",
                         "document_forms has no 'title' column")


# ---------------------------------------------------------------------------
# T13 (DB contract): REF query targets reference_form_public_view, not reference_forms
# ---------------------------------------------------------------------------

class T13_RefQueryTargetsPublicView(unittest.TestCase):
    def test_uses_reference_form_public_view(self):
        calls: list[str] = []

        def _select(table, **_):
            calls.append(table)
            return []

        client = MagicMock(spec=SupabaseRestClient)
        client.select.side_effect = _select
        get_unified_catalog(client, source_system="REFERENCE_CMS")

        self.assertIn("reference_form_public_view", calls)
        self.assertNotIn("reference_forms", calls)

    def test_no_publish_status_filter_on_view(self):
        calls: list[dict] = []

        def _select(table, columns="*", filters=None, **_):
            if table == "reference_form_public_view":
                calls.append({"filters": dict(filters) if filters else {}})
            return []

        client = MagicMock(spec=SupabaseRestClient)
        client.select.side_effect = _select
        get_unified_catalog(client, source_system="REFERENCE_CMS")

        if calls:
            self.assertNotIn("publish_status", calls[0]["filters"])


# ---------------------------------------------------------------------------
# T14 (DB contract): REF file count from qa_pass_files JSONB, not separate table
# ---------------------------------------------------------------------------

class T14_RefFileCountFromQaPassFiles(unittest.TestCase):
    def test_file_count_from_view_jsonb(self):
        tables_queried: list[str] = []

        def _select(table, **_):
            tables_queried.append(table)
            if table == "reference_form_public_view":
                return [_make_ref_row("ref-gov-01", file_count=3)]
            return []

        client = MagicMock(spec=SupabaseRestClient)
        client.select.side_effect = _select
        result = get_unified_catalog(client, source_system="REFERENCE_CMS")

        self.assertNotIn("reference_form_files", tables_queried)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].channels.REFERENCE_DOWNLOAD.state, "READY")


# ---------------------------------------------------------------------------
# Router endpoint tests
# ---------------------------------------------------------------------------

class T15_RouterListEndpointStructure(unittest.TestCase):
    """FastAPI endpoint returns expected response structure."""

    def _run_list(self, **params):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from routers.document_catalog import router

        app = FastAPI()
        app.include_router(router)
        return TestClient(app).get("/api/document-catalog", params=params)

    def test_empty_response_is_200(self):
        import unittest.mock as mock
        with mock.patch(
            "routers.document_catalog._get_rest_client",
            return_value=_make_mock_client(),
        ):
            resp = self._run_list()
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("total", data)
        self.assertIn("page", data)
        self.assertIn("per_page", data)
        self.assertIn("items", data)
        self.assertEqual(data["items"], [])

    def test_items_have_required_fields(self):
        import unittest.mock as mock
        with mock.patch(
            "routers.document_catalog._get_rest_client",
            return_value=_make_mock_client(
                saas_rows=[_make_saas_row()],
                schema_rows=[],
            ),
        ):
            resp = self._run_list(source_system="SAAS")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["items"]
        self.assertEqual(len(items), 1)
        item = items[0]
        for f in ("provisional_key", "source_system", "title", "channels", "links"):
            self.assertIn(f, item, f"Missing field: {f}")
        self.assertEqual(item["links"], [])

    def test_no_raw_storage_paths_in_response(self):
        import unittest.mock as mock
        with mock.patch(
            "routers.document_catalog._get_rest_client",
            return_value=_make_mock_client(
                saas_rows=[_make_saas_row()],
                schema_rows=[],
            ),
        ):
            resp = self._run_list(source_system="SAAS")
        self.assertNotIn("storage://", resp.text)
        self.assertNotIn("supabase.co/storage", resp.text)


class T16_RouterDetailEndpointStructure(unittest.TestCase):
    """Detail endpoint returns 200 on hit, 404 on miss, 404 on invalid key."""

    def _run_detail(self, key: str, client_mock=None):
        import unittest.mock as mock
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from routers.document_catalog import router

        app = FastAPI()
        app.include_router(router)
        tc = TestClient(app, raise_server_exceptions=False)
        if client_mock is None:
            client_mock = _make_mock_client()
        with mock.patch(
            "routers.document_catalog._get_rest_client",
            return_value=client_mock,
        ):
            return tc.get(f"/api/document-catalog/{key}")

    def test_doc_key_hit(self):
        resp = self._run_detail(
            "DOC:DOC-OSH-058",
            _make_mock_client(
                saas_rows=[_make_saas_row("DOC-OSH-058")],
                schema_rows=[],
            ),
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["provisional_key"], "DOC:DOC-OSH-058")
        self.assertEqual(data["links"], [])

    def test_ref_key_hit(self):
        resp = self._run_detail(
            "REF:ref-gov-01",
            _make_mock_client(ref_rows=[_make_ref_row("ref-gov-01")]),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["provisional_key"], "REF:ref-gov-01")

    def test_doc_key_miss_404(self):
        resp = self._run_detail("DOC:DOES-NOT-EXIST", _make_mock_client(saas_rows=[]))
        self.assertEqual(resp.status_code, 404)

    def test_invalid_key_format_404(self):
        resp = self._run_detail("INVALID:key", _make_mock_client())
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        T1_SaasCandidateSchemaWebEditBlocked,
        T2_RefFormWithFilesReferenceDownloadReady,
        T3_LawGoKrUrlOfficialOriginalUnverified,
        T4_NoFileUrl,
        T5_AutoFillAlwaysBlocked,
        T6_DocKeyResolvesSaasRecord,
        T7_RefKeyResolvesRefRecord,
        T8_PaginationRespected,
        T9_SaasApprovedSchemaWebEditReady,
        T10_RefFormNoFilesBlocked,
        T11_SaasQueryUsesIsActiveFilter,
        T12_SaasQuerySelectsCorrectColumns,
        T13_RefQueryTargetsPublicView,
        T14_RefFileCountFromQaPassFiles,
        T15_RouterListEndpointStructure,
        T16_RouterDetailEndpointStructure,
    ]

    for tc in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(tc))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
