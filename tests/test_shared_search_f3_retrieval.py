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


if __name__ == "__main__":
    unittest.main()
