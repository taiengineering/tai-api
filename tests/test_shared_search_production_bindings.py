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
        "law_master": [],
        "law_article": [],
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
    """F2 FINAL §1: storage_holds real column is `status`
    (OPEN / RESOLVED). No `resolved` boolean."""
    sb = FakeSupabase(tables={
        "kosha_safety_materials": [
            {"id": "m-1", "title": "Material 1",
             "url": "https://example/m1",
             "category": "cat", "industry_category": "건설",
             "accident_type": "추락", "product_type": "video"},
            {"id": "m-2", "title": "Material 2",
             "url": "https://example/m2"},
            {"id": "m-3", "title": "Material 3",
             "url": "https://example/m3"},
        ],
        "kosha_safety_material_snapshots": [
            {"id": "snap-mat-1", "completed_at": "2026-06-01T00:00:00+00:00",
             "status": "COMPLETED"},
        ],
        "kosha_safety_material_snapshot_items": [
            {"snapshot_id": "snap-mat-1", "material_id": "m-1"},
            {"snapshot_id": "snap-mat-1", "material_id": "m-2"},
            {"snapshot_id": "snap-mat-1", "material_id": "m-3"},
        ],
        "kosha_safety_material_details": [
            {"material_id": "m-1", "source_med_seq": 1001,
             "source_title": "Detail 1", "source_description": "desc",
             "source_published_at": "2026-05-01T00:00:00+00:00",
             "source_updated_at": "2026-05-10T00:00:00+00:00"},
            {"material_id": "m-2", "source_med_seq": 1002,
             "source_updated_at": "2026-05-10T00:00:00+00:00"},
            {"material_id": "m-3", "source_med_seq": 1003,
             "source_updated_at": "2026-05-10T00:00:00+00:00"},
        ],
        "kosha_safety_material_storage_holds": [
            # m-2 has an OPEN hold → HOLD.
            {"material_id": "m-2", "status": "OPEN"},
            # m-3 had a hold that was RESOLVED → PUBLISHED (no longer held).
            {"material_id": "m-3", "status": "RESOLVED",
             "resolved_at": "2026-05-15T00:00:00+00:00"},
        ],
    })
    adapters = build_production_adapters(sb)
    mat_adapter = next(a for a in adapters if a.domain_name == "SAFETY_MATERIAL")
    docs = list(mat_adapter.iter_documents())
    by_id = {d["canonical_id"]: d for d in docs}
    assert by_id["m-1"]["publication_status"] == "PUBLISHED"
    assert by_id["m-1"]["source_key"] == "1001"
    assert by_id["m-2"]["publication_status"] == "HOLD"
    assert by_id["m-2"]["visibility_scopes"] == []
    assert by_id["m-3"]["publication_status"] == "PUBLISHED"


def test_material_binding_uses_real_status_column_not_resolved_boolean():
    """Regression guard for the F2 FINAL §1 blocker: the production
    binding MUST NOT reference a `resolved` column on
    kosha_safety_material_storage_holds."""
    import pathlib
    bindings = (pathlib.Path(__file__).resolve().parents[1]
                / "services" / "shared_search" / "production_bindings.py")
    text = bindings.read_text(encoding="utf-8")
    # The phantom column must not appear anywhere in the source.
    assert "material_id,resolved" not in text
    assert '"resolved"' not in text
    # And the real column MUST appear.
    assert "material_id,status" in text


