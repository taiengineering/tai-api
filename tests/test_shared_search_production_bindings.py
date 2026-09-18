"""WO-TAI-SHARED-SEARCH-F2 CO — production bindings + shared census tests.

Uses a duck-typed `FakeSupabase` client that mimics the subset of
`supabase-py`'s Client API the bindings rely on. Zero network.
Zero SearchStore writes. Zero LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import pytest

from services.shared_search import (
    MemoryStore, Indexer,
    build_production_adapters,
    run_census, DomainCensus,
    GuideAdapter,
)


# ---------------------------------------------------------------------------
# FakeSupabase — enough surface to run paginate_supabase + rpc + eq/in_.
# ---------------------------------------------------------------------------


@dataclass
class _Query:
    tables: dict
    table_name: str
    _sel: str = "*"
    _filters: list = field(default_factory=list)
    _order: Optional[tuple] = None
    _range: Optional[tuple] = None
    _limit: Optional[int] = None
    _count_mode: Optional[str] = None

    def select(self, cols, count=None):
        self._sel = cols
        self._count_mode = count
        return self

    def eq(self, col, val):
        self._filters.append(("eq", col, val))
        return self

    def neq(self, col, val):
        self._filters.append(("neq", col, val))
        return self

    def in_(self, col, values):
        self._filters.append(("in", col, list(values)))
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _apply(self):
        rows = list(self.tables.get(self.table_name, []))
        for op, col, val in self._filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == val]
            elif op == "neq":
                rows = [r for r in rows if r.get(col) != val]
            elif op == "in":
                rows = [r for r in rows if r.get(col) in val]
        if self._order is not None:
            col, desc = self._order
            rows.sort(key=lambda r: (r.get(col) is None, r.get(col)),
                      reverse=desc)
        return rows

    def execute(self):
        rows = self._apply()
        count = len(rows)
        if self._range is not None:
            s, e = self._range
            rows = rows[s:e + 1]
        elif self._limit is not None:
            rows = rows[:self._limit]

        class _R:
            def __init__(self, data, count=None):
                self.data = data
                self.count = count

        return _R(rows, count=count if self._count_mode == "exact" else None)


@dataclass
class _RPC:
    name: str
    params: dict
    handler: Callable

    def execute(self):
        rows = self.handler(self.params)

        class _R:
            def __init__(self, data):
                self.data = data

        return _R(rows)


class FakeSupabase:
    def __init__(self, tables: dict, rpc_handlers: Optional[dict] = None):
        # tables: {table_name: [row, ...]}
        self.tables = tables
        self.rpc_handlers = rpc_handlers or {}

    def table(self, name):
        # supabase-py chained builder mutates via upsert/insert too;
        # for READ-only tests we only need query methods below.
        return _Query(tables=self.tables, table_name=name)

    def rpc(self, name, params):
        return _RPC(name, params, self.rpc_handlers.get(name, lambda p: []))


# ---------------------------------------------------------------------------
# build_production_adapters returns 8 adapters
# ---------------------------------------------------------------------------


def _empty_prod_supabase():
    return FakeSupabase(tables={
        "kosha_guide_current": [],
        "kosha_guide_snapshots": [],
        "csi_accident_current": [],
        "csi_accident_snapshots": [],
        "kosha_msds_current": [],
        "kosha_msds_seo_preview_current": [],
        "kosha_msds_snapshots": [],
        "safe_help_content": [],
        "industrial_accident_precedents": [],
        "kosha_safety_materials": [],
        "kosha_safety_material_snapshots": [],
        "kosha_safety_material_snapshot_items": [],
        "kosha_safety_material_details": [],
        "kosha_safety_material_storage_holds": [],
        "law_article_current": [],
    })


def test_registry_builds_all_eight_adapters():
    adapters = build_production_adapters(_empty_prod_supabase())
    names = [a.domain_name for a in adapters]
    assert names == [
        "GUIDE", "SAFETY_MATERIAL", "CSI_ACCIDENT", "CHEM",
        "KNOWLEDGE", "PRECEDENT", "LEGAL", "RISK",
    ]


def test_registry_adapters_yield_nothing_on_empty_supabase():
    adapters = build_production_adapters(_empty_prod_supabase())
    for a in adapters:
        # LEGAL raises AdapterBlockedSubtype when it finishes with any
        # blocked kinds — with an empty source it has none, so it just
        # returns an empty iterator.
        assert list(a.iter_documents()) == []


# ---------------------------------------------------------------------------
# Real Domain shape → production binding → adapter → SearchDocument
# ---------------------------------------------------------------------------


def test_guide_production_binding_uses_real_view_shape():
    """Verified column set from kosha_guide_current view."""
    sb = FakeSupabase(tables={
        "kosha_guide_current": [{
            "id": "g-001",
            "guide_no": "G-2024-01",
            "guide_title": "산업안전보건 관리 지침",
            "category_code": "S",
            "category_name": "안전관리",
            "guide_url": "https://kosha.or.kr/g/1",
            "regist_date": "2026-06-01T00:00:00+00:00",
            "content_hash": "abc",
            "snapshot_id": "snap-guide-001",
        }],
        "kosha_guide_snapshots": [{
            "id": "snap-guide-001",
            "completed_at": "2026-06-01T10:00:00+00:00",
        }],
    })
    adapters = build_production_adapters(sb)
    guide_adapter = next(a for a in adapters if a.domain_name == "GUIDE")
    docs = list(guide_adapter.iter_documents())
    assert len(docs) == 1
    d = docs[0]
    assert d["object_type"] == "GUIDE"
    assert d["canonical_id"] == "g-001"
    assert d["source_key"] == "G-2024-01"     # guide_no, not id
    assert d["public_url"] == "/safety-guide/g-001"


def test_csi_production_binding_filters_ready_only():
    sb = FakeSupabase(tables={
        "csi_accident_current": [
            {"content_id": "CSI:aaa", "identity_status": "READY",
             "title": "사고1", "occurred_at": "2026-03-01T00:00:00+00:00",
             "summary": "요약", "work_process": "용접",
             "snapshot_id": "snap-csi-1"},
            {"content_id": "CSI:bbb", "identity_status": "HOLD",
             "title": "사고2", "occurred_at": "2026-03-02T00:00:00+00:00",
             "snapshot_id": "snap-csi-1"},
        ],
        "csi_accident_snapshots": [{
            "id": "snap-csi-1",
            "completed_at": "2026-03-10T00:00:00+00:00",
        }],
    })
    adapters = build_production_adapters(sb)
    csi_adapter = next(a for a in adapters if a.domain_name == "CSI_ACCIDENT")
    docs = list(csi_adapter.iter_documents())
    assert [d["canonical_id"] for d in docs] == ["CSI:aaa"]
    d = docs[0]
    assert d["source_id"] == "CSI"
    assert d["source_key"] is None
    assert d["public_url"] == "/accident/csi/aaa"


def test_chem_binding_prefers_full_when_populated(monkeypatch):
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    sb = FakeSupabase(tables={
        "kosha_msds_current": [
            {"id": "cf1", "chem_id": "C-FULL", "source_key": "C-FULL",
             "chemical_name_ko": "Full only", "snapshot_id": "snap-full"},
        ],
        "kosha_msds_seo_preview_current": [
            {"id": "cp1", "chem_id": "C-PREV", "source_key": "C-PREV",
             "chemical_name_ko": "Preview only", "snapshot_id": "snap-preview"},
        ],
        "kosha_msds_snapshots": [
            {"id": "snap-full", "completed_at": "2026-08-10T00:00:00+00:00"},
            {"id": "snap-preview", "completed_at": "2026-08-05T00:00:00+00:00"},
        ],
    })
    adapters = build_production_adapters(sb)
    chem_adapter = next(a for a in adapters if a.domain_name == "CHEM")
    docs = list(chem_adapter.iter_documents())
    # FULL view is preferred when non-empty.
    assert [d["canonical_id"] for d in docs] == ["cf1"]


def test_chem_binding_falls_back_to_preview_when_full_empty(monkeypatch):
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    sb = FakeSupabase(tables={
        "kosha_msds_current": [],
        "kosha_msds_seo_preview_current": [
            {"id": "cp1", "chem_id": "C-PREV", "source_key": "C-PREV",
             "chemical_name_ko": "Preview", "snapshot_id": "snap-preview"},
        ],
        "kosha_msds_snapshots": [
            {"id": "snap-preview", "completed_at": "2026-08-05T00:00:00+00:00"},
        ],
    })
    adapters = build_production_adapters(sb)
    chem_adapter = next(a for a in adapters if a.domain_name == "CHEM")
    docs = list(chem_adapter.iter_documents())
    assert [d["canonical_id"] for d in docs] == ["cp1"]


def test_knowledge_binding_uses_real_columns():
    sb = FakeSupabase(tables={
        "safe_help_content": [
            {"doc_id": "h-1", "slug": "s", "title": "How to",
             "question": "Q?", "answer_short": "A.",
             "body": "<p>body</p>",
             "menu_group": "start", "status": "PUBLISHED",
             "updated_at": "2026-04-01T00:00:00+00:00"},
            {"doc_id": "h-2", "slug": "s2", "title": "Draft page",
             "status": "DRAFT",
             "updated_at": "2026-04-01T00:00:00+00:00"},
        ],
    })
    adapters = build_production_adapters(sb)
    knowledge_adapter = next(a for a in adapters if a.domain_name == "KNOWLEDGE")
    docs = list(knowledge_adapter.iter_documents())
    assert [d["canonical_id"] for d in docs] == ["h-1"]
    d = docs[0]
    assert "body" in d["search_text"]        # real body column read
    assert "Q?" in d["search_text"]           # question read
    assert d["summary"] == "A."                # answer_short as summary


def test_precedent_binding_active_only():
    sb = FakeSupabase(tables={
        "industrial_accident_precedents": [
            {"id": "p-1", "case_name": "Case 1",
             "prec_seq": "123", "source": "law_go_kr",
             "is_active": True, "collected_at": "2026-02-01T00:00:00+00:00"},
            {"id": "p-2", "case_name": "Case 2",
             "prec_seq": "456", "source": "law_go_kr",
             "is_active": False, "collected_at": "2026-02-01T00:00:00+00:00"},
        ],
    })
    adapters = build_production_adapters(sb)
    prec_adapter = next(a for a in adapters if a.domain_name == "PRECEDENT")
    docs = list(prec_adapter.iter_documents())
    assert [d["canonical_id"] for d in docs] == ["p-1"]
    assert docs[0]["public_url"] is None      # IAP detail resolver DEFERRED


def test_material_binding_joins_catalog_details_holds():
    sb = FakeSupabase(tables={
        "kosha_safety_materials": [
            {"id": "m-1", "title": "Material 1",
             "url": "https://example/m1",
             "category": "cat", "industry_category": "건설",
             "accident_type": "추락", "product_type": "video"},
            {"id": "m-2", "title": "Material 2",
             "url": "https://example/m2"},
        ],
        "kosha_safety_material_snapshots": [
            {"id": "snap-mat-1", "completed_at": "2026-06-01T00:00:00+00:00",
             "status": "COMPLETED"},
        ],
        "kosha_safety_material_snapshot_items": [
            {"snapshot_id": "snap-mat-1", "material_id": "m-1"},
            {"snapshot_id": "snap-mat-1", "material_id": "m-2"},
        ],
        "kosha_safety_material_details": [
            {"material_id": "m-1", "source_med_seq": 1001,
             "source_title": "Detail 1", "source_description": "desc",
             "source_published_at": "2026-05-01T00:00:00+00:00",
             "source_updated_at": "2026-05-10T00:00:00+00:00"},
        ],
        "kosha_safety_material_storage_holds": [
            {"material_id": "m-2", "resolved": False},
        ],
    })
    adapters = build_production_adapters(sb)
    mat_adapter = next(a for a in adapters if a.domain_name == "SAFETY_MATERIAL")
    docs = list(mat_adapter.iter_documents())
    # m-1 published, m-2 storage hold.
    by_id = {d["canonical_id"]: d for d in docs}
    assert by_id["m-1"]["publication_status"] == "PUBLISHED"
    assert by_id["m-1"]["source_key"] == "1001"
    assert by_id["m-2"]["publication_status"] == "HOLD"
    assert by_id["m-2"]["visibility_scopes"] == []


def test_legal_binding_yields_law_articles_and_reports_block():
    """production binding yields law_article rows and (empty) obligation
    subtypes — obligation_atom source (`legal_obligations`) currently
    has 0 rows in production, so it's not in `law_article_current`."""
    sb = FakeSupabase(tables={
        "law_article_current": [
            {"id": "art-1", "article_internal_key": "law-1/art-1",
             "law_name": "산업안전보건법",
             "article_no": "1", "article_title": "목적",
             "article_text": "이 법은...",
             "published_at": "2026-01-01T00:00:00+00:00"},
        ],
    })
    adapters = build_production_adapters(sb)
    legal_adapter = next(a for a in adapters if a.domain_name == "LEGAL")
    docs = list(legal_adapter.iter_documents())
    assert len(docs) == 1
    d = docs[0]
    assert d["canonical_id"] == "law-1/art-1"  # internal_key preferred
    assert "산업안전보건법" in d["title"]
    assert "제1조" in d["title"]


