"""F3 Shared Retrieval Engine Tests — WO-TAI-SHARED-SEARCH-F3 §52-§53.

Test classification:
  KEEP    — query validation, result contract, visibility, dedup, pagination,
            API contract, CSI/CHEM readiness (adapted to OpenSearch tier names)
  REWRITE — FTS/TRIGRAM tests → BM25_NORI/FUZZY_FALLBACK, SupabaseSearchReader tests
  ADD     — OpenSearch mapping, Nori analysis, _msearch tier mapping, BM25,
            fuzzy fallback, bulk rebuild, alias promotion, rollback, 503 runtime config

Uses MemorySearchReader for unit tests.
Integration tests (§48) are in test_shared_search_f3_opensearch_integration.py.
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

# --------------------------------------------------------------------------
# Services under test
# --------------------------------------------------------------------------
from services.shared_search.query import (
    TIER_ALIAS_EXACT,
    TIER_BM25_NORI,
    TIER_CANONICAL_ID_EXACT,
    TIER_CONTEXT_EXACT,
    TIER_DICTIONARY_EXACT,
    TIER_DICTIONARY_EXPANSION,
    TIER_FUZZY_FALLBACK,
    TIER_PRECEDENCE,
    TIER_SOURCE_KEY_EXACT,
    TIER_SUBJECT_EXACT,
    TIER_TITLE_EXACT,
    SubjectCandidate,
    build_query_plan,
)
from services.shared_search.result import SearchResponse, SearchResult
from services.shared_search.retrieval import (
    MemorySearchReader,
    SharedRetrievalEngine,
    retrieve,
)
from services.shared_search.opensearch_client import OpenSearchUnavailable
from services.shared_search.opensearch_mapping import (
    INDEX_BODY,
    candidate_index_name,
    mapping_sha256,
)


# --------------------------------------------------------------------------
# Fixture helpers
# --------------------------------------------------------------------------

def _doc(
    object_type="GUIDE",
    canonical_id="guid-001",
    title="Test Title",
    source_id="KOSHA",
    source_key=None,
    summary=None,
    aliases=None,
    subjects=None,
    context=None,
    publication_status="PUBLISHED",
    visibility_scopes=None,
    source_updated_at="2026-09-19T00:00:00+00:00",
    **extra,
):
    return {
        "object_type": object_type,
        "canonical_id": canonical_id,
        "title": title,
        "source_id": source_id,
        "source_key": source_key,
        "summary": summary,
        "aliases": aliases or [],
        "keywords": [],
        "subjects": subjects or [],
        "context": context or [],
        "public_url": f"/{object_type.lower()}/001",
        "saas_url": None,
        "publication_status": publication_status,
        "visibility_scopes": visibility_scopes or ["PUBLIC"],
        "source_updated_at": source_updated_at,
        "content_hash": "abc",
        **extra,
    }


def _pub_doc(**kwargs):
    return _doc(publication_status="PUBLISHED", visibility_scopes=["PUBLIC"], **kwargs)


def _reader(*docs):
    return MemorySearchReader(list(docs))


def _engine(*docs):
    return SharedRetrievalEngine(_reader(*docs))


# --------------------------------------------------------------------------
# §1 — Query building
# --------------------------------------------------------------------------

class TestQueryBuilding(unittest.TestCase):
    """KEEP + REWRITE: query plan, tier vocabulary (§21), identifier gate."""

    def test_blank_query_raises(self):
        with self.assertRaises(ValueError):
            build_query_plan("")

    def test_blank_query_whitespace_raises(self):
        with self.assertRaises(ValueError):
            build_query_plan("   ")

    def test_normal_query_builds_plan(self):
        plan = build_query_plan("지게차")
        self.assertEqual(plan.raw_query, "지게차")
        self.assertEqual(plan.normalized_query, "지게차")

    def test_identifier_candidate_for_no_space_query(self):
        plan = build_query_plan("지게차")
        self.assertIn("지게차", plan.identifier_candidates)

    def test_identifier_candidate_absent_for_multi_word(self):
        plan = build_query_plan("밀폐 공간 작업")
        self.assertEqual(plan.identifier_candidates, [])

    def test_all_tiers_present_by_default(self):
        plan = build_query_plan("추락", visibility_scopes=["PUBLIC"])
        # DICTIONARY_EXACT / EXPANSION may be removed if dictionary unavailable;
        # all other tiers must be in TIER_PRECEDENCE.
        non_dict = [
            t for t in TIER_PRECEDENCE
            if t not in (TIER_DICTIONARY_EXACT, TIER_DICTIONARY_EXPANSION)
        ]
        for t in non_dict:
            self.assertIn(t, plan.active_tiers)

    def test_tier_vocabulary_has_no_fts_or_trigram(self):
        """§21: FTS / TRIGRAM must not appear in tier vocabulary."""
        for t in TIER_PRECEDENCE:
            self.assertNotIn("FTS", t, f"Deprecated tier {t} found")
            self.assertNotIn("TRIGRAM", t, f"Deprecated tier {t} found")
        plan = build_query_plan("추락")
        for t in plan.active_tiers:
            self.assertNotIn("FTS", t)
            self.assertNotIn("TRIGRAM", t)

    def test_page_pagesize_passed_through(self):
        plan = build_query_plan("추락", page=3, page_size=25)
        self.assertEqual(plan.page, 3)
        self.assertEqual(plan.page_size, 25)

    def test_visibility_defaults_to_public(self):
        plan = build_query_plan("추락")
        self.assertEqual(plan.visibility_scopes, ["PUBLIC"])

    def test_no_kiwi_import(self):
        """§17 invariant: no Kiwi in shared_search package."""
        import ast, pathlib
        pkg = pathlib.Path(__file__).parent.parent / "services" / "shared_search"
        for py_file in pkg.rglob("*.py"):
            src = py_file.read_text(encoding="utf-8")
            # Allow comment mentions, flag actual imports/calls
            tree = ast.parse(src, filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = (
                        [a.name for a in node.names]
                        if isinstance(node, ast.Import)
                        else ([node.module] if node.module else [])
                    )
                    for name in names:
                        self.assertNotIn(
                            "kiwi", (name or "").lower(),
                            f"Kiwi import found in {py_file}: {ast.dump(node)}"
                        )


# --------------------------------------------------------------------------
# §2 — Result contract
# --------------------------------------------------------------------------

class TestResultContract(unittest.TestCase):
    """KEEP + REWRITE: no FTS/TRIGRAM in result vocabulary (§31)."""

    def test_to_dict_no_raw_score(self):
        r = SearchResult(
            object_type="GUIDE", canonical_id="g1", title="T",
            source_id="KOSHA", source_key=None, source_updated_at=None,
            match_type=TIER_BM25_NORI, opensearch_score=0.87,
        )
        d = r.to_dict()
        self.assertNotIn("opensearch_score", d)
        self.assertEqual(d["match_type"], TIER_BM25_NORI)

    def test_result_vocabulary_no_fts_trigram(self):
        for tier in [TIER_SOURCE_KEY_EXACT, TIER_CANONICAL_ID_EXACT,
                     TIER_DICTIONARY_EXACT, TIER_DICTIONARY_EXPANSION,
                     TIER_TITLE_EXACT, TIER_ALIAS_EXACT, TIER_SUBJECT_EXACT,
                     TIER_CONTEXT_EXACT, TIER_BM25_NORI, TIER_FUZZY_FALLBACK]:
            self.assertNotIn("FTS", tier)
            self.assertNotIn("TRIGRAM", tier)

    def test_search_response_to_dict(self):
        r = SearchResult(
            object_type="GUIDE", canonical_id="g1", title="T",
            source_id="S", source_key=None, source_updated_at=None,
        )
        resp = SearchResponse(query="추락", page=1, page_size=10,
                              total=1, items=[r], status="ok")
        d = resp.to_dict()
        self.assertEqual(d["total"], 1)
        self.assertEqual(len(d["items"]), 1)
        self.assertNotIn("opensearch_score", d["items"][0])


# --------------------------------------------------------------------------
# §3 — Tier precedence (MemorySearchReader)
# --------------------------------------------------------------------------

class TestTierPrecedence(unittest.TestCase):
    """KEEP: tier ranking correctness, adapted tier names (§21)."""

    def _make_engine_with_two_docs(self):
        docs = [
            _pub_doc(object_type="CSI_ACCIDENT", canonical_id="csi-1",
                     title="지게차", source_key="CSI:001",
                     subjects=[{"subject_type": "HAZARD", "subject_key": "지게차"}]),
            _pub_doc(object_type="GUIDE", canonical_id="g-1",
                     title="지게차 안전 가이드",
                     search_text="지게차 안전 가이드"),
        ]
        return SharedRetrievalEngine(MemorySearchReader(docs))

    def test_source_key_exact_beats_bm25(self):
        engine = self._make_engine_with_two_docs()
        resp = engine.search("CSI:001", visibility_scopes=["PUBLIC"])
        self.assertGreater(resp.total, 0)
        self.assertEqual(resp.items[0].match_type, TIER_SOURCE_KEY_EXACT)

    def test_title_exact_beats_bm25(self):
        docs = [
            _pub_doc(canonical_id="exact-1", title="지게차",
                     search_text="지게차 충돌"),
            _pub_doc(canonical_id="bm25-1", title="지게차 충돌 사고",
                     search_text="지게차 충돌 사고"),
        ]
        engine = SharedRetrievalEngine(MemorySearchReader(docs))
        resp = engine.search("지게차", visibility_scopes=["PUBLIC"])
        top = resp.items[0]
        self.assertEqual(top.match_type, TIER_TITLE_EXACT)
        self.assertEqual(top.canonical_id, "exact-1")

    def test_alias_exact_beats_bm25(self):
        docs = [
            _pub_doc(canonical_id="alias-1", title="MSDS 취급 교육",
                     aliases=["MSDS"],
                     search_text="MSDS 취급 교육"),
            _pub_doc(canonical_id="bm25-1", title="화학물질 MSDS 정보",
                     search_text="화학물질 MSDS 정보"),
        ]
        engine = SharedRetrievalEngine(MemorySearchReader(docs))
        resp = engine.search("MSDS", visibility_scopes=["PUBLIC"])
        top = resp.items[0]
        self.assertEqual(top.match_type, TIER_ALIAS_EXACT)
        self.assertEqual(top.canonical_id, "alias-1")

    def test_bm25_beats_fuzzy_fallback(self):
        """BM25_NORI (T8) outranks FUZZY_FALLBACK (T9)."""
        bm25_tier_idx  = TIER_PRECEDENCE.index(TIER_BM25_NORI)
        fuzzy_tier_idx = TIER_PRECEDENCE.index(TIER_FUZZY_FALLBACK)
        self.assertLess(bm25_tier_idx, fuzzy_tier_idx)


# --------------------------------------------------------------------------
# §4 — Visibility / scope filter
# --------------------------------------------------------------------------

class TestVisibilityFilter(unittest.TestCase):
    """KEEP: PUBLIC/SAAS/PAID scope enforcement."""

    def test_hold_doc_excluded(self):
        engine = _engine(
            _doc(publication_status="HOLD", visibility_scopes=["PUBLIC"],
                 title="추락 사고", search_text="추락 사고"),
        )
        resp = engine.search("추락", visibility_scopes=["PUBLIC"])
        self.assertEqual(resp.total, 0)

    def test_saas_only_excluded_from_public(self):
        # visibility_scopes=["SAAS"] only — PUBLIC search must not return it
        engine = _engine(
            _doc(publication_status="PUBLISHED", visibility_scopes=["SAAS"],
                 title="추락", search_text="추락"),
        )
        resp = engine.search("추락", visibility_scopes=["PUBLIC"])
        self.assertEqual(resp.total, 0)

    def test_saas_visible_in_saas_scope(self):
        engine = _engine(
            _doc(publication_status="PUBLISHED", visibility_scopes=["PUBLIC", "SAAS"],
                 title="추락", search_text="추락"),
        )
        resp = engine.search("추락", visibility_scopes=["SAAS"])
        self.assertEqual(resp.total, 1)

    def test_public_doc_visible_in_public(self):
        engine = _engine(
            _pub_doc(title="추락", search_text="추락"),
        )
        resp = engine.search("추락", visibility_scopes=["PUBLIC"])
        self.assertEqual(resp.total, 1)


# --------------------------------------------------------------------------
# §5 — Deduplication
# --------------------------------------------------------------------------

class TestDeduplication(unittest.TestCase):
    """KEEP: dedup by (object_type, canonical_id), highest tier wins."""

    def test_multi_tier_hit_deduped_to_one(self):
        doc = _pub_doc(
            canonical_id="dup-1", title="지게차",
            source_key="지게차",
            aliases=["지게차"],
            search_text="지게차",
        )
        engine = _engine(doc)
        resp = engine.search("지게차", visibility_scopes=["PUBLIC"])
        self.assertEqual(resp.total, 1)

    def test_top_tier_wins_on_dedup(self):
        doc = _pub_doc(
            canonical_id="dup-1", title="지게차",
            source_key="지게차",
            aliases=["지게차"],
        )
        engine = _engine(doc)
        resp = engine.search("지게차", visibility_scopes=["PUBLIC"])
        self.assertEqual(resp.total, 1)
        top = resp.items[0]
        # SOURCE_KEY_EXACT < TITLE_EXACT (lower tier_idx = higher precedence)
        self.assertIn(top.match_type, [TIER_SOURCE_KEY_EXACT, TIER_TITLE_EXACT])
        src_idx   = TIER_PRECEDENCE.index(TIER_SOURCE_KEY_EXACT)
        title_idx = TIER_PRECEDENCE.index(TIER_TITLE_EXACT)
        result_idx = TIER_PRECEDENCE.index(top.match_type)
        self.assertLessEqual(result_idx, title_idx)


# --------------------------------------------------------------------------
# §6 — Fuzzy fallback
# --------------------------------------------------------------------------

class TestFuzzyFallback(unittest.TestCase):
    """ADD: FUZZY_FALLBACK tier fires only when upper tiers empty."""

    def test_fuzzy_fires_when_upper_tiers_miss(self):
        # MemorySearchReader fuzzy = substring. "지게" matches "지게차" title.
        doc = _pub_doc(canonical_id="f-1", title="지게차 충돌")
        reader = MemorySearchReader([doc])
        plan = build_query_plan("지게", visibility_scopes=["PUBLIC"])
        # No upper tier will match (title exact / source_key exact all miss)
        resp = retrieve(plan, reader, fuzzy_trigger_threshold=0)
        # FUZZY fires because total after upper tiers == 0 <= 0
        self.assertEqual(resp.total, 1)
        self.assertEqual(resp.items[0].match_type, TIER_FUZZY_FALLBACK)

    def test_fuzzy_not_fired_when_upper_tiers_have_results(self):
        doc = _pub_doc(canonical_id="f-1", title="지게차",
                       search_text="지게차 충돌")
        plan = build_query_plan("지게차", visibility_scopes=["PUBLIC"])
        reader = MemorySearchReader([doc])
        # fuzzy_trigger_threshold=0 means "fire fuzzy only if 0 results from upper"
        resp = retrieve(plan, reader, fuzzy_trigger_threshold=0)
        # title exact already matches — fuzzy NOT fired
        self.assertNotIn(TIER_FUZZY_FALLBACK, resp.active_tiers)


# --------------------------------------------------------------------------
# §7 — OpenSearch mapping
# --------------------------------------------------------------------------

class TestOpenSearchMapping(unittest.TestCase):
    """ADD: mapping authority, Nori config, alias naming, sha256."""

    def test_mapping_has_nori_analyzer(self):
        settings = INDEX_BODY["settings"]
        analysis = settings["analysis"]
        self.assertIn("tai_nori_index", analysis["analyzer"])
        self.assertIn("tai_nori_search", analysis["analyzer"])

    def test_nori_tokenizer_defined(self):
        tokenizers = INDEX_BODY["settings"]["analysis"]["tokenizer"]
        self.assertIn("tai_nori_tokenizer", tokenizers)
        tt = tokenizers["tai_nori_tokenizer"]
        self.assertEqual(tt["type"], "nori_tokenizer")

    def test_keyword_fields_not_analyzed(self):
        props = INDEX_BODY["mappings"]["properties"]
        for field in ["source_key", "canonical_id", "object_type",
                      "publication_status"]:
            self.assertEqual(props[field]["type"], "keyword",
                             f"{field} should be keyword")

    def test_text_fields_use_nori(self):
        props = INDEX_BODY["mappings"]["properties"]
        for field in ["title", "summary", "search_text"]:
            f = props[field]
            self.assertEqual(f.get("analyzer"), "tai_nori_index", field)
            self.assertEqual(f.get("search_analyzer"), "tai_nori_search", field)

    def test_title_raw_subfield_exists(self):
        props = INDEX_BODY["mappings"]["properties"]
        self.assertIn("raw", props["title"]["fields"])

    def test_aliases_raw_subfield_exists(self):
        props = INDEX_BODY["mappings"]["properties"]
        self.assertIn("raw", props["aliases"]["fields"])

    def test_subjects_nested(self):
        props = INDEX_BODY["mappings"]["properties"]
        self.assertEqual(props["subjects"]["type"], "nested")

    def test_context_nested(self):
        props = INDEX_BODY["mappings"]["properties"]
        self.assertEqual(props["context"]["type"], "nested")

    def test_candidate_index_name_format(self):
        name = candidate_index_name("test-run-id-12345678-abcd")
        self.assertTrue(name.startswith("tai-shared-search-v1-"))
        self.assertLessEqual(len(name), len("tai-shared-search-v1-") + 16)

    def test_mapping_sha256_is_stable(self):
        sha1 = mapping_sha256()
        sha2 = mapping_sha256()
        self.assertEqual(sha1, sha2)
        self.assertEqual(len(sha1), 64)  # sha256 hex


# --------------------------------------------------------------------------
# §8 — OpenSearch Store (unit — mocked client)
# --------------------------------------------------------------------------

class TestOpenSearchStore(unittest.TestCase):
    """ADD: bulk staging, alias promotion, rollback via mocked client."""

    def _make_store(self):
        from services.shared_search.opensearch_store import OpenSearchSearchStore
        mock_client = MagicMock()
        mock_client.indices.exists.return_value = False
        mock_client.indices.exists_alias.return_value = False
        mock_client.indices.get_alias.return_value = {}
        mock_client.indices.create.return_value = {"acknowledged": True}
        mock_client.index.return_value = {}
        mock_client.count.return_value = {"count": 100}
        mock_client.indices.refresh.return_value = {}
        mock_client.update.return_value = {}
        mock_client.get.return_value = {
            "_source": {
                "indexed_count": 0, "failed_bulk_items": 0,
                "previous_index": None,
            }
        }
        return OpenSearchSearchStore(mock_client), mock_client

    def test_create_candidate_index_calls_create(self):
        store, client = self._make_store()
        idx = store.create_candidate_index("run-abc-123")
        self.assertTrue(idx.startswith("tai-shared-search-v1-"))
        client.indices.create.assert_called_once()

    def test_candidate_index_naming(self):
        store, _ = self._make_store()
        idx = store.create_candidate_index("aaaa-bbbb-cccc")
        self.assertIn("tai-shared-search-v1-", idx)

    def test_document_id_deterministic(self):
        from services.shared_search.opensearch_store import document_id
        d1 = document_id("GUIDE", "g-001")
        d2 = document_id("GUIDE", "g-001")
        self.assertEqual(d1, d2)
        self.assertIn("GUIDE", d1)
        self.assertIn("g-001", d1)

    def test_document_id_different_per_type(self):
        from services.shared_search.opensearch_store import document_id
        d1 = document_id("GUIDE", "g-001")
        d2 = document_id("CSI_ACCIDENT", "g-001")
        self.assertNotEqual(d1, d2)

    def test_alias_switch_action_structure(self):
        from services.shared_search.opensearch_mapping import build_alias_action
        action = build_alias_action("new-idx", "old-idx")
        actions = action["actions"]
        removes = [a for a in actions if "remove" in a]
        adds    = [a for a in actions if "add" in a]
        self.assertEqual(len(removes), 1)
        self.assertEqual(len(adds), 1)

    def test_alias_switch_without_old(self):
        from services.shared_search.opensearch_mapping import build_alias_action
        action = build_alias_action("new-idx")
        actions = action["actions"]
        removes = [a for a in actions if "remove" in a]
        self.assertEqual(len(removes), 0)


# --------------------------------------------------------------------------
# §9 — OpenSearch client + 503 handling
# --------------------------------------------------------------------------

class TestOpenSearchClient(unittest.TestCase):
    """ADD: OpenSearchUnavailable, 503 config missing."""

    def test_get_client_raises_when_url_missing(self):
        from services.shared_search.opensearch_client import (
            OpenSearchUnavailable, reset_client, get_client
        )
        reset_client()
        original = os.environ.pop("TAI_OPENSEARCH_URL", None)
        try:
            with self.assertRaises(OpenSearchUnavailable):
                get_client()
        finally:
            if original is not None:
                os.environ["TAI_OPENSEARCH_URL"] = original
            reset_client()

    def test_opensearch_unavailable_is_exception(self):
        self.assertTrue(issubclass(OpenSearchUnavailable, Exception))


# --------------------------------------------------------------------------
# §10 — Public API: visibility / 503
# --------------------------------------------------------------------------

class TestPublicAPILayer(unittest.TestCase):
    """ADD: 503 when OpenSearch config missing, type filtering."""

    def test_503_when_opensearch_not_configured(self):
        """API must raise 503 (not silently return empty) when OS missing."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from services.shared_search.opensearch_client import reset_client
        import routers.public_safety_search as pss_router

        reset_client()
        original = os.environ.pop("TAI_OPENSEARCH_URL", None)
        try:
            app = FastAPI()
            app.include_router(pss_router.router)
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/public/safety-search?q=지게차")
            self.assertEqual(resp.status_code, 503)
            body = resp.json()
            self.assertIn("SHARED_SEARCH_UNAVAILABLE", str(body))
        finally:
            if original is not None:
                os.environ["TAI_OPENSEARCH_URL"] = original
            reset_client()

    def test_kosha_endpoint_not_changed(self):
        """§42: /public/safety-search/kosha endpoint must exist."""
        import inspect
        import routers.public_safety_search as pss_router
        routes = [r.path for r in pss_router.router.routes]
        # endpoint exists
        self.assertTrue(any("kosha" in r for r in routes),
                        f"kosha endpoint missing; routes={routes}")


