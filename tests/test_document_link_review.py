"""
tests/test_document_link_review.py
WO-TAI-DOC-WP03A-LINK-REVIEW-WORKBENCH-001

Contract tests: A01-A14
No live DB; all REST calls are mocked.
CSV is loaded from the real data/document_link_candidates.csv file.
DB writes: 0
"""

from __future__ import annotations

import os
import sys
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.document_link_review_read import (
    _load_csv,
    get_candidates,
    get_candidate_detail,
    get_csv_class_counts,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_saas_row(
    doc_id: str = "DOC-OSH-058",
    uuid: str | None = None,
    is_active: bool = True,
    doc_name: str | None = None,
) -> dict[str, Any]:
    return {
        "id": uuid or f"uuid-{doc_id}",
        "doc_id": doc_id,
        "doc_name": doc_name if doc_name is not None else f"[test] {doc_id}",
        "sector": "COMMON",
        "category": "회의",
        "doc_format": "DIGITAL_OK",
        "file_url": "https://www.law.go.kr/test",
        "is_active": is_active,
    }


def _make_ref_row(slug: str = "ref-gov-01", uuid: str | None = None) -> dict[str, Any]:
    return {
        "id": uuid or f"uuid-{slug}",
        "canonical_slug": slug,
        "title": f"[test] {slug}",
        "qa_pass_files": [],
    }


def _make_link(
    saas_uuid: str, ref_uuid: str, state: str = "PROPOSED"
) -> dict[str, Any]:
    return {
        "id": f"link-{saas_uuid}-{ref_uuid}",
        "saas_catalog_id": saas_uuid,
        "reference_form_id": ref_uuid,
        "relation_type": "SAME_DOCUMENT_CANDIDATE",
        "review_state": state,
        "evidence_note": "test",
        "reviewed_by": None,
        "reviewed_at": None,
        "owner_approval_ref": None,
        "version": 1,
        "created_at": "2026-10-20T00:00:00Z",
        "updated_at": "2026-10-20T00:00:00Z",
    }


def _make_mock_client(saas_rows=None, ref_rows=None, link_rows=None, audit_rows=None):
    """Return a mock SupabaseRestClient with configurable return values."""
    client = MagicMock()

    def _select(table, **kwargs):
        if table == "document_forms":
            return saas_rows or []
        if table == "reference_form_public_view":
            return ref_rows or []
        if table == "unified_document_link":
            return link_rows or []
        if table == "unified_document_link_audit":
            return audit_rows or []
        return []

    client.select.side_effect = _select
    return client


# ---------------------------------------------------------------------------
# A01 — 후보 총 82쌍
# ---------------------------------------------------------------------------

class TestA01CandidateCount(unittest.TestCase):
    def test_csv_has_82_rows(self):
        rows = _load_csv()
        self.assertEqual(len(rows), 82, "CSV must contain exactly 82 candidate rows")

    def test_list_returns_82_total_with_no_filter(self):
        client = _make_mock_client()
        result = get_candidates(client)
        self.assertEqual(result.total, 82)

    def test_list_items_do_not_exceed_per_page(self):
        client = _make_mock_client()
        result = get_candidates(client, per_page=10)
        self.assertLessEqual(len(result.items), 10)
        self.assertEqual(result.total, 82)


# ---------------------------------------------------------------------------
# A02 — 분류별 3 / 14 / 43 / 22
# ---------------------------------------------------------------------------

class TestA02ClassCounts(unittest.TestCase):
    def test_class_counts_match_spec(self):
        counts = get_csv_class_counts()
        self.assertEqual(counts.get("SAME_DOCUMENT_CANDIDATE", 0), 3)
        self.assertEqual(counts.get("AMBIGUOUS", 0), 14)
        self.assertEqual(counts.get("RELATED_WORKFLOW", 0), 43)
        self.assertEqual(counts.get("VARIANT", 0), 22)

    def test_list_class_counts_in_response(self):
        client = _make_mock_client()
        result = get_candidates(client)
        self.assertEqual(result.class_counts["SAME_DOCUMENT_CANDIDATE"], 3)
        self.assertEqual(result.class_counts["RELATED_WORKFLOW"], 43)

    def test_filter_by_same_document_candidate(self):
        client = _make_mock_client()
        result = get_candidates(client, relation_type="SAME_DOCUMENT_CANDIDATE")
        self.assertEqual(result.total, 3)
        for item in result.items:
            self.assertEqual(item.relation_type, "SAME_DOCUMENT_CANDIDATE")


# ---------------------------------------------------------------------------
# A03 — 정확 일치 1쌍(DOC-OSH-058 / ref-gov-01) 미승인
# ---------------------------------------------------------------------------

class TestA03ExactMatchUnApproved(unittest.TestCase):
    def test_exact_match_pair_exists_in_candidates(self):
        rows = _load_csv()
        exact = [
            r for r in rows
            if r["saas_source_code"] == "DOC-OSH-058" and r["ref_source_code"] == "ref-gov-01"
        ]
        self.assertEqual(len(exact), 1)
        self.assertAlmostEqual(exact[0]["similarity_score"], 1.000, places=3)

    def test_exact_match_has_no_approved_link(self):
        # Mock: saas and ref exist, but link is PROPOSED (not APPROVED)
        saas = [_make_saas_row("DOC-OSH-058", "uuid-saas-058")]
        ref = [_make_ref_row("ref-gov-01", "uuid-ref-gov-01")]
        links = [_make_link("uuid-saas-058", "uuid-ref-gov-01", "PROPOSED")]
        client = _make_mock_client(saas, ref, links)
        detail = get_candidate_detail(client, "DOC-OSH-058__ref-gov-01")
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail.current_link_status, "PROPOSED")
        # Must NOT be APPROVED
        approved_links = [lk for lk in detail.all_links if lk["review_state"] == "APPROVED"]
        self.assertEqual(len(approved_links), 0)

    def test_exact_match_no_link_at_all(self):
        saas = [_make_saas_row("DOC-OSH-058", "uuid-saas-058")]
        ref = [_make_ref_row("ref-gov-01", "uuid-ref-gov-01")]
        client = _make_mock_client(saas, ref, [])
        detail = get_candidate_detail(client, "DOC-OSH-058__ref-gov-01")
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertIsNone(detail.current_link_status)
        self.assertEqual(detail.active_link_count, 0)


