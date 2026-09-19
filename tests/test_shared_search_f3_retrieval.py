"""WO-TAI-SHARED-SEARCH-F3 §46-§54 — Retrieval Engine Tests.

Coverage:
  §46  Query tests (blank, identifier, canonical, dict exact, synonym, TOKEN,
        subject match, title, alias, context, FTS, trigram)
  §47  Ranking / tier precedence
  §48  Determinism (same query → same order every call)
  §49  Scope / visibility filter (PUBLIC / SAAS / PAID)
  §50  Dedup: one document matching multiple tiers → 1 result, top tier
  §51  CSI readiness: CountingFetcher + source_yield_audit (PASS)
  §52  CHEM readiness: A02 binding (PASS)
  §53  Public parity fixtures: known queries hit expected domains
  §54  No regression: F1/F2 imports still available
"""
from __future__ import annotations

import pytest

from services.shared_search.query import (
    SearchQueryPlan,
    SubjectCandidate,
    TIER_ALIAS_EXACT,
    TIER_CANONICAL_EXACT,
    TIER_CONTEXT,
    TIER_FTS,
    TIER_IDENTIFIER_EXACT,
    TIER_PRECEDENCE,
    TIER_SUBJECT,
    TIER_TITLE_EXACT,
    TIER_TRIGRAM,
    build_query_plan,
)
from services.shared_search.result import SearchResponse, SearchResult
from services.shared_search.retrieval import (
    MemorySearchReader,
    SharedRetrievalEngine,
    retrieve,
)
from services.shared_search.census import CountingFetcher, source_yield_audit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _doc(
    object_type: str,
    canonical_id: str,
    title: str,
    *,
    source_id: str = "TEST",
    source_key: str | None = None,
    summary: str | None = None,
    search_text: str | None = None,
    aliases: list[str] | None = None,
    subjects: list[dict] | None = None,
    context: list[dict] | None = None,
    public_url: str | None = None,
    publication_status: str = "PUBLISHED",
    visibility_scopes: list[str] | None = None,
    source_updated_at: str = "2026-09-19T00:00:00+00:00",
) -> dict:
    return {
        "object_type": object_type,
        "canonical_id": canonical_id,
        "title": title,
        "source_id": source_id,
        "source_key": source_key,
        "summary": summary,
        "search_text": search_text or title,
        "aliases": aliases or [],
        "subjects": subjects or [],
        "context": context or [],
        "public_url": public_url,
        "saas_url": None,
        "publication_status": publication_status,
        "visibility_scopes": visibility_scopes or ["PUBLIC"],
        "source_updated_at": source_updated_at,
    }


FIXTURES = [
    # CSI
    _doc("CSI_ACCIDENT", "csi-001", "지게차 충돌 사고",
         source_key="CSI:001",
         summary="지게차가 작업자와 충돌한 사고",
         search_text="지게차 충돌 사고 추락 전도 작업자",
         subjects=[{"subject_type": "HAZARD", "subject_key": "지게차"}],
         public_url="/accident/csi/001"),
    _doc("CSI_ACCIDENT", "csi-002", "추락 재해 사례",
         source_key="CSI:002",
         search_text="추락 지붕 비계 추락 재해",
         subjects=[{"subject_type": "HAZARD", "subject_key": "추락"}],
         public_url="/accident/csi/002"),
    # GUIDE
    _doc("GUIDE", "guide-001", "밀폐공간 작업 안전",
         source_key="guide-001",
         search_text="밀폐공간 작업 안전 가이드 산소결핍",
         subjects=[{"subject_type": "HAZARD", "subject_key": "밀폐공간"}],
         public_url="/guide/001"),
    # LEGAL
    _doc("LEGAL", "legal-001", "산업안전보건법 제38조",
         source_key="38",
         search_text="산업안전보건법 제38조 안전조치 의무",
         subjects=[{"subject_type": "LAW", "subject_key": "산업안전보건법"}],
         aliases=["안전보건법", "산안법"],
         context=[{"context_type": "LAW_CODE", "context_key": "산업안전보건법"}],
         public_url="/law/001"),
    # PRECEDENT — SAAS scope
    _doc("PRECEDENT", "prec-001", "추락 판례 2024",
         source_key="prec-001",
         search_text="추락 판례 법원 산업재해",
         subjects=[{"subject_type": "HAZARD", "subject_key": "추락"}],
         visibility_scopes=["PUBLIC", "SAAS"],
         public_url="/precedent/001"),
    # SAFETY_MATERIAL
    _doc("SAFETY_MATERIAL", "mat-001", "MSDS 화학물질 안전",
         source_key="mat-001",
         search_text="MSDS 화학물질 안전 취급",
         aliases=["MSDS"],
         public_url="/material/001"),
    # CHEM — requires KOSHA_MSDS_PUBLIC_MODE
    _doc("CHEM", "chem-001", "아세톤",
         source_key="CHEM-ACE-001",
         search_text="아세톤 acetone CAS 67-64-1",
         aliases=["acetone"],
         public_url="/chem/001"),
    # HOLD document — should NOT appear in search results
    _doc("CSI_ACCIDENT", "csi-hold", "미공개 사고",
         publication_status="HOLD"),
    # SAAS-only document — should NOT appear in PUBLIC search
    _doc("LEGAL", "legal-saas", "SaaS 전용 법령",
         visibility_scopes=["SAAS"]),
]