# --------------------------------------------------------------------------
# §11 — CSI completeness (KEEP)
# --------------------------------------------------------------------------

class TestCSICompleteness(unittest.TestCase):
    """KEEP: CSI title fallback + census audit (§51)."""

    def test_csi_title_fallback_to_summary(self):
        from services.shared_search.adapters.csi_accident import CsiAccidentAdapter
        from unittest.mock import patch as _patch

        row = {"id": 1, "title": None, "summary": "요약 내용", "content": None}
        adapter = CsiAccidentAdapter.__new__(CsiAccidentAdapter)
        result = adapter._extract_title(row)
        self.assertEqual(result, "요약 내용")

    def test_csi_title_used_when_available(self):
        from services.shared_search.adapters.csi_accident import CsiAccidentAdapter
        row = {"id": 1, "title": "원래 제목", "summary": "요약 내용", "content": None}
        adapter = CsiAccidentAdapter.__new__(CsiAccidentAdapter)
        result = adapter._extract_title(row)
        self.assertEqual(result, "원래 제목")

    def test_csi_census_source_yield_audit_pass(self):
        from services.shared_search.census import source_yield_audit
        stats = source_yield_audit(
            eligible_source_count=10,
            yielded_count=10,
            explained_exclusions=[],
        )
        self.assertEqual(stats["unexplained_drop"], 0)

    def test_csi_census_audit_explains_drops(self):
        from services.shared_search.census import source_yield_audit
        stats = source_yield_audit(
            eligible_source_count=10,
            yielded_count=9,
            explained_exclusions=[{"reason": "no_title_no_summary", "count": 1}],
        )
        self.assertEqual(stats["unexplained_drop"], 0)
        self.assertEqual(stats["explained_exclusion_count"], 1)

    def test_csi_census_unexplained_drop_flagged(self):
        from services.shared_search.census import source_yield_audit
        stats = source_yield_audit(
            eligible_source_count=10,
            yielded_count=8,
            explained_exclusions=[{"reason": "no_title_no_summary", "count": 1}],
        )
        self.assertEqual(stats["unexplained_drop"], 1)