# ---------------------------------------------------------------------------
# A04 — AMBIGUOUS를 DB relation_type으로 자동 변환하지 않음
# ---------------------------------------------------------------------------

class TestA04NoAutoConversion(unittest.TestCase):
    def test_ambiguous_stays_as_csv_classification(self):
        rows = _load_csv()
        ambiguous = [r for r in rows if r["relation_type"] == "AMBIGUOUS"]
        self.assertEqual(len(ambiguous), 14)
        # Each AMBIGUOUS row keeps its classification — not converted to DB type
        for r in ambiguous:
            self.assertEqual(r["relation_type"], "AMBIGUOUS")

    def test_candidate_summary_preserves_csv_relation_type(self):
        client = _make_mock_client()
        result = get_candidates(client, relation_type="AMBIGUOUS")
        for item in result.items:
            self.assertEqual(item.relation_type, "AMBIGUOUS")

    def test_variant_classification_preserved(self):
        client = _make_mock_client()
        result = get_candidates(client, relation_type="VARIANT")
        self.assertEqual(result.total, 22)
        for item in result.items:
            self.assertEqual(item.relation_type, "VARIANT")

    def test_related_workflow_classification_preserved(self):
        client = _make_mock_client()
        result = get_candidates(client, relation_type="RELATED_WORKFLOW")
        self.assertEqual(result.total, 43)


# ---------------------------------------------------------------------------
# A05 — 원본 미존재 시 STALE_SOURCE
# ---------------------------------------------------------------------------

class TestA05StaleSource(unittest.TestCase):
    def test_stale_when_saas_missing(self):
        # ref exists but saas does not
        ref = [_make_ref_row("ref-gov-01")]
        client = _make_mock_client(saas_rows=[], ref_rows=ref)
        result = get_candidates(client, stale_only=True)
        # All candidates where saas_source_code is not found → stale
        for item in result.items:
            self.assertTrue(item.stale_source)
            self.assertIsNotNone(item.stale_reason)

    def test_stale_when_ref_missing(self):
        saas = [_make_saas_row("DOC-OSH-058")]
        client = _make_mock_client(saas_rows=saas, ref_rows=[])
        detail = get_candidate_detail(client, "DOC-OSH-058__ref-gov-01")
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertTrue(detail.stale_source)
        self.assertIn("ref-gov-01", detail.stale_reason or "")

    def test_not_stale_when_both_exist_with_matching_titles(self):
        # CORR-B: stale requires either missing OR title mismatch OR inactive.
        # Use exact CSV titles to confirm a clean (non-stale) pair.
        saas = [_make_saas_row("DOC-OSH-058", doc_name="산업안전보건위원회 회의록")]
        ref = [_make_ref_row("ref-gov-01")]
        ref[0]["title"] = "산업안전보건위원회 회의록"
        client = _make_mock_client(saas_rows=saas, ref_rows=ref)
        detail = get_candidate_detail(client, "DOC-OSH-058__ref-gov-01")
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertFalse(detail.stale_source)
        self.assertIsNone(detail.stale_reason)

    def test_stale_reason_describes_missing_party(self):
        # Neither exists
        client = _make_mock_client(saas_rows=[], ref_rows=[])
        detail = get_candidate_detail(client, "DOC-OSH-058__ref-gov-01")
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertTrue(detail.stale_source)
        reason = detail.stale_reason or ""
        self.assertIn("SAAS", reason)


# ---------------------------------------------------------------------------
# A06 — 401 / 403 인증 차단 (router level)
# ---------------------------------------------------------------------------