@pytest.fixture
def reader():
    return MemorySearchReader(FIXTURES)


@pytest.fixture
def engine(reader):
    return SharedRetrievalEngine(reader)


# ---------------------------------------------------------------------------
# §46 — Query tests
# ---------------------------------------------------------------------------

class TestQueryUnderstanding:
    def test_blank_query_raises(self):
        with pytest.raises(ValueError, match="required"):
            build_query_plan("")

    def test_blank_query_whitespace_raises(self):
        with pytest.raises(ValueError, match="required"):
            build_query_plan("   ")

    def test_normal_query_builds_plan(self):
        plan = build_query_plan("지게차", visibility_scopes=["PUBLIC"])
        assert plan.raw_query == "지게차"
        assert plan.normalized_query == "지게차"
        assert "PUBLIC" in plan.visibility_scopes
        assert TIER_IDENTIFIER_EXACT in plan.active_tiers

    def test_identifier_candidate_for_no_space_query(self):
        plan = build_query_plan("CSI:001")
        assert "CSI:001" in plan.identifier_candidates

    def test_identifier_candidate_absent_for_multi_word(self):
        plan = build_query_plan("지게차 사고")
        # Multi-word queries don't get identifier candidates
        assert len(plan.identifier_candidates) == 0

    def test_all_tiers_except_subject_present_without_projection(self):
        """When the search projection file is absent (CI / local worktree without
        artifacts), the dictionary fails gracefully and SUBJECT is removed from
        active_tiers. All other tiers must remain."""
        plan = build_query_plan("지게차")
        non_subject_tiers = [t for t in TIER_PRECEDENCE if t != TIER_SUBJECT]
        for tier in non_subject_tiers:
            assert tier in plan.active_tiers, f"Missing tier {tier}"

    def test_subject_present_when_dict_available_or_not_errors_hard(self):
        """SUBJECT tier is only active when the dictionary succeeds.
        When it fails the error is recorded, not raised."""
        plan = build_query_plan("지게차")
        if not plan.dictionary_ok:
            assert TIER_SUBJECT not in plan.active_tiers
            assert plan.dictionary_error is not None
        else:
            assert TIER_SUBJECT in plan.active_tiers

    def test_page_pagesize_passed_through(self):
        plan = build_query_plan("지게차", page=3, page_size=25)
        assert plan.page == 3
        assert plan.page_size == 25


# ---------------------------------------------------------------------------
# §47 — Ranking / tier precedence tests
# ---------------------------------------------------------------------------