# --------------------------------------------------------------------------
# §12 — CHEM completeness (KEEP)
# --------------------------------------------------------------------------

class TestCHEMCompleteness(unittest.TestCase):
    """KEEP: CHEM title logic + section_fields."""

    def test_chem_ko_name_used_when_available(self):
        from services.shared_search.adapters.chem import ChemAdapter
        row = {"id": 1, "chemical_name_ko": "아세톤", "section1_payload": None}
        adapter = ChemAdapter.__new__(ChemAdapter)
        result = adapter._extract_title(row)
        self.assertEqual(result, "아세톤")

    def test_chem_falls_back_to_product_name(self):
        from services.shared_search.adapters.chem import ChemAdapter
        from services.kosha_msds.section_fields import PRODUCT_NAME_ITEM_CODE
        payload = [{"msdsItemCode": PRODUCT_NAME_ITEM_CODE, "itemDetail": "안전제품A"}]
        import json
        row = {"id": 1, "chemical_name_ko": None, "section1_payload": json.dumps(payload)}
        adapter = ChemAdapter.__new__(ChemAdapter)
        result = adapter._extract_title(row)
        self.assertEqual(result, "안전제품A")

    def test_chem_drops_when_both_null(self):
        from services.shared_search.adapters.chem import ChemAdapter
        row = {"id": 1, "chemical_name_ko": None, "section1_payload": None}
        adapter = ChemAdapter.__new__(ChemAdapter)
        result = adapter._extract_title(row)
        self.assertIsNone(result)

    def test_chem_section_fields_extract_product_name(self):
        from services.kosha_msds.section_fields import (
            extract_product_name,
            PRODUCT_NAME_ITEM_CODE,
        )
        payload = [{"msdsItemCode": PRODUCT_NAME_ITEM_CODE, "itemDetail": "TestProd"}]
        result = extract_product_name(payload)
        self.assertEqual(result, "TestProd")

    def test_chem_section_fields_returns_none_when_missing(self):
        from services.kosha_msds.section_fields import extract_product_name
        result = extract_product_name([])
        self.assertIsNone(result)