# ---------------------------------------------------------------------------
# Cross-domain integration through the registry
# ---------------------------------------------------------------------------


def test_registry_full_rebuild_all_domains(monkeypatch):
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    sb = FakeSupabase(tables={
        "kosha_guide_current": [{
            "id": "g-1", "guide_no": "N-1", "guide_title": "Title",
            "regist_date": "2026-01-01T00:00:00+00:00",
            "snapshot_id": "s1",
        }],
        "kosha_guide_snapshots": [{"id": "s1", "completed_at": "2026-01-02T00:00:00+00:00"}],
        "csi_accident_current": [{
            "content_id": "CSI:x", "identity_status": "READY", "title": "T",
            "occurred_at": "2026-01-01T00:00:00+00:00", "snapshot_id": "cs1",
        }],
        "csi_accident_snapshots": [{"id": "cs1", "completed_at": "2026-01-02T00:00:00+00:00"}],
        "kosha_msds_current": [],
        "kosha_msds_seo_preview_current": [{
            "id": "chem-1", "chem_id": "C1", "source_key": "C1",
            "chemical_name_ko": "톨루엔",
            "snapshot_id": "ms1",
        }],
        "kosha_msds_snapshots": [{"id": "ms1", "completed_at": "2026-01-02T00:00:00+00:00"}],
        "safe_help_content": [{
            "doc_id": "h-1", "slug": "s", "title": "T",
            "body": "B", "status": "PUBLISHED",
            "updated_at": "2026-01-02T00:00:00+00:00",
        }],
        "industrial_accident_precedents": [{
            "id": "p-1", "case_name": "T", "prec_seq": "1", "source": "law_go_kr",
            "is_active": True, "collected_at": "2026-01-01T00:00:00+00:00",
        }],
        "kosha_safety_materials": [{"id": "m-1", "title": "T"}],
        "kosha_safety_material_snapshots": [{
            "id": "ms1", "completed_at": "2026-01-02T00:00:00+00:00", "status": "COMPLETED",
        }],
        "kosha_safety_material_snapshot_items": [{"snapshot_id": "ms1", "material_id": "m-1"}],
        "kosha_safety_material_details": [{
            "material_id": "m-1", "source_med_seq": 1,
            "source_updated_at": "2026-01-02T00:00:00+00:00",
        }],
        "kosha_safety_material_storage_holds": [],
        "law_article_current": [{
            "id": "art-1", "article_internal_key": "l/1", "law_name": "L",
            "article_no": "1", "article_text": "txt",
            "published_at": "2026-01-01T00:00:00+00:00",
        }],
    })
    adapters = build_production_adapters(sb)
    store = MemoryStore()
    indexer = Indexer(store)
    result = indexer.full_rebuild(adapters)
    assert result.status == "PROMOTED"
    # 7 Domains produce docs; RISK contributes zero.
    assert result.promoted_count == 7
    types = {row["object_type"] for row in store.iter_current()}
    assert types == {"GUIDE", "SAFETY_MATERIAL", "CSI_ACCIDENT", "CHEM",
                     "KNOWLEDGE", "PRECEDENT", "LEGAL"}