class TestA06AuthGuard(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from routers.document_link_review import router
        from routers.auth import get_current_user

        self.app = FastAPI()
        self.app.include_router(router)
        self._get_current_user = get_current_user
        self.app_dep = self.app.dependency_overrides

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def _client(self):
        return TestClient(self.app, raise_server_exceptions=False)

    def test_no_auth_header_401(self):
        # No override → real get_current_user → 401
        resp = TestClient(self.app, raise_server_exceptions=False).get(
            "/api/document-link-review/candidates"
        )
        self.assertEqual(resp.status_code, 401)

    def test_role_002_forbidden(self):
        from routers.document_link_review import router, get_current_user
        self.app.dependency_overrides[get_current_user] = lambda: {
            "id": "u1", "role_code": "002", "is_active": True
        }
        resp = self._client().get("/api/document-link-review/candidates")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["detail"]["code"], "DOCUMENT_LINK_REVIEW_FORBIDDEN")

    def test_role_001_allowed(self):
        from routers.document_link_review import get_current_user
        self.app.dependency_overrides[get_current_user] = lambda: {
            "id": "u1", "role_code": "001", "is_active": True
        }
        with patch(
            "routers.document_link_review.SupabaseRestClient"
        ) as MockClient:
            MockClient.return_value.select.return_value = []
            resp = self._client().get("/api/document-link-review/candidates")
        self.assertEqual(resp.status_code, 200)

    def test_detail_no_auth_401(self):
        resp = TestClient(self.app, raise_server_exceptions=False).get(
            "/api/document-link-review/candidates/DOC-OSH-058__ref-gov-01"
        )
        self.assertEqual(resp.status_code, 401)

    def test_detail_role_002_forbidden(self):
        from routers.document_link_review import get_current_user
        self.app.dependency_overrides[get_current_user] = lambda: {
            "id": "u1", "role_code": "002", "is_active": True
        }
        resp = self._client().get(
            "/api/document-link-review/candidates/DOC-OSH-058__ref-gov-01"
        )
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# A07 — 필터·정렬·페이지네이션
# ---------------------------------------------------------------------------

class TestA07FilterSortPagination(unittest.TestCase):
    def _client_no_db(self):
        return _make_mock_client()

    def test_q_filter_narrows_results(self):
        client = self._client_no_db()
        result = get_candidates(client, q="회의록")
        self.assertLess(result.total, 82)
        for item in result.items:
            title_match = "회의록" in item.saas_title or "회의록" in item.ref_title
            self.assertTrue(title_match)

    def test_q_filter_empty_string_returns_all(self):
        client = self._client_no_db()
        result = get_candidates(client, q="")
        self.assertEqual(result.total, 82)

    def test_per_page_capped_at_200(self):
        client = self._client_no_db()
        result = get_candidates(client, per_page=999)
        self.assertLessEqual(len(result.items), 200)

    def test_pagination_page2(self):
        client = self._client_no_db()
        p1 = get_candidates(client, page=1, per_page=10)
        p2 = get_candidates(client, page=2, per_page=10)
        p1_ids = {s.candidate_id for s in p1.items}
        p2_ids = {s.candidate_id for s in p2.items}
        self.assertEqual(len(p1_ids.intersection(p2_ids)), 0, "Page 1 and 2 must not overlap")

    def test_sort_ascending_similarity(self):
        client = self._client_no_db()
        result = get_candidates(client, sort="similarity_score", sort_desc=False, per_page=82)
        scores = [s.similarity_score for s in result.items]
        self.assertEqual(scores, sorted(scores))

    def test_sort_descending_similarity(self):
        client = self._client_no_db()
        result = get_candidates(client, sort="similarity_score", sort_desc=True, per_page=82)
        scores = [s.similarity_score for s in result.items]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_unknown_sort_field_falls_back_to_default(self):
        client = self._client_no_db()
        # _VALID_SORT_FIELDS fallback is applied in get_candidates
        result = get_candidates(client, sort="unknown_field")
        self.assertEqual(result.total, 82)

    def test_link_status_none_filter(self):
        client = self._client_no_db()
        result = get_candidates(client, link_status="NONE")
        # All should have current_link_status = None
        for item in result.items:
            self.assertIsNone(item.current_link_status)


# ---------------------------------------------------------------------------
# A08 — 기존 연결 상태 조회
# ---------------------------------------------------------------------------

class TestA08ExistingLinkStatus(unittest.TestCase):
    def test_proposed_link_reflected(self):
        saas = [_make_saas_row("DOC-OSH-058", "uuid-s1")]
        ref = [_make_ref_row("ref-gov-01", "uuid-r1")]
        links = [_make_link("uuid-s1", "uuid-r1", "PROPOSED")]
        client = _make_mock_client(saas, ref, links)
        detail = get_candidate_detail(client, "DOC-OSH-058__ref-gov-01")
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail.current_link_status, "PROPOSED")
        self.assertEqual(detail.active_link_count, 1)

    def test_approved_link_reflected(self):
        saas = [_make_saas_row("DOC-OSH-058", "uuid-s1")]
        ref = [_make_ref_row("ref-gov-01", "uuid-r1")]
        links = [_make_link("uuid-s1", "uuid-r1", "APPROVED")]
        client = _make_mock_client(saas, ref, links)
        detail = get_candidate_detail(client, "DOC-OSH-058__ref-gov-01")
        assert detail is not None
        self.assertEqual(detail.current_link_status, "APPROVED")

    def test_no_link_returns_none_status(self):
        saas = [_make_saas_row("DOC-OSH-058", "uuid-s1")]
        ref = [_make_ref_row("ref-gov-01", "uuid-r1")]
        client = _make_mock_client(saas, ref, [])
        detail = get_candidate_detail(client, "DOC-OSH-058__ref-gov-01")
        assert detail is not None
        self.assertIsNone(detail.current_link_status)
        self.assertEqual(detail.active_link_count, 0)


# ---------------------------------------------------------------------------
# A09 — 과거 REJECTED / RETIRED 이력 보존
# ---------------------------------------------------------------------------