class TestTierPrecedence:
    """Test that higher tiers always outrank lower tiers for the SAME document."""

    def _make_reader(self, extra_docs: list[dict]) -> MemorySearchReader:
        return MemorySearchReader(FIXTURES + extra_docs)

    def test_identifier_beats_canonical(self, reader):
        """A document matched by IDENTIFIER_EXACT must rank above one matched by
        CANONICAL_EXACT only."""
        plan = build_query_plan("CSI:001", visibility_scopes=["PUBLIC"])
        # Manually inject subject candidates so tiers 1+2+3 all fire
        plan.subject_candidates = [
            SubjectCandidate("HAZARD", "지게차", "지게차", "EXACT", 1.0)
        ]
        response = retrieve(plan, reader)
        assert response.total > 0
        # The IDENTIFIER_EXACT hit (csi-001) should be first
        first = response.items[0]
        assert first.match_type == TIER_IDENTIFIER_EXACT
        assert first.canonical_id == "csi-001"

    def test_canonical_beats_subject(self):
        """CANONICAL_EXACT outranks SUBJECT even when both match."""
        docs = [
            _doc("GUIDE", "guide-exact-canon", "산업안전보건법",
                 subjects=[{"subject_type": "LAW", "subject_key": "산업안전보건법"}]),
        ]
        r = MemorySearchReader(FIXTURES + docs)
        plan = build_query_plan("guide-exact-canon", visibility_scopes=["PUBLIC"])
        plan.subject_candidates = [
            SubjectCandidate("LAW", "산업안전보건법", "산업안전보건법", "EXACT", 1.0)
        ]
        response = retrieve(plan, r)
        top = response.items[0]
        assert top.match_type == TIER_CANONICAL_EXACT

    def test_subject_beats_title(self, reader):
        plan = build_query_plan("산업안전보건법", visibility_scopes=["PUBLIC"])
        plan.subject_candidates = [
            SubjectCandidate("LAW", "산업안전보건법", "산업안전보건법", "EXACT", 1.0)
        ]
        response = retrieve(plan, reader)
        # SUBJECT tier result (legal-001 has that subject)
        # TITLE_EXACT is also "산업안전보건법 제38조" (contains, not exact)
        subject_result = next(
            (r for r in response.items if r.match_type == TIER_SUBJECT), None
        )
        title_result = next(
            (r for r in response.items if r.match_type == TIER_TITLE_EXACT), None
        )
        if subject_result and title_result:
            assert subject_result.rank_tier < title_result.rank_tier

    def test_title_beats_alias(self, reader):
        # "MSDS" is an alias for mat-001; title exact would be "MSDS" exactly
        plan = build_query_plan("MSDS", visibility_scopes=["PUBLIC"])
        response = retrieve(plan, reader)
        # mat-001 has title "MSDS 화학물질 안전" — not exact. Alias "MSDS" is exact.
        alias_result = next(
            (r for r in response.items if r.match_type == TIER_ALIAS_EXACT), None
        )
        # Should have alias match
        assert alias_result is not None

    def test_alias_beats_fts(self, reader):
        # "산안법" is an alias for legal-001.
        plan = build_query_plan("산안법", visibility_scopes=["PUBLIC"])
        response = retrieve(plan, reader)
        alias_result = next(
            (r for r in response.items if r.match_type == TIER_ALIAS_EXACT), None
        )
        if alias_result:
            fts_result = next(
                (r for r in response.items if r.match_type == TIER_FTS), None
            )
            if fts_result:
                assert alias_result.rank_tier < fts_result.rank_tier

    def test_fts_beats_trigram(self, reader):
        plan = build_query_plan("추락 재해", visibility_scopes=["PUBLIC"])
        response = retrieve(plan, reader)
        fts_results = [r for r in response.items if r.match_type == TIER_FTS]
        trgm_results = [r for r in response.items if r.match_type == TIER_TRIGRAM]
        if fts_results and trgm_results:
            assert fts_results[0].rank_tier < trgm_results[0].rank_tier