# ---------------------------------------------------------------------------
# Shared census tests
# ---------------------------------------------------------------------------


def test_census_counts_publication_visibility_and_uniqueness():
    """Shared run_census aggregates over any DomainAdapter."""
    adapter = GuideAdapter(fetch_current=lambda: [
        {"id": "g-1", "guide_no": "N-1", "guide_title": "T",
         "regist_date": "2026-01-01T00:00:00+00:00"},
        {"id": "g-2", "guide_no": "N-2", "guide_title": "T",
         "regist_date": "2026-01-01T00:00:00+00:00"},
        {"id": "g-2", "guide_no": "N-2", "guide_title": "T",
         "regist_date": "2026-01-01T00:00:00+00:00"},   # duplicate
    ])
    census = run_census(adapter)
    assert isinstance(census, DomainCensus)
    assert census.yielded_count == 3
    assert census.unique_canonical_ids == 2
    assert census.duplicate_canonical_ids == 1
    assert census.published == 3
    assert census.visibility_public == 3
    assert census.visibility_saas == 3
    assert census.visibility_paid == 3


def test_census_flags_missing_timestamp_as_normalization_failure():
    """A row that trips the writer's guards is captured as a failure
    count, not silently dropped."""
    # A row missing the timestamp will not produce a payload (the
    # adapter's own guard rejects it before normalize is even called).
    # But if the adapter emits a payload without source_updated_at,
    # normalize_document rejects it — that hits the census failure
    # buckets.
    class _BadAdapter:
        domain_name = "TEST"
        object_type = "TEST"

        def iter_documents(self):
            yield {
                "object_type": "TEST",
                "canonical_id": "x",
                "source_id": "S",
                "source_key": None,
                "title": "T",
                "search_text": "T",
                "publication_status": "PUBLISHED",
                "visibility_scopes": ["PUBLIC"],
                # no source_updated_at — writer rejects.
            }

        def iter_expected_hashes(self):
            return iter(())

        def object_reindex_payload(self, canonical_id):
            return None

    census = run_census(_BadAdapter())
    assert census.yielded_count == 1
    assert census.timestamp_failures == 1
    assert census.unique_canonical_ids == 0