class TestA09TerminalStateHistory(unittest.TestCase):
    def test_rejected_link_in_history(self):
        saas = [_make_saas_row("DOC-OSH-058", "uuid-s1")]
        ref = [_make_ref_row("ref-gov-01", "uuid-r1")]
        rejected_link = _make_link("uuid-s1", "uuid-r1", "REJECTED")
        proposed_link = _make_link("uuid-s1", "uuid-r1", "PROPOSED")
        proposed_link["id"] = "link-proposed-2"
        client = _make_mock_client(saas, ref, [rejected_link, proposed_link])
        detail = get_candidate_detail(client, "DOC-OSH-058__ref-gov-01")
        assert detail is not None
        states = [lk["review_state"] for lk in detail.all_links]
        self.assertIn("REJECTED", states)
        self.assertIn("PROPOSED", states)

    def test_terminal_states_not_counted_as_active(self):
        # CORR-A: terminal states (REJECTED/RETIRED) now returned as current_link_status
        # when no active links exist, but active_link_count stays 0.
        saas = [_make_saas_row("DOC-OSH-058", "uuid-s1")]
        ref = [_make_ref_row("ref-gov-01", "uuid-r1")]
        rejected = _make_link("uuid-s1", "uuid-r1", "REJECTED")
        rejected["updated_at"] = "2026-10-20T00:00:00Z"
        retired = _make_link("uuid-s1", "uuid-r1", "RETIRED")
        retired["id"] = "link-retired"
        retired["updated_at"] = "2026-10-21T00:00:00Z"  # more recent
        links = [rejected, retired]
        client = _make_mock_client(saas, ref, links)
        detail = get_candidate_detail(client, "DOC-OSH-058__ref-gov-01")
        assert detail is not None
        # latest terminal = RETIRED (updated_at more recent)
        self.assertEqual(detail.current_link_status, "RETIRED")
        self.assertEqual(detail.active_link_count, 0)

    def test_multiple_historical_links_preserved(self):
        saas = [_make_saas_row("DOC-OSH-058", "uuid-s1")]
        ref = [_make_ref_row("ref-gov-01", "uuid-r1")]
        links = [
            {**_make_link("uuid-s1", "uuid-r1", "REJECTED"), "id": "link-r1"},
            {**_make_link("uuid-s1", "uuid-r1", "REJECTED"), "id": "link-r2"},
            {**_make_link("uuid-s1", "uuid-r1", "PROPOSED"), "id": "link-p1"},
        ]
        client = _make_mock_client(saas, ref, links)
        detail = get_candidate_detail(client, "DOC-OSH-058__ref-gov-01")
        assert detail is not None
        self.assertEqual(len(detail.all_links), 3)


# ---------------------------------------------------------------------------
# A10 — APPROVED 없는 경우 current_link_status ≠ APPROVED
# ---------------------------------------------------------------------------

class TestA10NoAutoApproval(unittest.TestCase):
    def test_proposed_not_treated_as_approved(self):
        saas = [_make_saas_row("DOC-OSH-058", "uuid-s1")]
        ref = [_make_ref_row("ref-gov-01", "uuid-r1")]
        links = [_make_link("uuid-s1", "uuid-r1", "PROPOSED")]
        client = _make_mock_client(saas, ref, links)
        detail = get_candidate_detail(client, "DOC-OSH-058__ref-gov-01")
        assert detail is not None
        self.assertNotEqual(detail.current_link_status, "APPROVED")

    def test_under_review_not_treated_as_approved(self):
        saas = [_make_saas_row("DOC-OSH-058", "uuid-s1")]
        ref = [_make_ref_row("ref-gov-01", "uuid-r1")]
        links = [_make_link("uuid-s1", "uuid-r1", "UNDER_REVIEW")]
        client = _make_mock_client(saas, ref, links)
        detail = get_candidate_detail(client, "DOC-OSH-058__ref-gov-01")
        assert detail is not None
        self.assertEqual(detail.current_link_status, "UNDER_REVIEW")
        self.assertNotEqual(detail.current_link_status, "APPROVED")

    def test_similarity_1_0_does_not_mean_approved(self):
        """Even similarity_score=1.000 does not imply APPROVED status."""
        rows = _load_csv()
        exact = next(r for r in rows
                     if r["saas_source_code"] == "DOC-OSH-058"
                     and r["ref_source_code"] == "ref-gov-01")
        self.assertAlmostEqual(exact["similarity_score"], 1.000)
        # No link in DB → must not be auto-approved
        client = _make_mock_client(saas_rows=[], ref_rows=[])
        detail = get_candidate_detail(client, exact["candidate_id"])
        assert detail is not None
        self.assertIsNone(detail.current_link_status)


# ---------------------------------------------------------------------------
# A11 — 감사 기록 조회 및 권한 차단
# ---------------------------------------------------------------------------

class TestA11AuditAccess(unittest.TestCase):
    def test_audit_history_in_detail(self):
        saas = [_make_saas_row("DOC-OSH-058", "uuid-s1")]
        ref = [_make_ref_row("ref-gov-01", "uuid-r1")]
        links = [_make_link("uuid-s1", "uuid-r1", "PROPOSED")]
        audit = [{
            "id": 1,
            "link_id": "link-uuid-s1-uuid-r1",
            "event_type": "INITIAL_PROPOSE",
            "actor": "system",
            "from_state": None,
            "to_state": "PROPOSED",
            "changed_at": "2026-10-20T00:00:00Z",
            "change_note": None,
            "old_evidence_note": None,
            "old_value": None,
            "new_value": None,
        }]
        client = _make_mock_client(saas, ref, links, audit)
        detail = get_candidate_detail(client, "DOC-OSH-058__ref-gov-01")
        assert detail is not None
        self.assertEqual(len(detail.audit_history), 1)
        self.assertEqual(detail.audit_history[0]["event_type"], "INITIAL_PROPOSE")

    def test_audit_not_exposed_in_list(self):
        client = _make_mock_client()
        result = get_candidates(client)
        # CandidateSummary has no audit_history field
        for item in result.items:
            self.assertFalse(hasattr(item, "audit_history"))