def test_legal_binding_reads_law_master_version_article_directly():
    """F2 FINAL §3-§10: LEGAL binding assembles current-eligible
    articles from law_master + law_version + law_article — the
    `law_article_current` view does NOT exist in production. The
    canonical_id MUST be `law_article.id` (not article_internal_key).
    """
    sb = FakeSupabase(tables={
        "law_master": [
            {"id": "lm-1", "law_name": "산업안전보건법",
             "is_active": True, "current_version_id": "lv-1a"},
            # inactive law — must be excluded.
            {"id": "lm-inactive", "law_name": "구법",
             "is_active": False, "current_version_id": "lv-old"},
            # active law with a different current version.
            {"id": "lm-2", "law_name": "산업안전보건법 시행규칙",
             "is_active": True, "current_version_id": "lv-2c"},
        ],
        "law_article": [
            # PUBLISHED (belongs to current version + not deleted).
            {"id": "art-A", "law_id": "lm-1", "law_version_id": "lv-1a",
             "article_no": "1", "article_title": "목적",
             "article_text": "이 법은…",
             "is_deleted_in_version": False,
             "enforcement_date": "2026-01-01T00:00:00+00:00"},
            {"id": "art-B", "law_id": "lm-1", "law_version_id": "lv-1a",
             "article_no": "2", "article_title": "정의",
             "article_text": "이 법에서 …",
             "is_deleted_in_version": False,
             "enforcement_date": "2026-01-01T00:00:00+00:00"},
            {"id": "art-C", "law_id": "lm-2", "law_version_id": "lv-2c",
             "article_no": "1",
             "article_text": "시행규칙 §1 …",
             "is_deleted_in_version": False,
             "enforcement_date": "2026-01-01T00:00:00+00:00"},
            # Same article_internal_key as art-A but on the CURRENT
            # version — proves canonical_id ≠ article_internal_key
            # (F2 FINAL §6/§7). Both must survive as distinct rows.
            {"id": "art-A-companion", "law_id": "lm-1", "law_version_id": "lv-1a",
             "article_internal_key": "law-1/art-1",  # collides
             "article_no": "3", "article_title": "적용대상",
             "article_text": "…",
             "is_deleted_in_version": False,
             "enforcement_date": "2026-01-01T00:00:00+00:00"},
            # Belongs to an OLD version — excluded.
            {"id": "art-old", "law_id": "lm-1", "law_version_id": "lv-1-OLD",
             "article_no": "1", "article_text": "예전",
             "is_deleted_in_version": False,
             "enforcement_date": "2025-01-01T00:00:00+00:00"},
            # Current version but deleted in it — excluded.
            {"id": "art-deleted", "law_id": "lm-1", "law_version_id": "lv-1a",
             "article_no": "99", "article_text": "삭제됨",
             "is_deleted_in_version": True,
             "enforcement_date": "2026-01-01T00:00:00+00:00"},
            # Belongs to an INACTIVE master — excluded.
            {"id": "art-inactive", "law_id": "lm-inactive",
             "law_version_id": "lv-old",
             "article_no": "1", "article_text": "폐지",
             "is_deleted_in_version": False,
             "enforcement_date": "2024-01-01T00:00:00+00:00"},
        ],
    })
    adapters = build_production_adapters(sb)
    legal_adapter = next(a for a in adapters if a.domain_name == "LEGAL")
    docs = list(legal_adapter.iter_documents())
    canonical_ids = [d["canonical_id"] for d in docs]
    assert set(canonical_ids) == {"art-A", "art-B", "art-C", "art-A-companion"}
    # Canonical uniqueness across the run.
    assert len(canonical_ids) == len(set(canonical_ids))
    # law_name projected onto each row.
    d_a = next(d for d in docs if d["canonical_id"] == "art-A")
    assert "산업안전보건법" in d_a["title"]
    assert "제1조" in d_a["title"]
    # article_internal_key collision does NOT collapse the two rows —
    # they carry distinct canonical_id (law_article.id).
    d_companion = next(d for d in docs
                       if d["canonical_id"] == "art-A-companion")
    assert d_companion["title"] != d_a["title"]


def test_legal_binding_by_id_respects_current_version_gate():
    sb = FakeSupabase(tables={
        "law_master": [
            {"id": "lm-1", "law_name": "L", "is_active": True,
             "current_version_id": "lv-current"},
        ],
        "law_article": [
            {"id": "current", "law_id": "lm-1", "law_version_id": "lv-current",
             "article_no": "1", "article_text": "current",
             "is_deleted_in_version": False,
             "enforcement_date": "2026-01-01T00:00:00+00:00"},
            {"id": "old", "law_id": "lm-1", "law_version_id": "lv-OLD",
             "article_no": "1", "article_text": "old",
             "is_deleted_in_version": False,
             "enforcement_date": "2025-01-01T00:00:00+00:00"},
            {"id": "deleted", "law_id": "lm-1", "law_version_id": "lv-current",
             "article_no": "9", "article_text": "gone",
             "is_deleted_in_version": True,
             "enforcement_date": "2026-01-01T00:00:00+00:00"},
        ],
    })
    adapters = build_production_adapters(sb)
    legal_adapter = next(a for a in adapters if a.domain_name == "LEGAL")
    # Current row → payload.
    assert legal_adapter.object_reindex_payload("current") is not None
    # Old version → None (should be tombstoned by indexer).
    assert legal_adapter.object_reindex_payload("old") is None
    # Current version but deleted → None.
    assert legal_adapter.object_reindex_payload("deleted") is None