# --------------------------------------------------------------------------
# §13 — F1/F2/F3 import smoke tests (KEEP)
# --------------------------------------------------------------------------

class TestImportRegressions(unittest.TestCase):
    """KEEP: smoke-test all major import chains."""

    def test_f1_foundation_imports(self):
        from services.shared_search import (
            SearchDocument, SearchStore, normalize_document, content_hash,
        )

    def test_f2_adapter_imports(self):
        from services.shared_search import (
            GuideAdapter, SafetyMaterialAdapter, CsiAccidentAdapter,
            ChemAdapter, LegalAdapter, PrecedentAdapter, KnowledgeAdapter,
        )

    def test_f2_indexer_imports(self):
        from services.shared_search import Indexer, RebuildResult, DryRunCensus

    def test_f2_census_imports(self):
        from services.shared_search import (
            DomainCensus, run_census, CountingFetcher, source_yield_audit,
        )

    def test_f3_retrieval_imports(self):
        from services.shared_search import (
            SharedRetrievalEngine, MemorySearchReader, retrieve,
            build_query_plan, SearchQueryPlan, SearchResult, SearchResponse,
        )
        # SupabaseSearchReader must NOT be exported
        import services.shared_search as ss
        self.assertFalse(
            hasattr(ss, "SupabaseSearchReader"),
            "SupabaseSearchReader must not be exported from shared_search (§4)"
        )

    def test_f3_opensearch_imports(self):
        from services.shared_search import (
            OpenSearchSearchStore, OpenSearchSearchReader,
            get_opensearch_client, OpenSearchUnavailable,
        )

    def test_production_bindings_import(self):
        from services.shared_search import build_production_adapters

    def test_section_fields_import(self):
        from services.kosha_msds.section_fields import extract_product_name

    def test_no_postgres_fts_in_f3_code(self):
        """§44: to_tsvector / plainto_tsquery / pg_trgm must not appear in
        actual code (non-comment lines) in F3 shared_search paths."""
        import ast, pathlib
        banned = ["to_tsvector", "plainto_tsquery", "pg_trgm", "search_by_trigram"]
        pkg = pathlib.Path(__file__).parent.parent / "services" / "shared_search"
        for py_file in pkg.rglob("*.py"):
            src = py_file.read_text(encoding="utf-8")
            # Strip comment lines for the check (comments are explanatory docs)
            code_lines = [
                line for line in src.splitlines()
                if not line.lstrip().startswith("#")
                and not line.lstrip().startswith('"""')
                and not line.lstrip().startswith("'''")
            ]
            code_only = "\n".join(code_lines)
            # Also strip from string literals in docstrings via ast parsing
            try:
                tree = ast.parse(src, filename=str(py_file))
                # Check only non-docstring string values in call/assign nodes
                # — if any node's s value contains the banned term that's actual code
            except SyntaxError:
                pass
            for token in banned:
                self.assertNotIn(
                    token, code_only,
                    f"Banned PostgreSQL token {token!r} found in code of {py_file}"
                )

    def test_supabase_retrieval_migration_deleted(self):
        """§44: The FTS migration file must be deleted from the branch."""
        import pathlib
        migration = (pathlib.Path(__file__).parent.parent
                     / "supabase" / "migrations"
                     / "20260919_shared_search_retrieval.sql")
        self.assertFalse(
            migration.exists(),
            "supabase/migrations/20260919_shared_search_retrieval.sql "
            "must be deleted (§44)"
        )


# --------------------------------------------------------------------------
# §14 — Pagination (KEEP)
# --------------------------------------------------------------------------

class TestPagination(unittest.TestCase):
    """KEEP: pagination contract."""

    def _make_docs(self, n: int):
        return [
            _pub_doc(canonical_id=f"doc-{i}", title="추락",
                     search_text="추락 사고")
            for i in range(n)
        ]

    def test_page1_vs_page2_different(self):
        engine = SharedRetrievalEngine(MemorySearchReader(self._make_docs(5)))
        r1 = engine.search("추락", visibility_scopes=["PUBLIC"], page=1, page_size=3)
        r2 = engine.search("추락", visibility_scopes=["PUBLIC"], page=2, page_size=3)
        ids1 = {item.canonical_id for item in r1.items}
        ids2 = {item.canonical_id for item in r2.items}
        self.assertFalse(ids1 & ids2, "Page 1 and page 2 must not overlap")

    def test_total_consistent_across_pages(self):
        engine = SharedRetrievalEngine(MemorySearchReader(self._make_docs(5)))
        r1 = engine.search("추락", visibility_scopes=["PUBLIC"], page=1, page_size=3)
        r2 = engine.search("추락", visibility_scopes=["PUBLIC"], page=2, page_size=3)
        self.assertEqual(r1.total, r2.total)

    def test_page_size_capped_at_50(self):
        engine = SharedRetrievalEngine(MemorySearchReader(self._make_docs(100)))
        resp = engine.search("추락", visibility_scopes=["PUBLIC"],
                              page=1, page_size=100)
        self.assertLessEqual(len(resp.items), 50)

    def test_engine_raises_on_empty(self):
        engine = SharedRetrievalEngine(MemorySearchReader([]))
        with self.assertRaises(ValueError):
            engine.search("")

    def test_engine_raises_on_whitespace(self):
        engine = SharedRetrievalEngine(MemorySearchReader([]))
        with self.assertRaises(ValueError):
            engine.search("   ")