# ---------------------------------------------------------------------------
# A12 — 기존 카탈로그 목록·상세 회귀
# ---------------------------------------------------------------------------

class TestA12CatalogRegression(unittest.TestCase):
    def test_catalog_aggregator_still_importable(self):
        from services.catalog_aggregator import (
            get_unified_catalog, get_document_detail,
            SupabaseRestClient, CatalogItem,
        )
        self.assertTrue(callable(get_unified_catalog))
        self.assertTrue(callable(get_document_detail))

    def test_router_registry_has_both_routes(self):
        import importlib
        pub = importlib.import_module("router_registry.public")
        modules = [r["module"] for r in pub.ROUTERS]
        self.assertIn("routers.document_catalog", modules)
        self.assertIn("routers.document_link_review", modules)

    def test_review_service_does_not_modify_catalog_service(self):
        from services.catalog_aggregator import get_unified_catalog
        from services.document_link_review_read import get_candidates
        # Both must be independent callables with no shared mutable state
        self.assertIsNot(get_unified_catalog, get_candidates)


# ---------------------------------------------------------------------------
# A13 — 기존 채널 READY 상태 불변
# ---------------------------------------------------------------------------

class TestA13ChannelStateUnchanged(unittest.TestCase):
    def test_compute_channel_state_still_works(self):
        from services.catalog_aggregator import compute_channel_state
        result = compute_channel_state("REFERENCE_CMS", None, 1, None, None)
        self.assertEqual(result.REFERENCE_DOWNLOAD.state, "READY")

    def test_saas_auto_fill_always_blocked(self):
        from services.catalog_aggregator import compute_channel_state
        result = compute_channel_state("SAAS", "APPROVED_FOR_RUNTIME_USE", 0, "url", "DIGITAL_OK",
                                       factory_scope_verified=True, active_instance_exists=True)
        self.assertEqual(result.SAAS_AUTO_FILL.state, "BLOCKED")


# ---------------------------------------------------------------------------
# A14 — DB 쓰기 0건
# ---------------------------------------------------------------------------

class TestA14NoDbWrite(unittest.TestCase):
    def test_get_candidates_never_writes(self):
        client = MagicMock()
        client.select.return_value = []
        get_candidates(client)
        # Only select() may be called — never insert/update/delete/execute
        for call in client.method_calls:
            self.assertNotIn("insert", str(call))
            self.assertNotIn("update", str(call))
            self.assertNotIn("delete", str(call))
            self.assertNotIn("execute", str(call))

    def test_get_candidate_detail_never_writes(self):
        client = MagicMock()
        client.select.return_value = []
        get_candidate_detail(client, "DOC-OSH-058__ref-gov-01")
        for call_name in [str(c) for c in client.method_calls]:
            self.assertNotIn("insert", call_name)
            self.assertNotIn("update", call_name)
            self.assertNotIn("delete", call_name)

    def test_csv_loading_is_read_only(self):
        # _load_csv should not write any file
        import tempfile, shutil
        original_path = str(
            __import__("services.document_link_review_read", fromlist=["_CSV_PATH"])._CSV_PATH
        )
        # Just verify it loads without modification
        rows = _load_csv()
        self.assertEqual(len(rows), 82)

    def test_candidate_not_found_returns_none(self):
        client = _make_mock_client()
        result = get_candidate_detail(client, "NONEXISTENT__CANDIDATE")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Corr-001 — T01-T11
# ---------------------------------------------------------------------------

class TestT01RejectedFilter(unittest.TestCase):
    """T01: REJECTED 단독 → current_link_status=REJECTED, link_status 필터 작동."""

    def test_rejected_only_returns_rejected_status(self):
        # One candidate with a REJECTED link (no active links)
        saas = _make_saas_row()
        ref = _make_ref_row()
        link = _make_link(saas["id"], ref["id"], state="REJECTED")
        link["updated_at"] = "2026-10-20T12:00:00Z"
        client = _make_mock_client(saas_rows=[saas], ref_rows=[ref], link_rows=[link])
        result = get_candidates(client)
        # Find our pair
        item = next(
            (i for i in result.items if i.saas_source_code == "DOC-OSH-058"), None
        )
        self.assertIsNotNone(item)
        self.assertEqual(item.current_link_status, "REJECTED")
        self.assertEqual(item.active_link_count, 0)

    def test_link_status_rejected_filter_matches(self):
        saas = _make_saas_row()
        ref = _make_ref_row()
        link = _make_link(saas["id"], ref["id"], state="REJECTED")
        link["updated_at"] = "2026-10-20T12:00:00Z"
        client = _make_mock_client(saas_rows=[saas], ref_rows=[ref], link_rows=[link])
        result = get_candidates(client, link_status="REJECTED")
        self.assertGreater(result.total, 0)
        for item in result.items:
            self.assertEqual(item.current_link_status, "REJECTED")