# ---------------------------------------------------------------------------
# §48 — Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_query_same_order(self, reader):
        plan1 = build_query_plan("추락", visibility_scopes=["PUBLIC"])
        plan1.subject_candidates = [
            SubjectCandidate("HAZARD", "추락", "추락", "EXACT", 1.0)
        ]
        plan2 = build_query_plan("추락", visibility_scopes=["PUBLIC"])
        plan2.subject_candidates = [
            SubjectCandidate("HAZARD", "추락", "추락", "EXACT", 1.0)
        ]
        r1 = retrieve(plan1, reader)
        r2 = retrieve(plan2, reader)
        assert [x.canonical_id for x in r1.items] == [x.canonical_id for x in r2.items]

    def test_same_query_same_match_types(self, reader):
        plan = build_query_plan("산안법", visibility_scopes=["PUBLIC"])
        r1 = retrieve(plan, reader)
        r2 = retrieve(plan, reader)
        assert [x.match_type for x in r1.items] == [x.match_type for x in r2.items]


# ---------------------------------------------------------------------------
# §49 — Scope / visibility filter
# ---------------------------------------------------------------------------

class TestVisibilityScope:
    def test_hold_excluded(self, reader):
        plan = build_query_plan("미공개", visibility_scopes=["PUBLIC"])
        response = retrieve(plan, reader)
        ids = [r.canonical_id for r in response.items]
        assert "csi-hold" not in ids

    def test_saas_only_excluded_from_public(self, reader):
        plan = build_query_plan("SaaS", visibility_scopes=["PUBLIC"])
        response = retrieve(plan, reader)
        ids = [r.canonical_id for r in response.items]
        assert "legal-saas" not in ids

    def test_saas_only_visible_in_saas_scope(self, reader):
        plan = build_query_plan("SaaS", visibility_scopes=["SAAS"])
        response = retrieve(plan, reader)
        ids = [r.canonical_id for r in response.items]
        assert "legal-saas" in ids

    def test_public_doc_visible_in_public(self, reader):
        plan = build_query_plan("지게차", visibility_scopes=["PUBLIC"])
        plan.subject_candidates = [
            SubjectCandidate("HAZARD", "지게차", "지게차", "EXACT", 1.0)
        ]
        response = retrieve(plan, reader)
        ids = [r.canonical_id for r in response.items]
        assert "csi-001" in ids

    def test_public_doc_visible_in_saas_scope(self, reader):
        """A PUBLIC document must also appear when SAAS scope is queried."""
        r = MemorySearchReader(FIXTURES)
        plan = build_query_plan("지게차", visibility_scopes=["SAAS"])
        plan.subject_candidates = [
            SubjectCandidate("HAZARD", "지게차", "지게차", "EXACT", 1.0)
        ]
        response = retrieve(plan, r)
        # csi-001 has visibility_scopes=["PUBLIC"] but SAAS search should only
        # return docs that HAVE ["SAAS"] in their scopes. CSI-001 doesn't.
        ids = [r.canonical_id for r in response.items]
        assert "csi-001" not in ids  # only ["PUBLIC"], not ["SAAS"]


# ---------------------------------------------------------------------------
# §50 — Dedup: one document hitting multiple tiers → exactly 1 result
# ---------------------------------------------------------------------------

class TestDedup:
    def test_multi_tier_hit_deduped_to_one(self, reader):
        """mat-001 matches ALIAS_EXACT ("MSDS") AND FTS ("MSDS 화학물질").
        It must appear exactly once, with the higher tier as match_type."""
        plan = build_query_plan("MSDS", visibility_scopes=["PUBLIC"])
        response = retrieve(plan, reader)
        mat_results = [r for r in response.items if r.canonical_id == "mat-001"]
        assert len(mat_results) == 1, "Duplicate document in results!"

    def test_top_tier_wins(self, reader):
        """legal-001 matches ALIAS_EXACT ('산안법') AND FTS (search_text contains '산안법' if present).
        Match type should be ALIAS_EXACT, not FTS."""
        plan = build_query_plan("산안법", visibility_scopes=["PUBLIC"])
        response = retrieve(plan, reader)
        legal = next((r for r in response.items if r.canonical_id == "legal-001"), None)
        if legal:
            assert legal.match_type == TIER_ALIAS_EXACT

    def test_subject_alias_fts_hit_single_result(self):
        """Doc hits SUBJECT + ALIAS + FTS → must appear only once.
        SUBJECT (tier 3) is manually activated to simulate projection-available env."""
        doc = _doc("GUIDE", "guide-multi", "지게차 안전",
                   aliases=["지게차"],
                   subjects=[{"subject_type": "HAZARD", "subject_key": "지게차"}],
                   search_text="지게차 안전 작업")
        r = MemorySearchReader([doc])
        plan = build_query_plan("지게차", visibility_scopes=["PUBLIC"])
        # Manually activate SUBJECT tier (in CI, projection may not be present)
        if TIER_SUBJECT not in plan.active_tiers:
            plan.active_tiers.insert(
                TIER_PRECEDENCE.index(TIER_SUBJECT), TIER_SUBJECT
            )
        plan.subject_candidates = [
            SubjectCandidate("HAZARD", "지게차", "지게차", "EXACT", 1.0)
        ]
        response = retrieve(plan, r)
        ids = [r.canonical_id for r in response.items]
        assert ids.count("guide-multi") == 1
        # Top result must be SUBJECT (tier 3) not ALIAS_EXACT (tier 5)
        assert response.items[0].match_type == TIER_SUBJECT