# --------------------------------------------------------------------------
# §15 — Deterministic dictionary API (ADD)
# --------------------------------------------------------------------------

class TestDeterministicDictionary(unittest.TestCase):
    """ADD: lookup_deterministic does not include Kiwi TOKEN/TRIGRAM."""

    def test_lookup_deterministic_returns_dict(self):
        from services.search_query_svc import lookup_deterministic, SearchDictError
        try:
            result = lookup_deterministic("지게차", limit=5)
        except SearchDictError:
            self.skipTest("Search dictionary projection not available in CI")
        self.assertIsInstance(result, dict)
        self.assertIn("items", result)

    def test_lookup_deterministic_active_tiers_no_kiwi(self):
        from services.search_query_svc import lookup_deterministic, SearchDictError
        try:
            result = lookup_deterministic("추락", limit=5)
        except SearchDictError:
            self.skipTest("Search dictionary projection not available in CI")
        tiers = result.get("active_tiers") or []
        for t in tiers:
            self.assertNotIn("TOKEN", t.upper(),
                             f"Kiwi TOKEN tier {t!r} found in active_tiers")
            self.assertNotIn("TRIGRAM", t.upper())

    def test_lookup_deterministic_blank_raises(self):
        from services.search_query_svc import lookup_deterministic, SearchDictError
        with self.assertRaises(SearchDictError):
            lookup_deterministic("")

    def test_legacy_lookup_still_exists(self):
        """§16: existing lookup() must not be removed."""
        from services.search_query_svc import lookup, SearchDictError
        try:
            result = lookup("지게차", limit=5)
        except SearchDictError:
            self.skipTest("Search dictionary projection not available in CI")
        self.assertIn("items", result)


# --------------------------------------------------------------------------
# §16 — Parity fixture (KEEP adapted)
# --------------------------------------------------------------------------

class TestParityFixtures(unittest.TestCase):
    """KEEP: basic parity that CSI and GUIDE docs appear in search."""

    def test_csi_via_subject(self):
        docs = [
            _pub_doc(
                object_type="CSI_ACCIDENT", canonical_id="csi-1",
                title="지게차 충돌",
                search_text="지게차 충돌",
                subjects=[{"subject_type": "HAZARD", "subject_key": "지게차"}],
            )
        ]
        engine = SharedRetrievalEngine(MemorySearchReader(docs))
        plan = build_query_plan("지게차", visibility_scopes=["PUBLIC"])
        plan.subject_candidates = [
            SubjectCandidate("HAZARD", "지게차", "지게차", "EXACT", 100.0)
        ]
        from services.shared_search.retrieval import retrieve
        resp = retrieve(plan, MemorySearchReader(docs))
        self.assertEqual(resp.total, 1)
        self.assertEqual(resp.items[0].object_type, "CSI_ACCIDENT")

    def test_guide_via_bm25(self):
        docs = [
            _pub_doc(
                object_type="GUIDE", canonical_id="g-1",
                title="밀폐공간 작업 안전",
                search_text="밀폐공간 작업 안전 가이드 산소결핍",
            )
        ]
        engine = SharedRetrievalEngine(MemorySearchReader(docs))
        resp = engine.search("밀폐공간", visibility_scopes=["PUBLIC"])
        self.assertGreater(resp.total, 0)
        self.assertEqual(resp.items[0].object_type, "GUIDE")


# --------------------------------------------------------------------------
# §17 — F3-G1 Rebuild safety scoped unit tests (§2-§15, §22-§23)
# --------------------------------------------------------------------------

def _make_sample_payload(**overrides) -> dict:
    """Minimal valid payload for prepare_search_document()."""
    p = {
        "object_type": "GUIDE", "canonical_id": "g-test-001", "title": "Test Doc",
        "source_id": "KOSHA", "source_key": "g-001",
        "publication_status": "PUBLISHED", "visibility_scopes": ["PUBLIC"],
        "source_updated_at": "2026-09-19T00:00:00+00:00",
        "search_text": "Test document for negative integration tests",
    }
    p.update(overrides)
    return p


class TestPrepareSDocumentHelper(unittest.TestCase):
    """§5 — prepare_search_document() is the single canonical prepare authority."""

    def test_prepare_returns_doc_and_wire(self):
        from services.shared_search.writer import prepare_search_document
        doc, wire = prepare_search_document(_make_sample_payload())
        self.assertEqual(doc.object_type, "GUIDE")
        self.assertIn("content_hash", wire)
        self.assertIn("canonical_id", wire)

    def test_prepare_sets_content_hash(self):
        from services.shared_search.writer import prepare_search_document
        doc, wire = prepare_search_document(_make_sample_payload())
        self.assertIsNotNone(doc.content_hash)
        self.assertTrue(len(doc.content_hash) >= 32)

    def test_prepare_parity_with_writer_prepare(self):
        """Writer._prepare() must delegate to prepare_search_document()."""
        from services.shared_search.writer import prepare_search_document, Writer, MemoryStore
        payload = _make_sample_payload()
        doc_h, wire_h = prepare_search_document(payload)
        writer = Writer(MemoryStore())
        doc_w, wire_w = writer._prepare(payload)
        self.assertEqual(doc_h.content_hash, doc_w.content_hash)
        self.assertEqual(wire_h["canonical_id"], wire_w["canonical_id"])

    def test_prepare_rejects_missing_required_field(self):
        from services.shared_search.writer import prepare_search_document
        from services.shared_search.contract import SearchContractError
        bad = {k: v for k, v in _make_sample_payload().items() if k != "search_text"}
        with self.assertRaises(SearchContractError):
            prepare_search_document(bad)

    def test_prepare_exported_from_package(self):
        from services.shared_search import prepare_search_document
        self.assertTrue(callable(prepare_search_document))