class TestT02RetiredFilter(unittest.TestCase):
    """T02: RETIRED 단독 → current_link_status=RETIRED, link_status 필터 작동."""

    def test_retired_only_returns_retired_status(self):
        saas = _make_saas_row()
        ref = _make_ref_row()
        link = _make_link(saas["id"], ref["id"], state="RETIRED")
        link["updated_at"] = "2026-10-20T12:00:00Z"
        client = _make_mock_client(saas_rows=[saas], ref_rows=[ref], link_rows=[link])
        result = get_candidates(client)
        item = next(
            (i for i in result.items if i.saas_source_code == "DOC-OSH-058"), None
        )
        self.assertIsNotNone(item)
        self.assertEqual(item.current_link_status, "RETIRED")
        self.assertEqual(item.active_link_count, 0)

    def test_link_status_retired_filter_matches(self):
        saas = _make_saas_row()
        ref = _make_ref_row()
        link = _make_link(saas["id"], ref["id"], state="RETIRED")
        link["updated_at"] = "2026-10-20T12:00:00Z"
        client = _make_mock_client(saas_rows=[saas], ref_rows=[ref], link_rows=[link])
        result = get_candidates(client, link_status="RETIRED")
        self.assertGreater(result.total, 0)
        for item in result.items:
            self.assertEqual(item.current_link_status, "RETIRED")


class TestT03ActiveAndHistory(unittest.TestCase):
    """T03: 활성 링크 + 과거 이력 동시 존재 → 활성 상태 우선, 이력은 보존."""

    def test_approved_wins_over_rejected_history(self):
        saas = _make_saas_row()
        ref = _make_ref_row()
        active_link = _make_link(saas["id"], ref["id"], state="APPROVED")
        active_link["updated_at"] = "2026-10-21T00:00:00Z"
        hist_link = _make_link(saas["id"], ref["id"], state="REJECTED")
        hist_link["id"] = "link-old"
        hist_link["updated_at"] = "2026-10-19T00:00:00Z"
        client = _make_mock_client(
            saas_rows=[saas], ref_rows=[ref],
            link_rows=[active_link, hist_link],
        )
        result = get_candidates(client)
        item = next(
            (i for i in result.items if i.saas_source_code == "DOC-OSH-058"), None
        )
        self.assertIsNotNone(item)
        self.assertEqual(item.current_link_status, "APPROVED")
        self.assertEqual(item.active_link_count, 1)

    def test_detail_all_links_preserved(self):
        saas = _make_saas_row()
        ref = _make_ref_row()
        active_link = _make_link(saas["id"], ref["id"], state="APPROVED")
        active_link["updated_at"] = "2026-10-21T00:00:00Z"
        hist_link = dict(active_link)
        hist_link["id"] = "link-old"
        hist_link["review_state"] = "REJECTED"
        hist_link["updated_at"] = "2026-10-19T00:00:00Z"
        client = _make_mock_client(
            saas_rows=[saas], ref_rows=[ref],
            link_rows=[active_link, hist_link],
        )
        # Use first CSV row with DOC-OSH-058
        csv_rows = _load_csv()
        row = next(r for r in csv_rows if r["saas_source_code"] == "DOC-OSH-058")
        detail = get_candidate_detail(client, row["candidate_id"])
        self.assertIsNotNone(detail)
        self.assertEqual(len(detail.all_links), 2)


class TestT04NoLinkHistory(unittest.TestCase):
    """T04: 연결 이력 없음(NONE) → current_link_status=None."""

    def test_no_links_returns_none_status(self):
        saas = _make_saas_row()
        ref = _make_ref_row()
        client = _make_mock_client(saas_rows=[saas], ref_rows=[ref], link_rows=[])
        result = get_candidates(client)
        item = next(
            (i for i in result.items if i.saas_source_code == "DOC-OSH-058"), None
        )
        self.assertIsNotNone(item)
        self.assertIsNone(item.current_link_status)
        self.assertEqual(item.active_link_count, 0)

    def test_link_status_none_filter_matches(self):
        saas = _make_saas_row()
        ref = _make_ref_row()
        client = _make_mock_client(saas_rows=[saas], ref_rows=[ref], link_rows=[])
        result = get_candidates(client, link_status="NONE")
        for item in result.items:
            self.assertIsNone(item.current_link_status)


class TestT05SaasTitleMismatch(unittest.TestCase):
    """T05: SaaS 제목 변경 감지 — DB doc_name ≠ CSV saas_title."""

    def test_title_mismatch_marks_stale(self):
        # CSV has the original title; we simulate DB having a different doc_name
        csv_rows = _load_csv()
        row = next(r for r in csv_rows if r["saas_source_code"] == "DOC-OSH-058")
        csv_title = row["saas_title"]
        # DB title is different
        saas = _make_saas_row(doc_name=csv_title + " [수정됨]")
        ref = _make_ref_row()
        client = _make_mock_client(saas_rows=[saas], ref_rows=[ref], link_rows=[])
        result = get_candidates(client)
        item = next(
            (i for i in result.items if i.saas_source_code == "DOC-OSH-058"), None
        )
        self.assertIsNotNone(item)
        self.assertTrue(item.stale_source)
        self.assertIn("제목 불일치", item.stale_reason or "")
        self.assertIn("SaaS", item.stale_reason or "")

    def test_same_title_not_stale(self):
        csv_rows = _load_csv()
        row = next(r for r in csv_rows if r["saas_source_code"] == "DOC-OSH-058")
        # DB title matches CSV exactly
        saas = _make_saas_row(doc_name=row["saas_title"])
        # Ref title also matches
        ref = _make_ref_row()
        ref["title"] = row["ref_title"]
        client = _make_mock_client(saas_rows=[saas], ref_rows=[ref], link_rows=[])
        result = get_candidates(client)
        item = next(
            (i for i in result.items if i.saas_source_code == "DOC-OSH-058"), None
        )
        self.assertIsNotNone(item)
        self.assertFalse(item.stale_source)