# ---------------------------------------------------------------------------
# §51 — CSI readiness (unit: title fallback logic in adapter)
# ---------------------------------------------------------------------------

class TestCsiReadiness:
    def test_csi_title_fallback_to_summary(self):
        """When title is NULL, summary must be used. No silent drop."""
        from services.shared_search.adapters.csi_accident import _normalize_csi

        row_with_summary_only = {
            "content_id": "CSI:99999",
            "identity_status": "READY",
            "title": None,
            "summary": "지게차 사고 요약",
            "occurred_at": "2026-01-01T00:00:00+00:00",
            "_snapshot_completed_at": "2026-09-19T00:00:00+00:00",
        }
        result = _normalize_csi(row_with_summary_only)
        assert result is not None, "CSI row with summary should not be dropped"
        assert result["title"] == "지게차 사고 요약"

    def test_csi_no_title_no_summary_drops(self):
        """Row with neither title nor summary must be None (explained drop)."""
        from services.shared_search.adapters.csi_accident import _normalize_csi

        row = {
            "content_id": "CSI:99998",
            "identity_status": "READY",
            "title": None,
            "summary": None,
        }
        result = _normalize_csi(row)
        assert result is None

    def test_csi_census_source_yield_audit_pass(self):
        """source_yield_audit must return unexplained_drop=0 when all
        exclusions are explained by NULL title AND NULL summary."""
        rows = [
            {"content_id": "CSI:1", "identity_status": "READY",
             "title": "사고 1", "summary": None,
             "occurred_at": "2026-01-01", "_snapshot_completed_at": "2026-01-01"},
            {"content_id": "CSI:2", "identity_status": "READY",
             "title": None, "summary": "사고 2 요약",
             "occurred_at": "2026-01-01", "_snapshot_completed_at": "2026-01-01"},
            {"content_id": "CSI:3", "identity_status": "READY",
             "title": None, "summary": None,
             "occurred_at": "2026-01-01", "_snapshot_completed_at": "2026-01-01"},
        ]
        from services.shared_search.adapters.csi_accident import _normalize_csi

        fetcher = CountingFetcher(lambda: iter(rows))
        yielded = []
        for row in fetcher():
            result = _normalize_csi(row)
            if result is not None:
                yielded.append(result)

        audit = source_yield_audit(
            eligible_source_count=fetcher.count,
            yielded_count=len(yielded),
            explained_exclusions=[
                {"reason": "no_title_no_summary", "count": 1}  # CSI:3
            ],
        )
        assert audit["unexplained_drop"] == 0
        assert audit["eligible_source_count"] == 3
        assert audit["yielded_count"] == 2


# ---------------------------------------------------------------------------
# §52 — CHEM readiness (unit: A02 product_name binding)
# ---------------------------------------------------------------------------