class TestOpenSearchStoreSafetyGuards(unittest.TestCase):
    """§8-§13 F3-G1 — Negative safety contracts via mocked client.

    These tests are the authoritative fast unit tests. Full live tests
    are done via the integration script (tests are mocked here).
    """

    def _make_store_and_client(self, run_source=None):
        from services.shared_search.opensearch_store import OpenSearchSearchStore, RUN_STATUS_RUNNING
        mc = MagicMock()
        mc.indices.exists.return_value = False
        mc.indices.create.return_value = {"acknowledged": True}
        mc.index.return_value = {}
        mc.count.return_value = {"count": 1}
        mc.indices.refresh.return_value = {}
        mc.indices.update_aliases.return_value = {}
        mc.indices.get_alias.return_value = {"tai-shared-search-v1-oldddddddddddddd": {}}
        _default_source = {
            "status": RUN_STATUS_RUNNING, "failed_bulk_items": 0,
            "expected_count": 0, "indexed_count": 0,
            "previous_index": None, "manifest": {}, "duplicate_count": 0,
        }
        if run_source:
            _default_source.update(run_source)
        mc.get.return_value = {"_source": _default_source}
        mc.update.return_value = {}
        mc.search.return_value = {"aggregations": {"unique_ids": {"value": 1}}}
        return OpenSearchSearchStore(mc), mc

    def test_validate_run_fails_on_bulk_failures(self):
        from services.shared_search.opensearch_store import RebuildRejected, RUN_STATUS_RUNNING
        store, mc = self._make_store_and_client(
            {"status": RUN_STATUS_RUNNING, "failed_bulk_items": 2})
        with self.assertRaises(RebuildRejected) as ctx:
            store.validate_run("run-x", expected_count=10)
        self.assertIn("bulk", str(ctx.exception).lower())

    def test_validate_run_fails_on_zero_expected(self):
        from services.shared_search.opensearch_store import RebuildRejected, RUN_STATUS_RUNNING
        store, mc = self._make_store_and_client(
            {"status": RUN_STATUS_RUNNING, "failed_bulk_items": 0})
        with self.assertRaises(RebuildRejected) as ctx:
            store.validate_run("run-x", expected_count=0)
        self.assertIn("expected_count == 0", str(ctx.exception))

    def test_validate_run_fails_on_count_mismatch(self):
        from services.shared_search.opensearch_store import RebuildRejected, RUN_STATUS_RUNNING
        store, mc = self._make_store_and_client(
            {"status": RUN_STATUS_RUNNING, "failed_bulk_items": 0})
        # count() returns 1 but we expect 4
        mc.count.return_value = {"count": 1}
        with self.assertRaises(RebuildRejected) as ctx:
            store.validate_run("run-x", expected_count=4)
        self.assertIn("actual", str(ctx.exception).lower())

    def test_validate_run_fails_on_per_domain_mismatch(self):
        from services.shared_search.opensearch_store import RebuildRejected, RUN_STATUS_RUNNING
        mc_source = {
            "status": RUN_STATUS_RUNNING, "failed_bulk_items": 0,
            "manifest": {"GUIDE": {"expected": 1, "indexed": 1}, "CSI": {"expected": 0, "indexed": 0}},
        }
        store, mc = self._make_store_and_client(mc_source)
        mc.count.return_value = {"count": 1}
        with self.assertRaises(RebuildRejected) as ctx:
            store.validate_run("run-x", expected_count=1,
                               per_domain_expected={"GUIDE": 1, "CSI": 5})
        self.assertIn("domain", str(ctx.exception).lower())

    def test_promote_rejects_when_not_validated(self):
        from services.shared_search.opensearch_store import RebuildRejected, RUN_STATUS_RUNNING
        store, mc = self._make_store_and_client({"status": RUN_STATUS_RUNNING})
        with self.assertRaises(RebuildRejected) as ctx:
            store.promote("run-x")
        self.assertIn("VALIDATED", str(ctx.exception))

    def test_promote_rejects_when_failed(self):
        from services.shared_search.opensearch_store import RebuildRejected, RUN_STATUS_FAILED
        store, mc = self._make_store_and_client({"status": RUN_STATUS_FAILED})
        with self.assertRaises(RebuildRejected) as ctx:
            store.promote("run-x")
        self.assertIn("VALIDATED", str(ctx.exception))

    def test_promote_rejects_when_indexed_ne_expected(self):
        from services.shared_search.opensearch_store import RebuildRejected, RUN_STATUS_VALIDATED
        store, mc = self._make_store_and_client({
            "status": RUN_STATUS_VALIDATED, "failed_bulk_items": 0,
            "expected_count": 10, "indexed_count": 9,
        })
        mc.indices.exists.return_value = True
        with self.assertRaises(RebuildRejected) as ctx:
            store.promote("run-x")
        self.assertIn("blocked", str(ctx.exception).lower())

    def test_promote_rejects_when_bulk_failures_nonzero(self):
        from services.shared_search.opensearch_store import RebuildRejected, RUN_STATUS_VALIDATED
        store, mc = self._make_store_and_client({
            "status": RUN_STATUS_VALIDATED, "failed_bulk_items": 3,
            "expected_count": 10, "indexed_count": 10,
        })
        with self.assertRaises(RebuildRejected) as ctx:
            store.promote("run-x")
        self.assertIn("blocked", str(ctx.exception).lower())

    def test_promote_succeeds_when_validated(self):
        from services.shared_search.opensearch_store import RUN_STATUS_VALIDATED
        store, mc = self._make_store_and_client({
            "status": RUN_STATUS_VALIDATED, "failed_bulk_items": 0,
            "expected_count": 1, "indexed_count": 1,
            "previous_index": "tai-shared-search-v1-oldddddddddddddd",
        })
        mc.indices.exists.return_value = True
        mc.count.return_value = {"count": 1}
        mc.indices.get_alias.return_value = {"tai-shared-search-v1-oldddddddddddddd": {}}
        result = store.promote("run-x")
        mc.indices.update_aliases.assert_called_once()
        self.assertTrue(result.startswith("tai-shared-search-v1-"))

    def test_alias_unchanged_after_validation_failure(self):
        """Alias must not be touched when validate_run fails."""
        from services.shared_search.opensearch_store import RebuildRejected, RUN_STATUS_RUNNING
        store, mc = self._make_store_and_client(
            {"status": RUN_STATUS_RUNNING, "failed_bulk_items": 1})
        try:
            store.validate_run("run-x", expected_count=10)
        except RebuildRejected:
            pass
        mc.indices.update_aliases.assert_not_called()

    def test_rebuild_tool_uses_real_adapter_api(self):
        """Smoke: opensearch_rebuild imports and references correct API symbols."""
        import ast, pathlib
        src = pathlib.Path("tools/shared_search/opensearch_rebuild.py").read_text()
        tree = ast.parse(src)
        attr_names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        # Must reference the real F2 contract symbols
        self.assertIn("build_production_adapters",
                      {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)})
        self.assertIn("prepare_search_document",
                      {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)})
        self.assertIn("domain_name", attr_names)
        self.assertIn("iter_documents", attr_names)
        # Must NOT reference banned F2 API symbols (§2 F3-G1)
        self.assertNotIn("build_domain", attr_names)     # Indexer.build_domain() = nonexistent
        self.assertNotIn("dry_run_census", attr_names)   # Indexer.dry_run_census() = nonexistent
        self.assertNotIn("Indexer(adapters=", src)       # wrong constructor pattern
        # adapter.domain (without _name) must not appear as attribute in full_rebuild
        # (dry_run uses Indexer.dry_run(adapter) which is allowed §17)
        self.assertNotIn(".build_domain(", src)
        self.assertNotIn(".dry_run_census(", src)

    def test_prepare_search_document_is_the_canonical_authority(self):
        """Only prepare_search_document (not normalize_document directly) should be in rebuild."""
        import pathlib
        rebuild_src = pathlib.Path("tools/shared_search/opensearch_rebuild.py").read_text()
        self.assertIn("prepare_search_document", rebuild_src)
        # Should NOT call normalize_document directly in rebuild
        self.assertNotIn("normalize_document(", rebuild_src)

    def test_no_id_aggregation_in_store(self):
        """_id cardinality aggregation must NOT exist in opensearch_store.py (§6 F3-G1).
        OpenSearch _id is not aggregatable."""
        import pathlib
        src = pathlib.Path("services/shared_search/opensearch_store.py").read_text()
        # Check for actual aggregation code patterns, not docstring mentions
        self.assertNotIn('cardinality(field="_id"', src)
        self.assertNotIn('"cardinality":', src)
        self.assertNotIn("precision_threshold", src)
        self.assertNotIn("check_duplicates", src)

    def test_no_id_aggregation_in_rebuild(self):
        """opensearch_rebuild.py must not reference _id aggregation (§6 F3-G1)."""
        import pathlib
        src = pathlib.Path("tools/shared_search/opensearch_rebuild.py").read_text()
        # Check for actual aggregation code patterns
        self.assertNotIn('cardinality(field="_id"', src)
        self.assertNotIn('"cardinality":', src)
        self.assertNotIn("precision_threshold", src)
        self.assertNotIn("check_duplicates", src)

    def test_global_seen_in_rebuild(self):
        """Global identity tracking (global_seen) must be present in full_rebuild (§7-§9)."""
        import pathlib
        src = pathlib.Path("tools/shared_search/opensearch_rebuild.py").read_text()
        self.assertIn("global_seen", src)

    def test_dry_run_uses_run_census(self):
        """dry_run() must use run_census() from census.py (§3 F3-G1 BLOCKER A)."""
        import pathlib
        src = pathlib.Path("tools/shared_search/opensearch_rebuild.py").read_text()
        self.assertIn("run_census", src)
        # Must NOT reference DryRunCensus field names that don't exist
        self.assertNotIn("census.published_count", src)
        self.assertNotIn("census.eligible_count", src)
        self.assertNotIn("census.hold_count", src)
        self.assertNotIn("census.duplicate_count", src)