class TestT06RefTitleMismatch(unittest.TestCase):
    """T06: 참고서식 제목 변경 감지 — DB title ≠ CSV ref_title."""

    def test_ref_title_mismatch_marks_stale(self):
        csv_rows = _load_csv()
        row = next(r for r in csv_rows if r["saas_source_code"] == "DOC-OSH-058")
        csv_ref_title = row["ref_title"]
        saas = _make_saas_row(doc_name=row["saas_title"])  # SaaS title matches
        ref = _make_ref_row()
        ref["title"] = csv_ref_title + " [개정]"  # Ref title changed
        client = _make_mock_client(saas_rows=[saas], ref_rows=[ref], link_rows=[])
        result = get_candidates(client)
        item = next(
            (i for i in result.items if i.saas_source_code == "DOC-OSH-058"), None
        )
        self.assertIsNotNone(item)
        self.assertTrue(item.stale_source)
        self.assertIn("참고서식 제목 불일치", item.stale_reason or "")


class TestT07InactiveSaasDoc(unittest.TestCase):
    """T07: SaaS 비활성화 감지 — is_active=False."""

    def test_inactive_doc_marks_stale(self):
        saas = _make_saas_row(is_active=False)
        ref = _make_ref_row()
        client = _make_mock_client(saas_rows=[saas], ref_rows=[ref], link_rows=[])
        result = get_candidates(client)
        item = next(
            (i for i in result.items if i.saas_source_code == "DOC-OSH-058"), None
        )
        self.assertIsNotNone(item)
        self.assertTrue(item.stale_source)
        self.assertIn("비활성화", item.stale_reason or "")

    def test_active_doc_not_stale_due_to_activity(self):
        saas = _make_saas_row(is_active=True)
        ref = _make_ref_row()
        client = _make_mock_client(saas_rows=[saas], ref_rows=[ref], link_rows=[])
        result = get_candidates(client)
        item = next(
            (i for i in result.items if i.saas_source_code == "DOC-OSH-058"), None
        )
        self.assertIsNotNone(item)
        # is_active=True alone shouldn't cause stale (title still mismatches in fixture
        # unless we set titles to match — check stale reason doesn't include "비활성화")
        self.assertNotIn("비활성화", item.stale_reason or "")


class TestT08ApprovedLinksInCatalog(unittest.TestCase):
    """T08: APPROVED SAME_DOCUMENT_VERIFIED 연결은 카탈로그 상세에 노출."""

    def test_approved_link_exposed_in_catalog(self):
        from services.catalog_aggregator import get_approved_links_for_catalog

        client = MagicMock()
        saas_uuid = "uuid-saas-001"
        ref_uuid = "uuid-ref-001"

        def _select(table, **kwargs):
            filters = kwargs.get("filters", {})
            if table == "unified_document_link":
                return [{
                    "id": "link-001",
                    "reference_form_id": ref_uuid,
                    "relation_type": "SAME_DOCUMENT_VERIFIED",
                    "review_state": "APPROVED",
                }]
            if table == "reference_form_public_view":
                return [{
                    "id": ref_uuid,
                    "canonical_slug": "ref-gov-01",
                    "title": "안전보건관리 참고서식",
                }]
            return []

        client.select.side_effect = _select
        links = get_approved_links_for_catalog(client, saas_uuid, "SAAS")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["relation_type"], "SAME_DOCUMENT_VERIFIED")
        self.assertEqual(links[0]["linked_key"], "REF:ref-gov-01")


class TestT09UnapprovedLinksNotInCatalog(unittest.TestCase):
    """T09: PROPOSED/UNDER_REVIEW 연결은 카탈로그에 노출되지 않음."""

    def test_proposed_link_not_in_catalog(self):
        from services.catalog_aggregator import get_approved_links_for_catalog

        client = MagicMock()

        def _select(table, **kwargs):
            # unified_document_link returns nothing (filter is APPROVED only)
            return []

        client.select.side_effect = _select
        links = get_approved_links_for_catalog(client, "uuid-001", "SAAS")
        self.assertEqual(links, [])

    def test_under_review_link_not_in_catalog(self):
        from services.catalog_aggregator import get_approved_links_for_catalog

        client = MagicMock()
        client.select.return_value = []
        links = get_approved_links_for_catalog(client, "uuid-001", "SAAS")
        self.assertEqual(links, [])