def test_census_does_not_write_to_store():
    """READ-only: census MUST NOT touch a SearchStore."""
    from services.shared_search import MemoryStore
    store = MemoryStore()
    adapter = GuideAdapter(fetch_current=lambda: [
        {"id": "g-1", "guide_no": "N-1", "guide_title": "T",
         "regist_date": "2026-01-01T00:00:00+00:00"},
    ])
    before = list(store.iter_current())
    run_census(adapter)
    after = list(store.iter_current())
    assert after == before
    assert store.count_current() == 0


# ---------------------------------------------------------------------------
# Duplicate-implementation audit — narrowed to F2 CO §44 additions
# ---------------------------------------------------------------------------


def test_source_reader_is_the_only_paginator():
    """Every adapter that paginates must go through
    services.shared_search.source_reader.paginate_supabase. No
    manual `.range(...)` loops living inside adapter files."""
    import pathlib
    adapters_dir = pathlib.Path(__file__).resolve().parents[1] / "services" / "shared_search" / "adapters"
    for py in adapters_dir.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        # Adapters must not implement their own pagination.
        assert ".range(" not in text, (
            f"{py.name}: adapters must not call .range(); use "
            "source_reader.paginate_supabase from the production binding.")


def test_census_is_shared_module_not_reimplemented_per_adapter():
    """Census aggregation logic is defined once in
    services/shared_search/census.py. Adapters must not carry their
    own duplicate implementations."""
    import pathlib
    adapters_dir = pathlib.Path(__file__).resolve().parents[1] / "services" / "shared_search" / "adapters"
    for py in adapters_dir.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        # census-specific counter dicts / DomainCensus-shaped code
        # patterns should NOT appear in adapter files.
        for marker in ("DomainCensus", "run_census(", "expected_count ="):
            assert marker not in text, (
                f"{py.name} contains census-specific pattern {marker!r}; "
                "census belongs in services/shared_search/census.py")