class TestOpenSearchStoreRebuildConstants(unittest.TestCase):
    """§31 — RUN_STATUS constants are correct strings."""

    def test_run_status_values(self):
        from services.shared_search.opensearch_store import (
            RUN_STATUS_RUNNING, RUN_STATUS_VALIDATED,
            RUN_STATUS_PROMOTED, RUN_STATUS_FAILED,
        )
        self.assertEqual(RUN_STATUS_RUNNING, "RUNNING")
        self.assertEqual(RUN_STATUS_VALIDATED, "VALIDATED")
        self.assertEqual(RUN_STATUS_PROMOTED, "PROMOTED")
        self.assertEqual(RUN_STATUS_FAILED, "FAILED")

    def test_rebuild_rejected_is_exception(self):
        from services.shared_search.opensearch_store import RebuildRejected
        self.assertTrue(issubclass(RebuildRejected, Exception))

    def test_check_duplicates_removed(self):
        """check_duplicates() must NOT exist in OpenSearchSearchStore (§6 BLOCKER B).
        OpenSearch _id is not aggregatable."""
        from services.shared_search.opensearch_store import OpenSearchSearchStore
        self.assertFalse(hasattr(OpenSearchSearchStore, "check_duplicates"))


class TestGlobalDuplicateGuard(unittest.TestCase):
    """§7-§11 F3-G1 — Global identity duplicate guard in rebuild.

    Duplicate detection must happen in TAI canonical preparation (global_seen),
    NOT in OpenSearch via _id aggregation.
    """

    def _make_valid_payload(self, otype: str, cid: str, title: str = "Doc") -> dict:
        return {
            "object_type": otype, "canonical_id": cid, "title": title,
            "source_id": "KOSHA", "source_key": f"sk-{cid}",
            "publication_status": "PUBLISHED", "visibility_scopes": ["PUBLIC"],
            "source_updated_at": "2026-09-19T00:00:00+00:00",
            "search_text": f"Search text for {cid}",
        }

    def test_D1_same_domain_duplicate_detected(self):
        """D1: Same adapter yields duplicate (object_type, canonical_id) → detected."""
        from services.shared_search.writer import prepare_search_document
        from services.shared_search.contract import PUBLICATION_STATUS_PUBLISHED

        payloads = [
            self._make_valid_payload("GUIDE", "g-dup-001"),
            self._make_valid_payload("GUIDE", "g-dup-001"),  # duplicate
            self._make_valid_payload("GUIDE", "g-unique-002"),
        ]

        global_seen: set[tuple[str, str]] = set()
        duplicates_found = 0

        for payload in payloads:
            try:
                doc, wire = prepare_search_document(payload)
            except Exception:
                continue
            if doc.publication_status != PUBLICATION_STATUS_PUBLISHED:
                continue
            identity = (doc.object_type, doc.canonical_id)
            if identity in global_seen:
                duplicates_found += 1
            else:
                global_seen.add(identity)

        self.assertEqual(duplicates_found, 1, "D1: exactly 1 duplicate should be detected")

    def test_D2_cross_adapter_duplicate_detected(self):
        """D2: Two adapters emit same (object_type, canonical_id) → detected globally."""
        from services.shared_search.writer import prepare_search_document
        from services.shared_search.contract import PUBLICATION_STATUS_PUBLISHED

        adapter_a_payloads = [
            self._make_valid_payload("GUIDE", "cross-001"),
        ]
        adapter_b_payloads = [
            self._make_valid_payload("GUIDE", "cross-001"),  # same identity from different adapter
        ]

        global_seen: set[tuple[str, str]] = set()
        cross_dups = 0

        for payload in adapter_a_payloads + adapter_b_payloads:
            try:
                doc, wire = prepare_search_document(payload)
            except Exception:
                continue
            if doc.publication_status != PUBLICATION_STATUS_PUBLISHED:
                continue
            identity = (doc.object_type, doc.canonical_id)
            if identity in global_seen:
                cross_dups += 1
            else:
                global_seen.add(identity)

        self.assertEqual(cross_dups, 1, "D2: cross-adapter duplicate must be detected")

    def test_D3_duplicate_blocks_promotion_store_guard(self):
        """D3: When rebuild detects duplicate and calls fail_run, promote() is blocked."""
        from unittest.mock import MagicMock
        from services.shared_search.opensearch_store import (
            OpenSearchSearchStore, RebuildRejected, RUN_STATUS_FAILED
        )
        mc = MagicMock()
        mc.indices.exists.return_value = False
        mc.indices.create.return_value = {}
        mc.index.return_value = {}
        mc.get.return_value = {"_source": {"status": RUN_STATUS_FAILED,
                                            "failed_bulk_items": 0,
                                            "expected_count": 0, "indexed_count": 0,
                                            "previous_index": None}}
        mc.update.return_value = {}
        mc.indices.update_aliases.return_value = {}
        store = OpenSearchSearchStore(mc)

        # Simulate: fail_run() was called due to duplicate
        store.fail_run("run-dup", "Duplicate identity detected")

        # promote() must be blocked
        with self.assertRaises(RebuildRejected) as ctx:
            store.promote("run-dup")
        self.assertIn("VALIDATED", str(ctx.exception))
        # alias must not have been touched
        mc.indices.update_aliases.assert_not_called()

    def test_D3_alias_unchanged_on_duplicate(self):
        """D3: update_aliases is never called when duplicate detection fails the run."""
        from unittest.mock import MagicMock
        from services.shared_search.opensearch_store import (
            OpenSearchSearchStore, RebuildRejected, RUN_STATUS_FAILED
        )
        mc = MagicMock()
        mc.get.return_value = {"_source": {"status": RUN_STATUS_FAILED,
                                            "failed_bulk_items": 0,
                                            "expected_count": 0, "indexed_count": 0,
                                            "previous_index": None}}
        mc.update.return_value = {}
        store = OpenSearchSearchStore(mc)
        try:
            store.promote("run-dup2")
        except RebuildRejected:
            pass
        mc.indices.update_aliases.assert_not_called()

    def test_no_id_aggregation_in_opensearch_store(self):
        """OpenSearch _id is not aggregatable. Cardinality agg code must not exist."""
        import pathlib
        src = pathlib.Path("services/shared_search/opensearch_store.py").read_text()
        # Check for actual aggregation code (not docstring mentions)
        self.assertNotIn('cardinality(field="_id"', src)
        self.assertNotIn('"cardinality":', src)
        self.assertNotIn("precision_threshold", src)
        self.assertNotIn("check_duplicates", src)

    def test_global_seen_is_before_bulk_write(self):
        """global_seen check must appear before stage_documents call in rebuild source."""
        import pathlib
        src = pathlib.Path("tools/shared_search/opensearch_rebuild.py").read_text()
        idx_global = src.find("global_seen")
        idx_stage  = src.find("stage_documents")
        self.assertGreater(idx_global, 0, "global_seen must exist")
        self.assertGreater(idx_stage, 0, "stage_documents must exist")
        self.assertLess(idx_global, idx_stage,
                        "global_seen must appear before stage_documents")