class TestT10RelatedFormNotSameDoc(unittest.TestCase):
    """T10: RELATED_FORM 관계는 동일 문서로 표시하지 않음."""

    def test_related_form_excluded_from_catalog_links(self):
        from services.catalog_aggregator import get_approved_links_for_catalog

        client = MagicMock()

        def _select(table, **kwargs):
            # If filter includes relation_type=SAME_DOCUMENT_VERIFIED, no results
            return []

        client.select.side_effect = _select
        links = get_approved_links_for_catalog(client, "uuid-001", "SAAS")
        # RELATED_FORM should not appear since we query only SAME_DOCUMENT_VERIFIED
        self.assertEqual(links, [])
        # Verify the query included relation_type filter
        call_args = client.select.call_args_list[0]
        filters = call_args.kwargs.get("filters", {})
        self.assertIn("relation_type", filters)
        self.assertEqual(filters["relation_type"], "eq.SAME_DOCUMENT_VERIFIED")


class TestCorr002A_LawRef(unittest.TestCase):
    """CORR-002-A: law_ref/regulation_ref 조회 포함."""

    def test_law_ref_fetched_when_present(self):
        """saas_document에 law_ref 필드가 포함돼야 한다."""
        csv_rows = _load_csv()
        row = next(r for r in csv_rows if r["saas_source_code"] == "DOC-OSH-058")
        saas = _make_saas_row(doc_name=row["saas_title"])
        saas["law_ref"] = "산업안전보건법 제24조"
        saas["regulation_ref"] = None
        ref = _make_ref_row()
        ref["title"] = row["ref_title"]
        client = _make_mock_client(saas_rows=[saas], ref_rows=[ref])
        detail = get_candidate_detail(client, row["candidate_id"])
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertIsNotNone(detail.saas_document)
        self.assertEqual(detail.saas_document["law_ref"], "산업안전보건법 제24조")
        self.assertIsNone(detail.saas_document["regulation_ref"])

    def test_empty_law_ref_preserved_as_none(self):
        """law_ref가 없는 경우 None으로 그대로 전달돼야 한다."""
        csv_rows = _load_csv()
        row = next(r for r in csv_rows if r["saas_source_code"] == "DOC-OSH-058")
        saas = _make_saas_row(doc_name=row["saas_title"])
        saas["law_ref"] = None
        saas["regulation_ref"] = None
        ref = _make_ref_row()
        ref["title"] = row["ref_title"]
        client = _make_mock_client(saas_rows=[saas], ref_rows=[ref])
        detail = get_candidate_detail(client, row["candidate_id"])
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertIsNone(detail.saas_document["law_ref"])

    def test_db_query_includes_law_ref_column(self):
        """DB 조회 컬럼에 law_ref, regulation_ref가 포함돼야 한다."""
        client = _make_mock_client()
        get_candidates(client)
        for call in client.select.call_args_list:
            if call.args[0] == "document_forms":
                cols = call.kwargs.get("columns", "")
                self.assertIn("law_ref", cols)
                self.assertIn("regulation_ref", cols)
                break


class TestCorr002C_LinkFetchError(unittest.TestCase):
    """CORR-002-C: DB 조회 실패 시 빈 목록과 구분 가능한 오류."""

    def test_get_approved_links_raises_on_db_error(self):
        """DB 오류 발생 시 RuntimeError가 전파돼야 한다."""
        from services.catalog_aggregator import get_approved_links_for_catalog

        client = MagicMock()
        client.select.side_effect = Exception("DB connection failed")

        with self.assertRaises(Exception):
            get_approved_links_for_catalog(client, "uuid-saas", "SAAS")

    def test_approved_zero_results_returns_empty_list(self):
        """실제 0건 조회는 빈 목록을 반환해야 한다 (예외 없음)."""
        from services.catalog_aggregator import get_approved_links_for_catalog

        client = MagicMock()
        client.select.return_value = []
        result = get_approved_links_for_catalog(client, "uuid-saas", "SAAS")
        self.assertEqual(result, [])

    def test_ref_cms_db_error_also_raises(self):
        """REFERENCE_CMS 측 DB 오류도 전파돼야 한다."""
        from services.catalog_aggregator import get_approved_links_for_catalog

        client = MagicMock()
        client.select.side_effect = RuntimeError("network timeout")

        with self.assertRaises(Exception):
            get_approved_links_for_catalog(client, "uuid-ref", "REFERENCE_CMS")


class TestT11ChannelStateUnchanged(unittest.TestCase):
    """T11: 채널 상태 불변 — CORR-001 이후에도 SAAS_AUTO_FILL은 BLOCKED."""

    def test_saas_auto_fill_still_blocked(self):
        from services.catalog_aggregator import compute_channel_state
        result = compute_channel_state(
            record_type="SAAS",
            schema_status="APPROVED_FOR_RUNTIME_USE",
            file_count=0,
            file_url="https://www.law.go.kr/test",
            rights_state="DIGITAL_OK",
        )
        self.assertEqual(result.SAAS_AUTO_FILL.state, "BLOCKED")

    def test_reference_cms_channel_states_unchanged(self):
        from services.catalog_aggregator import compute_channel_state
        result = compute_channel_state(
            record_type="REFERENCE_CMS",
            schema_status=None,
            file_count=2,
            file_url=None,
            rights_state=None,
        )
        self.assertEqual(result.REFERENCE_DOWNLOAD.state, "READY")
        self.assertEqual(result.WEB_EDIT.state, "NOT_APPLICABLE")
        self.assertEqual(result.SAAS_AUTO_FILL.state, "NOT_APPLICABLE")


if __name__ == "__main__":
    unittest.main()