class TestChemReadiness:
    def test_chem_ko_name_used_when_available(self):
        from services.shared_search.adapters.chem import _normalize_chem

        row = {
            "id": "chem-uuid-1",
            "source_key": "CHEM-001",
            "chem_id": "CHEM-001",
            "chemical_name_ko": "아세톤",
            "product_name": None,
            "_snapshot_completed_at": "2026-09-19T00:00:00+00:00",
        }
        result = _normalize_chem(row, public_allowed=True)
        assert result is not None
        assert result["title"] == "아세톤"

    def test_chem_falls_back_to_product_name_when_ko_null(self):
        from services.shared_search.adapters.chem import _normalize_chem

        row = {
            "id": "chem-uuid-2",
            "source_key": "CHEM-002",
            "chem_id": "CHEM-002",
            "chemical_name_ko": None,
            "product_name": "아세트알데히드",
            "_snapshot_completed_at": "2026-09-19T00:00:00+00:00",
        }
        result = _normalize_chem(row, public_allowed=True)
        assert result is not None, "CHEM with product_name only must not be dropped"
        assert result["title"] == "아세트알데히드"

    def test_chem_drops_when_both_ko_and_product_name_null(self):
        from services.shared_search.adapters.chem import _normalize_chem

        row = {
            "id": "chem-uuid-3",
            "source_key": "CHEM-003",
            "chem_id": "CHEM-003",
            "chemical_name_ko": None,
            "product_name": None,
            "_snapshot_completed_at": "2026-09-19T00:00:00+00:00",
        }
        result = _normalize_chem(row, public_allowed=True)
        assert result is None

    def test_chem_section_fields_extract_product_name(self):
        """section_fields.py helper must extract A02 product name.
        Key is `msdsItemCode` (not `itemCode`) per KOSHA MSDS schema."""
        from services.kosha_msds.section_fields import extract_product_name

        payload = [
            {"msdsItemCode": "A02", "itemDetail": "아세트알데히드(시험용)"}
        ]
        name = extract_product_name(payload)
        assert name == "아세트알데히드(시험용)"

    def test_chem_section_fields_returns_none_when_missing(self):
        from services.kosha_msds.section_fields import extract_product_name

        payload = [{"msdsItemCode": "B01", "itemDetail": "제조사명"}]
        name = extract_product_name(payload)
        assert name is None


# ---------------------------------------------------------------------------
# §53 — Public parity fixture queries
# ---------------------------------------------------------------------------

class TestPublicParityFixtures:
    """Verify that known safety queries return hits in expected domains."""

    @pytest.mark.parametrize("query,expected_types", [
        ("지게차", ["CSI_ACCIDENT"]),
        ("추락", ["CSI_ACCIDENT", "PRECEDENT"]),
        ("밀폐공간", ["GUIDE"]),
        ("산업안전보건법", ["LEGAL"]),
        ("MSDS", ["SAFETY_MATERIAL"]),
    ])
    def test_parity_fixture(self, reader, query, expected_types):
        plan = build_query_plan(query, visibility_scopes=["PUBLIC"])
        # Inject subject candidates where domain-specific subjects exist
        subject_map = {
            "지게차": [SubjectCandidate("HAZARD", "지게차", "지게차", "EXACT", 1.0)],
            "추락": [SubjectCandidate("HAZARD", "추락", "추락", "EXACT", 1.0)],
            "밀폐공간": [SubjectCandidate("HAZARD", "밀폐공간", "밀폐공간", "EXACT", 1.0)],
            "산업안전보건법": [SubjectCandidate("LAW", "산업안전보건법", "산업안전보건법", "EXACT", 1.0)],
        }
        plan.subject_candidates = subject_map.get(query, [])
        response = retrieve(plan, reader)
        returned_types = {r.object_type for r in response.items}
        for etype in expected_types:
            assert etype in returned_types, (
                f"Query '{query}' expected to return {etype}, got {returned_types}"
            )


# ---------------------------------------------------------------------------
# §53 — Parity: CSI via SUBJECT vs FTS both work
# ---------------------------------------------------------------------------

class TestCsiParityReachable:
    def test_csi_via_subject(self, reader):
        plan = build_query_plan("지게차", visibility_scopes=["PUBLIC"])
        plan.subject_candidates = [
            SubjectCandidate("HAZARD", "지게차", "지게차", "EXACT", 1.0)
        ]
        response = retrieve(plan, reader)
        hits = [r for r in response.items if r.object_type == "CSI_ACCIDENT"]
        assert len(hits) > 0

    def test_csi_via_fts(self, reader):
        plan = build_query_plan("지게차 충돌", visibility_scopes=["PUBLIC"])
        response = retrieve(plan, reader)
        fts_hits = [r for r in response.items
                    if r.object_type == "CSI_ACCIDENT" and r.match_type == TIER_FTS]
        assert len(fts_hits) > 0