class TestWithinSearch(unittest.TestCase):
    """WO-MKT-SEARCH-02 Within Search — B01-B10."""

    # ------------------------------------------------------------------
    # Shared fixtures
    # ------------------------------------------------------------------

    def _doc_with_text(self, cid, title, search_text="", summary="", aliases=None, keywords=None):
        return {
            "object_type": "GUIDE",
            "canonical_id": cid,
            "title": title,
            "source_id": "KOSHA",
            "source_key": None,
            "summary": summary,
            "aliases": aliases or [],
            "keywords": keywords or [],
            "subjects": [],
            "context": [],
            "public_url": f"/guide/{cid}",
            "saas_url": None,
            "publication_status": "PUBLISHED",
            "visibility_scopes": ["PUBLIC"],
            "source_updated_at": "2026-09-19T00:00:00+00:00",
            "search_text": search_text,
            "content_hash": "abc",
        }

    def _forklift_doc(self, cid="fork-001"):
        return self._doc_with_text(cid, "지게차 안전작업", search_text="지게차 안전 작업 매뉴얼")

    def _crane_doc(self, cid="crane-001"):
        return self._doc_with_text(cid, "크레인 안전", search_text="크레인 안전 지침")

    # ------------------------------------------------------------------
    # B01: within=None yields same results as omitting within
    # ------------------------------------------------------------------

    def test_B01_within_None_equals_no_within(self):
        """B01: within=None → same result count as baseline (no narrowing)."""
        engine = _engine(self._forklift_doc(), self._crane_doc())
        r_none   = engine.search("안전", within_query=None)
        r_base   = engine.search("안전")
        self.assertEqual(r_none.total, r_base.total)
        self.assertEqual(
            [i.canonical_id for i in r_none.items],
            [i.canonical_id for i in r_base.items],
        )

    # ------------------------------------------------------------------
    # B02: within single token filters to matching docs only
    # ------------------------------------------------------------------

    def test_B02_within_single_token_filters(self):
        """B02: within='지게차' keeps only docs whose text contains '지게차'."""
        engine = _engine(self._forklift_doc(), self._crane_doc())
        result = engine.search("안전", within_query="지게차")
        cids = {r.canonical_id for r in result.items}
        self.assertIn("fork-001", cids,    "forklift doc must survive within filter")
        self.assertNotIn("crane-001", cids, "crane doc must be filtered out")

    # ------------------------------------------------------------------
    # B03: within="" is treated as no within (ignored)
    # ------------------------------------------------------------------

    def test_B03_within_empty_string_ignored(self):
        """B03: within='' → same as within=None, no narrowing applied."""
        engine = _engine(self._forklift_doc(), self._crane_doc())
        r_empty = engine.search("안전", within_query="")
        r_none  = engine.search("안전", within_query=None)
        self.assertEqual(r_empty.total, r_none.total)

    # ------------------------------------------------------------------
    # B04: within multi-token is AND across tokens
    # ------------------------------------------------------------------

    def test_B04_within_multi_token_AND(self):
        """B04: within='지게차 안전' keeps only docs containing BOTH tokens."""
        doc_both   = self._doc_with_text("both-001", "지게차 안전", search_text="지게차 안전 관련 내용")
        doc_fork   = self._doc_with_text("fork-002", "지게차만", search_text="지게차 운전 방법")
        doc_safety = self._doc_with_text("safe-001", "안전만", search_text="일반 안전 지침")
        engine = _engine(doc_both, doc_fork, doc_safety)
        result = engine.search("안전", within_query="지게차 안전")
        cids = {r.canonical_id for r in result.items}
        self.assertIn("both-001", cids,    "doc with both tokens must survive")
        self.assertNotIn("fork-002", cids, "doc missing '안전' must be filtered")
        self.assertNotIn("safe-001", cids, "doc missing '지게차' must be filtered")

    # ------------------------------------------------------------------
    # B05: within all-excluded returns empty
    # ------------------------------------------------------------------

    def test_B05_within_all_excluded_returns_empty(self):
        """B05: within='존재하지않는키워드' → 0 results, status='empty'."""
        engine = _engine(self._forklift_doc(), self._crane_doc())
        result = engine.search("안전", within_query="존재하지않는키워드")
        self.assertEqual(result.total, 0)
        self.assertEqual(result.status, "empty")

    # ------------------------------------------------------------------
    # B06: within does not change tier precedence order
    # ------------------------------------------------------------------

    def test_B06_within_does_not_change_tier_order(self):
        """B06: Within filter narrows set but winner tier ranking is unchanged.

        If doc A (TITLE_EXACT match) and doc B (BM25_NORI match) both pass
        within, doc A must still rank higher.
        """
        # q = "지게차" → title exact hit on fork-A
        doc_a = self._doc_with_text("fork-A", "지게차", search_text="지게차 안전")
        doc_b = self._doc_with_text("fork-B", "산업 안전", search_text="지게차 산업 안전 내용")
        engine = _engine(doc_a, doc_b)
        result = engine.search("지게차", within_query="안전")
        self.assertGreater(result.total, 0)
        # doc_a wins via TITLE_EXACT (lower tier_idx = higher precedence)
        top = result.items[0]
        self.assertEqual(top.canonical_id, "fork-A")
        self.assertLessEqual(
            top.rank_tier,
            result.items[-1].rank_tier if len(result.items) > 1 else top.rank_tier,
        )

    # ------------------------------------------------------------------
    # B07: _inject_within adds clauses to bool.filter (not must)
    # ------------------------------------------------------------------

    def test_B07_inject_within_adds_filter_context(self):
        """B07: _inject_within appends within clauses to bool.filter, not bool.must."""
        from services.shared_search.opensearch_reader import _inject_within

        base_query = {
            "query": {
                "bool": {
                    "must": [{"term": {"title.raw": "지게차"}}],
                    "filter": [{"term": {"publication_status": "PUBLISHED"}}],
                }
            },
            "size": 200,
        }
        result = _inject_within(base_query, "지게차 안전")
        bool_q = result["query"]["bool"]

        # must is unchanged
        self.assertEqual(len(bool_q["must"]), 1)
        # filter has original + 2 new within clauses (one per token)
        self.assertEqual(len(bool_q["filter"]), 3)  # 1 original + 2 tokens
        # original query is not mutated
        self.assertEqual(len(base_query["query"]["bool"]["filter"]), 1)

    # ------------------------------------------------------------------
    # B08: _within_filter produces one bool.should clause per token
    # ------------------------------------------------------------------

    def test_B08_within_filter_multi_token_AND_clauses(self):
        """B08: _within_filter('a b') returns 2 clauses, each a bool.should over all fields."""
        from services.shared_search.opensearch_reader import _within_filter

        clauses = _within_filter("지게차 안전")
        self.assertEqual(len(clauses), 2, "one clause per token")
        for clause in clauses:
            self.assertIn("bool", clause)
            self.assertIn("should", clause["bool"])
            # each should branch covers 5 fields
            self.assertEqual(len(clause["bool"]["should"]), 5)

    # ------------------------------------------------------------------
    # B09: FUZZY fallback also applies within filter
    # ------------------------------------------------------------------

    def test_B09_fuzzy_within_pass_through(self):
        """B09: run_fuzzy with within_query returns only within-matching docs."""
        reader = MemorySearchReader([
            self._forklift_doc("fork-001"),
            self._crane_doc("crane-001"),
        ])
        fuzzy_all    = reader.run_fuzzy("안", object_types=[], visibility=["PUBLIC"])
        fuzzy_within = reader.run_fuzzy("안", object_types=[], visibility=["PUBLIC"],
                                        within_query="지게차")
        all_cids    = {d["canonical_id"] for d in fuzzy_all}
        within_cids = {d["canonical_id"] for d in fuzzy_within}

        self.assertIn("fork-001", all_cids)
        self.assertIn("crane-001", all_cids)
        self.assertIn("fork-001", within_cids)
        self.assertNotIn("crane-001", within_cids,
                         "crane doc does not contain '지게차', must be excluded")

    # ------------------------------------------------------------------
    # B10: SharedRetrievalEngine.search passes within_query to plan
    # ------------------------------------------------------------------

    def test_B10_engine_search_passes_within_to_plan(self):
        """B10: engine.search(within_query='X') passes within_query through to plan."""
        from unittest.mock import patch as _patch, MagicMock

        captured = {}

        def fake_retrieve(plan, reader, **kwargs):
            captured["within_query"] = plan.within_query
            resp = MagicMock()
            resp.total = 0
            resp.items = []
            resp.active_tiers = []
            resp.status = "empty"
            return resp

        with _patch("services.shared_search.retrieval.retrieve", side_effect=fake_retrieve):
            engine = _engine(self._forklift_doc())
            engine.search("안전", within_query="지게차")

        self.assertEqual(captured.get("within_query"), "지게차")


if __name__ == "__main__":
    unittest.main()