def test_no_law_article_current_view_referenced():
    """Regression guard for F2 FINAL §3: no production code path may
    call `.table("law_article_current")`. Comments / docstrings that
    document why we DON'T use it are allowed."""
    import pathlib
    import re
    banned = re.compile(r'''\.table\(\s*["']law_article_current["']\s*\)''')
    root = pathlib.Path(__file__).resolve().parents[1] / "services" / "shared_search"
    for py in root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert not banned.search(text), (
            f"{py}: calls .table('law_article_current') which does not "
            "exist in production; use law_master + law_article directly.")


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
        "law_master": [{
            "id": "lm-1", "law_name": "L", "is_active": True,
            "current_version_id": "lv-1",
        }],
        "law_article": [{
            "id": "art-1", "law_id": "lm-1", "law_version_id": "lv-1",
            "article_no": "1", "article_text": "txt",
            "is_deleted_in_version": False,
            "enforcement_date": "2026-01-01T00:00:00+00:00",
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


# ---------------------------------------------------------------------------
# WO-TAI-SHARED-SEARCH-F2-FINAL-PATCH-OBJECT-REINDEX-001
# SAFETY_MATERIAL object_reindex regression tests
# ---------------------------------------------------------------------------


def _make_mat_supabase(
    *,
    snapshot_rows: list,
    snapshot_items: list,
    catalog_rows: list,
    detail_rows: list,
    hold_rows: list,
) -> "FakeSupabase":
    """Convenience builder for SAFETY_MATERIAL object_reindex tests."""
    return FakeSupabase(tables={
        "kosha_safety_materials": catalog_rows,
        "kosha_safety_material_snapshots": snapshot_rows,
        "kosha_safety_material_snapshot_items": snapshot_items,
        "kosha_safety_material_details": detail_rows,
        "kosha_safety_material_storage_holds": hold_rows,
    })


def _mat_adapter(sb: "FakeSupabase"):
    return next(
        a for a in build_production_adapters(sb)
        if a.domain_name == "SAFETY_MATERIAL"
    )


# T1 — no latest snapshot membership → object_reindex_payload = None
def test_material_object_reindex_no_membership_returns_none():
    """T1: material exists in catalog + an older snapshot but NOT in the
    latest COMPLETED snapshot → object_reindex_payload must return None.

    Without the snapshot gate the old _by_id would happily return a
    payload for a material the current Domain set no longer contains,
    re-publishing a removed item.
    """
    sb = _make_mat_supabase(
        snapshot_rows=[
            # old snapshot — completed
            {"id": "snap-old", "completed_at": "2026-05-01T00:00:00+00:00",
             "status": "COMPLETED"},
            # latest snapshot — m-stale is NOT a member
            {"id": "snap-latest", "completed_at": "2026-09-01T00:00:00+00:00",
             "status": "COMPLETED"},
        ],
        snapshot_items=[
            # m-stale was in the old snapshot only
            {"snapshot_id": "snap-old", "material_id": "m-stale"},
        ],
        catalog_rows=[
            {"id": "m-stale", "title": "Stale Material",
             "url": "https://example/stale"},
        ],
        detail_rows=[
            {"material_id": "m-stale", "source_med_seq": 9999,
             "source_updated_at": "2026-05-01T00:00:00+00:00"},
        ],
        hold_rows=[],
    )
    adapter = _mat_adapter(sb)
    assert adapter.object_reindex_payload("m-stale") is None, (
        "Material absent from latest COMPLETED snapshot must return None "
        "from object_reindex_payload — snapshot membership gate missing"
    )


# T2 — latest member + OPEN hold → publication_status = HOLD
def test_material_object_reindex_latest_member_open_hold_is_hold():
    """T2: material IS in the latest COMPLETED snapshot but has an
    OPEN hold → publication_status must be HOLD (not PUBLISHED).
    """
    sb = _make_mat_supabase(
        snapshot_rows=[
            {"id": "snap-1", "completed_at": "2026-09-01T00:00:00+00:00",
             "status": "COMPLETED"},
        ],
        snapshot_items=[
            {"snapshot_id": "snap-1", "material_id": "m-held"},
        ],
        catalog_rows=[
            {"id": "m-held", "title": "Held Material",
             "url": "https://example/held"},
        ],
        detail_rows=[
            {"material_id": "m-held", "source_med_seq": 42,
             "source_updated_at": "2026-08-01T00:00:00+00:00"},
        ],
        hold_rows=[
            {"material_id": "m-held", "status": "OPEN"},
        ],
    )
    adapter = _mat_adapter(sb)
    payload = adapter.object_reindex_payload("m-held")
    assert payload is not None, "Should return a payload (member of latest snapshot)"
    assert payload["publication_status"] == "HOLD", (
        f"Expected HOLD, got {payload['publication_status']!r}"
    )


# T3 — multiple holds: RESOLVED + OPEN → HOLD (fail-closed, row-order independent)
def test_material_object_reindex_multiple_holds_any_open_is_hold():
    """T3: material has two hold rows — one RESOLVED, one OPEN.
    The old _fetch_one implementation could return the RESOLVED row
    depending on DB ordering, incorrectly marking the material PUBLISHED.
    The fix reads ALL hold rows and ANYs the condition.
    """
    for hold_order in [
        [{"material_id": "m-multi", "status": "RESOLVED"},
         {"material_id": "m-multi", "status": "OPEN"}],
        [{"material_id": "m-multi", "status": "OPEN"},
         {"material_id": "m-multi", "status": "RESOLVED"}],
    ]:
        sb = _make_mat_supabase(
            snapshot_rows=[
                {"id": "snap-1", "completed_at": "2026-09-01T00:00:00+00:00",
                 "status": "COMPLETED"},
            ],
            snapshot_items=[
                {"snapshot_id": "snap-1", "material_id": "m-multi"},
            ],
            catalog_rows=[
                {"id": "m-multi", "title": "Multi-hold Material",
                 "url": "https://example/multi"},
            ],
            detail_rows=[
                {"material_id": "m-multi", "source_med_seq": 7,
                 "source_updated_at": "2026-09-01T00:00:00+00:00"},
            ],
            hold_rows=hold_order,
        )
        adapter = _mat_adapter(sb)
        payload = adapter.object_reindex_payload("m-multi")
        assert payload is not None
        assert payload["publication_status"] == "HOLD", (
            f"RESOLVED+OPEN must still be HOLD regardless of row order; "
            f"hold_rows={hold_order!r}, got {payload['publication_status']!r}"
        )


# T4 — latest member + all holds resolved → PUBLISHED
def test_material_object_reindex_latest_member_all_resolved_is_published():
    """T4: material IS in the latest COMPLETED snapshot and ALL holds
    are RESOLVED → publication_status must be PUBLISHED.
    """
    sb = _make_mat_supabase(
        snapshot_rows=[
            {"id": "snap-1", "completed_at": "2026-09-01T00:00:00+00:00",
             "status": "COMPLETED"},
        ],
        snapshot_items=[
            {"snapshot_id": "snap-1", "material_id": "m-ok"},
        ],
        catalog_rows=[
            {"id": "m-ok", "title": "Clean Material",
             "url": "https://example/ok"},
        ],
        detail_rows=[
            {"material_id": "m-ok", "source_med_seq": 100,
             "source_updated_at": "2026-09-01T00:00:00+00:00"},
        ],
        hold_rows=[
            {"material_id": "m-ok", "status": "RESOLVED",
             "resolved_at": "2026-08-20T00:00:00+00:00"},
            {"material_id": "m-ok", "status": "RESOLVED",
             "resolved_at": "2026-07-10T00:00:00+00:00"},
        ],
    )
    adapter = _mat_adapter(sb)
    payload = adapter.object_reindex_payload("m-ok")
    assert payload is not None
    assert payload["publication_status"] == "PUBLISHED", (
        f"All-RESOLVED holds must yield PUBLISHED; got {payload['publication_status']!r}"
    )


# T5 — catalog gate: latest snapshot member but catalog row absent → None
def test_material_object_reindex_missing_catalog_returns_none():
    """T5 (catalog gate): material is in the latest COMPLETED snapshot
    but has no row in kosha_safety_materials → object_reindex_payload
    must return None.

    F2 publication contract requires catalog + snapshot (§72).
    """
    sb = _make_mat_supabase(
        snapshot_rows=[
            {"id": "snap-1", "completed_at": "2026-09-01T00:00:00+00:00",
             "status": "COMPLETED"},
        ],
        snapshot_items=[
            {"snapshot_id": "snap-1", "material_id": "m-nocatalog"},
        ],
        catalog_rows=[],   # intentionally absent
        detail_rows=[],
        hold_rows=[],
    )
    adapter = _mat_adapter(sb)
    assert adapter.object_reindex_payload("m-nocatalog") is None, (
        "Snapshot member without catalog row must return None — "
        "F2 publication requires catalog + snapshot"
    )