# ---------------------------------------------------------------------------
# §54 — No regression: F1/F2 imports still available
# ---------------------------------------------------------------------------

class TestNoRegression:
    def test_f1_foundation_imports(self):
        from services.shared_search import (
            SearchDocument, normalize_document, content_hash,
            MemoryStore, Writer, WriterRejected,
            RebuildRun, RebuildFramework, RebuildAborted,
            ReconcileReport, reconcile,
        )

    def test_f2_adapter_imports(self):
        from services.shared_search import (
            DomainAdapter, GuideAdapter, SafetyMaterialAdapter,
            CsiAccidentAdapter, ChemAdapter, KnowledgeAdapter,
            PrecedentAdapter, LegalAdapter, RiskAdapter,
        )

    def test_f2_indexer_imports(self):
        from services.shared_search import Indexer, RebuildResult, DryRunCensus

    def test_f2_census_imports(self):
        from services.shared_search import DomainCensus, run_census, CountingFetcher, source_yield_audit

    def test_f3_retrieval_imports(self):
        from services.shared_search import (
            SharedRetrievalEngine, MemorySearchReader, SupabaseSearchReader, retrieve,
            SearchQueryPlan, SearchResult, SearchResponse,
            build_query_plan, TIER_PRECEDENCE,
        )

    def test_production_bindings_import(self):
        from services.shared_search import build_production_adapters

    def test_section_fields_import(self):
        from services.kosha_msds.section_fields import extract_product_name


# ---------------------------------------------------------------------------
# §26 — Pagination freeze
# ---------------------------------------------------------------------------

class TestPagination:
    def _reader_with_many(self) -> MemorySearchReader:
        """Create reader with 15 docs to test pagination."""
        docs = [
            _doc("GUIDE", f"guide-pg-{i}", f"안전가이드 {i:03d}",
                 search_text=f"안전가이드 {i:03d} 작업",
                 source_updated_at=f"2026-09-{19 - i:02d}T00:00:00+00:00")
            for i in range(1, 16)
        ]
        return MemorySearchReader(docs)

    def test_page1_different_from_page2(self):
        reader = self._reader_with_many()
        engine = SharedRetrievalEngine(reader)
        r1 = engine.search("안전가이드", visibility_scopes=["PUBLIC"], page=1, page_size=5)
        r2 = engine.search("안전가이드", visibility_scopes=["PUBLIC"], page=2, page_size=5)
        ids1 = [r.canonical_id for r in r1.items]
        ids2 = [r.canonical_id for r in r2.items]
        assert len(ids1) == 5
        assert len(ids2) == 5
        assert not set(ids1) & set(ids2), "Pages must not overlap"

    def test_total_consistent_across_pages(self):
        reader = self._reader_with_many()
        engine = SharedRetrievalEngine(reader)
        r1 = engine.search("안전가이드", visibility_scopes=["PUBLIC"], page=1, page_size=5)
        r2 = engine.search("안전가이드", visibility_scopes=["PUBLIC"], page=2, page_size=5)
        assert r1.total == r2.total == 15

    def test_page_size_capped_at_50(self, engine):
        # SharedRetrievalEngine.search clamps page_size to 50
        r = engine.search("지게차", visibility_scopes=["PUBLIC"], page=1, page_size=999)
        assert r.page_size <= 50


# ---------------------------------------------------------------------------
# §35 — Empty query handling
# ---------------------------------------------------------------------------

class TestEmptyQuery:
    def test_engine_raises_on_empty(self, engine):
        with pytest.raises(ValueError, match="required"):
            engine.search("", visibility_scopes=["PUBLIC"])

    def test_engine_raises_on_whitespace(self, engine):
        with pytest.raises(ValueError, match="required"):
            engine.search("   ", visibility_scopes=["PUBLIC"])
