"""WO-TAI-SHARED-SEARCH-F2 — Domain adapter + Indexer + shared-infra tests.

Covers:
- per-adapter unit tests (eligible → PUBLISHED; ineligible → not surfaced;
  identity + provenance preserved; deterministic hash)
- cross-domain integration via the Common Indexer
- publication safety (HOLD / non-current / disabled state never becomes
  discoverable)
- legal / tenant / no-LLM safety inherited from F1
- shared-use / duplicate-implementation audit
- RISK DRAFT negative

All fixtures use in-memory adapters — zero Supabase, zero DB, zero
network, zero LLM.
"""
from __future__ import annotations

import datetime as _dt
import pathlib
import re

import pytest

from services.shared_search import (
    MemoryStore, Indexer, ReconcileReport,
    ChemAdapter, CsiAccidentAdapter, GuideAdapter, KnowledgeAdapter,
    LegalAdapter, PrecedentAdapter, RiskAdapter, SafetyMaterialAdapter,
)
from services.shared_search.contract import (
    PUBLICATION_STATUS_HOLD, PUBLICATION_STATUS_PUBLISHED,
)


UTC = _dt.timezone.utc


# ---------------------------------------------------------------------------
# Fixtures per Domain — real-column-name-based shapes
# ---------------------------------------------------------------------------


def _guide_row(guide_id="g-001", title="산업안전보건 관리 지침"):
    return {
        "id": guide_id,
        "title": title,
        "description": "공정별 안전관리 요령",
        "category_name": "안전관리",
        "url": "https://kosha.or.kr/g/001",
        "first_seen_at": "2026-01-01T00:00:00+00:00",
        "last_seen_at": "2026-06-01T00:00:00+00:00",
    }


def _material_row(mid="m-001", storage_hold=False):
    return {
        "id": mid,
        "title": "고소작업 안전자료",
        "summary": "추락 방지 요약",
        "category": "재해예방",
        "industry_category": "건설",
        "accident_type": "추락",
        "url": "https://kosha.or.kr/m/001",
        "source_med_seq": 12345,
        "updated_at": "2026-05-01T00:00:00+00:00",
        "storage_hold": storage_hold,
    }


def _csi_row(uuid_part="abcd", identity_status="READY"):
    return {
        "content_id": f"CSI:{uuid_part}",
        "identity_status": identity_status,
        "title": "용접 작업 중 화재 사고",
        "summary": "용접 스파크에 의한 화재 발생",
        "accident_type": "화재",
        "work_type": "용접",
        "first_seen_at": "2026-03-01T00:00:00+00:00",
    }


def _chem_row(uuid="chem-uuid-001", chem_id="C00001"):
    return {
        "id": uuid,
        "source_key": chem_id,
        "chem_id": chem_id,
        "chemical_name_ko": "톨루엔",
        "chemical_name_en": "Toluene",
        "cas_no": "108-88-3",
        "ke_no": "KE-31580",
        "en_no": "203-625-9",
        "un_no": "1294",
        "last_date": "2026-08-01T00:00:00+00:00",
    }


def _help_row(doc_id="h-001", status="PUBLISHED"):
    return {
        "doc_id": doc_id,
        "slug": "how-to-use",
        "title": "사용 가이드",
        "body_text": "본문 내용",
        "menu_group": "start",
        "status": status,
        "updated_at": "2026-04-01T00:00:00+00:00",
    }


def _precedent_row(pid="p-001", is_active=True):
    return {
        "id": pid,
        "prec_seq": "202601010001",
        "case_number": "2026다1234",
        "case_name": "산업안전보건법 위반 사건",
        "court_name": "대법원",
        "decision_date": "2026-02-01",
        "sector": "construction",
        "hazard_type": "추락",
        "summary": "판결 요지 요약",
        "source_url": "https://law.go.kr/prec/202601010001",
        "is_active": is_active,
        "collected_at": "2026-02-05T00:00:00+00:00",
    }


def _legal_row(kind, ident="leg-001", title="산업안전보건법 시행규칙 제1조"):
    row = {
        "record_kind": kind,
        "title": title,
        "summary": "요지",
        "body": "본문",
        "subject_key": "산업안전보건법 시행규칙",
        "source_id": "LEG_OFFICIAL",
        "source_key": ident,
        "published_at": "2026-01-01T00:00:00+00:00",
    }
    if kind == "obligation_atom":
        row["obligation_atom_id"] = ident
    elif kind == "law_article":
        row["article_id"] = ident
    return row


# ---------------------------------------------------------------------------
# Per-adapter unit tests
# ---------------------------------------------------------------------------


def test_guide_adapter_yields_published_document():
    adapter = GuideAdapter(
        fetch_current=lambda: [_guide_row()],
        fetch_by_id=lambda _id: _guide_row(guide_id=_id),
    )
    docs = list(adapter.iter_documents())
    assert len(docs) == 1
    d = docs[0]
    assert d["object_type"] == "GUIDE"
    assert d["canonical_id"] == "g-001"
    assert d["source_id"] == "KOSHA_OFFICIAL_GUIDE"
    assert d["source_key"] == "g-001"
    assert d["publication_status"] == "PUBLISHED"
    assert "PUBLIC" in d["visibility_scopes"]


def test_guide_adapter_missing_title_rejected():
    adapter = GuideAdapter(fetch_current=lambda: [
        {"id": "g-1"}   # no title
    ])
    assert list(adapter.iter_documents()) == []


def test_material_adapter_storage_hold_becomes_hold():
    adapter = SafetyMaterialAdapter(
        fetch_current=lambda: [_material_row(storage_hold=True)],
    )
    docs = list(adapter.iter_documents())
    assert len(docs) == 1
    d = docs[0]
    assert d["publication_status"] == "HOLD"
    assert d["visibility_scopes"] == []


def test_material_adapter_source_key_uses_source_med_seq():
    adapter = SafetyMaterialAdapter(
        fetch_current=lambda: [_material_row()],
    )
    d = list(adapter.iter_documents())[0]
    assert d["source_key"] == "12345"


def test_csi_adapter_uses_content_id_and_null_source_key():
    adapter = CsiAccidentAdapter(
        fetch_current=lambda: [_csi_row()],
    )
    d = list(adapter.iter_documents())[0]
    assert d["canonical_id"] == "CSI:abcd"
    assert d["source_id"] == "CSI"
    assert d["source_key"] is None
    assert d["public_url"] == "/public/accidents/csi/abcd"


def test_csi_adapter_non_ready_rejected():
    adapter = CsiAccidentAdapter(
        fetch_current=lambda: [_csi_row(identity_status="HOLD")],
    )
    assert list(adapter.iter_documents()) == []


def test_chem_adapter_public_gated_by_env(monkeypatch):
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "off")
    adapter = ChemAdapter(fetch_current=lambda: [_chem_row()])
    d = list(adapter.iter_documents())[0]
    assert "PUBLIC" not in d["visibility_scopes"]
    assert d["public_url"] is None
    assert d["saas_url"].startswith("/saas/chemical/")


def test_chem_adapter_public_visible_when_env_seo_preview(monkeypatch):
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    adapter = ChemAdapter(fetch_current=lambda: [_chem_row()])
    d = list(adapter.iter_documents())[0]
    assert "PUBLIC" in d["visibility_scopes"]
    assert d["public_url"].startswith("/public/kosha/msds/")


def test_chem_adapter_never_asserts_chem_term(monkeypatch):
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    adapter = ChemAdapter(fetch_current=lambda: [_chem_row()])
    d = list(adapter.iter_documents())[0]
    # WO §17 / F2 §19: CHEM_TERM subject is NOT auto-assigned.
    assert d["subjects"] == []
    # But the chemical context tuple IS set (adapter policy).
    assert any(c["context_type"] == "chemical" for c in d["context"])


def test_knowledge_adapter_only_published_rows_yield():
    adapter = KnowledgeAdapter(fetch_current=lambda: [
        _help_row(doc_id="h-1", status="DRAFT"),
        _help_row(doc_id="h-2", status="PUBLISHED"),
    ])
    docs = list(adapter.iter_documents())
    assert len(docs) == 1
    assert docs[0]["canonical_id"] == "h-2"


def test_precedent_adapter_is_active_false_rejected():
    adapter = PrecedentAdapter(fetch_current=lambda: [
        _precedent_row(pid="p-1", is_active=True),
        _precedent_row(pid="p-2", is_active=False),
    ])
    docs = list(adapter.iter_documents())
    assert [d["canonical_id"] for d in docs] == ["p-1"]


def test_precedent_adapter_provenance_preserved():
    adapter = PrecedentAdapter(fetch_current=lambda: [_precedent_row()])
    d = list(adapter.iter_documents())[0]
    assert d["source_id"] == "law_go_kr"
    assert d["source_key"] == "202601010001"


def test_precedent_adapter_detail_resolver_deferred():
    adapter = PrecedentAdapter(fetch_current=lambda: [_precedent_row()])
    d = list(adapter.iter_documents())[0]
    # F2 WO §22: detail resolver DEFERRED — do NOT reuse the legacy
    # /precedents/{id} posts route.
    assert d["public_url"] is None
    assert d["saas_url"] is None


def test_legal_adapter_supported_subtypes_pass():
    adapter = LegalAdapter(fetch_current=lambda: [
        _legal_row("obligation_atom", ident="obl-1"),
        _legal_row("law_article", ident="art-1"),
    ])
    docs = list(adapter.iter_documents())
    assert {d["canonical_id"] for d in docs} == {"obl-1", "art-1"}
    # Obligation atoms carry a legal_obligation context tuple.
    obl = next(d for d in docs if d["canonical_id"] == "obl-1")
    assert any(c["context_type"] == "legal_obligation" for c in obl["context"])


def test_legal_adapter_blocks_unsupported_subtype():
    from services.shared_search import AdapterBlockedSubtype
    adapter = LegalAdapter(fetch_current=lambda: [
        _legal_row("obligation_atom", ident="obl-1"),
        _legal_row("norm_cluster", ident="nc-1"),
    ])
    it = adapter.iter_documents()
    yielded = []
    with pytest.raises(AdapterBlockedSubtype, match="norm_cluster"):
        for d in it:
            yielded.append(d)
    # We still got the obligation_atom before the block was raised.
    assert [d["canonical_id"] for d in yielded] == ["obl-1"]


def test_risk_adapter_yields_nothing_by_default():
    adapter = RiskAdapter()
    assert list(adapter.iter_documents()) == []


def test_risk_adapter_stays_empty_even_when_fetcher_returns_draft_rows():
    """Even if a future misconfigured fetcher yields DRAFT rows, the
    adapter must not translate them into SearchDocuments."""
    adapter = RiskAdapter(fetch_active=lambda: [
        {"id": "r-1", "canonical_code": "R1", "status": "DRAFT"},
    ])
    assert list(adapter.iter_documents()) == []


# ---------------------------------------------------------------------------
# Adapter → Writer identity + hash determinism (round-trip through F1)
# ---------------------------------------------------------------------------


def test_guide_adapter_hash_deterministic_across_two_runs():
    a = GuideAdapter(fetch_current=lambda: [_guide_row()])
    b = GuideAdapter(fetch_current=lambda: [_guide_row()])
    ha = list(a.iter_expected_hashes())
    hb = list(b.iter_expected_hashes())
    assert ha == hb
    assert ha[0]["canonical_id"] == "g-001"


# ---------------------------------------------------------------------------
# Cross-domain integration via the Common Indexer
# ---------------------------------------------------------------------------


def _all_adapters(monkeypatch):
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")
    return [
        GuideAdapter(fetch_current=lambda: [_guide_row()]),
        SafetyMaterialAdapter(fetch_current=lambda: [_material_row()]),
        CsiAccidentAdapter(fetch_current=lambda: [_csi_row()]),
        ChemAdapter(fetch_current=lambda: [_chem_row()]),
        KnowledgeAdapter(fetch_current=lambda: [_help_row()]),
        PrecedentAdapter(fetch_current=lambda: [_precedent_row()]),
        LegalAdapter(fetch_current=lambda: [
            _legal_row("obligation_atom", ident="obl-1"),
        ]),
    ]


def test_full_rebuild_seven_domains_coexist(monkeypatch):
    store = MemoryStore()
    indexer = Indexer(store)
    result = indexer.full_rebuild(_all_adapters(monkeypatch))
    assert result.status == "PROMOTED"
    assert result.promoted_count == 7
    # Every object_type present.
    types = {row["object_type"] for row in store.iter_current()}
    assert types == {"GUIDE", "SAFETY_MATERIAL", "CSI_ACCIDENT", "CHEM",
                     "KNOWLEDGE", "PRECEDENT", "LEGAL"}


def test_full_rebuild_material_on_storage_hold_not_current(monkeypatch):
    store = MemoryStore()
    indexer = Indexer(store)
    adapters = [
        SafetyMaterialAdapter(fetch_current=lambda: [
            _material_row(mid="m-1", storage_hold=True),
            _material_row(mid="m-2", storage_hold=False),
        ]),
    ]
    result = indexer.full_rebuild(adapters)
    # Both staged; only the PUBLISHED one becomes current.
    assert result.promoted_count == 1
    assert store.get_current("SAFETY_MATERIAL", "m-1") is None
    assert store.get_current("SAFETY_MATERIAL", "m-2") is not None


def test_full_rebuild_legal_blocked_subtype_records_but_does_not_fail(monkeypatch):
    store = MemoryStore()
    indexer = Indexer(store)
    adapters = [
        LegalAdapter(fetch_current=lambda: [
            _legal_row("obligation_atom", ident="obl-1"),
            _legal_row("norm_cluster", ident="nc-1"),
        ]),
    ]
    result = indexer.full_rebuild(adapters)
    assert result.status == "PROMOTED"
    assert result.promoted_count == 1     # obligation_atom only
    assert any("LEGAL" == b["domain"] for b in result.blocked_subtypes)


def test_full_rebuild_risk_yields_zero_docs(monkeypatch):
    """WO §24: RISK adapter yields zero SearchDocuments until RISK-C02
    opens the ACTIVE gate. A rebuild that ONLY has RISK adapters
    correctly aborts (nothing to promote); the interesting case is
    running RISK alongside a real adapter — the real one succeeds and
    RISK contributes zero to current."""
    from services.shared_search import RebuildAborted
    store = MemoryStore()
    indexer = Indexer(store)

    # RISK-only rebuild aborts because there is nothing to promote.
    with pytest.raises(RebuildAborted, match="no staged documents"):
        indexer.full_rebuild([RiskAdapter()])

    result2 = indexer.full_rebuild([
        GuideAdapter(fetch_current=lambda: [_guide_row()]),
        RiskAdapter(),
    ])
    assert result2.status == "PROMOTED"
    assert result2.promoted_count == 1   # GUIDE only
    # Zero RISK documents in current.
    assert list(store.iter_current(object_type="RISK")) == []


def test_object_reindex_via_indexer(monkeypatch):
    store = MemoryStore()
    indexer = Indexer(store)
    # Seed
    indexer.full_rebuild(_all_adapters(monkeypatch))
    # Update GUIDE title via object reindex
    adapter = GuideAdapter(
        fetch_current=lambda: [_guide_row()],
        fetch_by_id=lambda _id: _guide_row(guide_id="g-001", title="새 제목"),
    )
    assert indexer.object_reindex(adapter, "g-001") is True
    row = store.get_current("GUIDE", "g-001")
    assert row["title"] == "새 제목"


def test_reconcile_via_indexer(monkeypatch):
    store = MemoryStore()
    indexer = Indexer(store)
    indexer.full_rebuild(_all_adapters(monkeypatch))
    adapter = GuideAdapter(fetch_current=lambda: [_guide_row()])
    report = indexer.reconcile_domain(adapter)
    assert isinstance(report, ReconcileReport)
    assert report.ok is True
    assert report.match == 1


def test_dry_run_census(monkeypatch):
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "off")
    adapter = ChemAdapter(fetch_current=lambda: [
        _chem_row(uuid="u-1", chem_id="C1"),
        _chem_row(uuid="u-2", chem_id="C2"),
    ])
    store = MemoryStore()
    indexer = Indexer(store)
    census = indexer.dry_run(adapter)
    assert census.total_yielded == 2
    assert census.unique_canonical_ids == 2
    assert census.duplicate_canonical_ids == 0
    assert census.visibility_public == 0    # PUBLIC_MODE=off → PUBLIC withheld
    assert census.visibility_saas == 2
    assert census.hash_collisions == 0
    assert census.normalization_failures == 0


# ---------------------------------------------------------------------------
# Cross-Domain identity collision audit (WO §28)
# ---------------------------------------------------------------------------


def test_same_canonical_id_different_object_type_allowed(monkeypatch):
    """(GUIDE, x) and (CHEM, x) may coexist — object_type disambiguates."""
    store = MemoryStore()
    indexer = Indexer(store)
    guide_row = _guide_row(guide_id="shared-id")
    chem_row = _chem_row(uuid="shared-id", chem_id="C_shared")
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "off")
    indexer.full_rebuild([
        GuideAdapter(fetch_current=lambda: [guide_row]),
        ChemAdapter(fetch_current=lambda: [chem_row]),
    ])
    assert store.count_current() == 2
    assert store.get_current("GUIDE", "shared-id") is not None
    assert store.get_current("CHEM", "shared-id") is not None


def test_duplicate_within_domain_is_upserted_not_duplicated(monkeypatch):
    """Two rows with the same (object_type, canonical_id) collapse to one."""
    store = MemoryStore()
    indexer = Indexer(store)
    row1 = _guide_row(guide_id="dup", title="v1")
    row2 = _guide_row(guide_id="dup", title="v2")
    indexer.full_rebuild([
        GuideAdapter(fetch_current=lambda: [row1, row2]),
    ])
    assert store.count_current(object_type="GUIDE") == 1
    # Whichever staged last wins in the atomic swap.
    assert store.get_current("GUIDE", "dup")["title"] == "v2"


# ---------------------------------------------------------------------------
# Shared-use / duplicate-implementation audit (WO §29)
# ---------------------------------------------------------------------------


def test_no_duplicate_common_implementations():
    """The Foundation rule from the F2 WO: any capability used by
    2+ adapters lives in ONE shared module. This audit checks the
    common suspects by counting hits in the adapters directory.
    """
    adapters_dir = pathlib.Path(__file__).resolve().parents[1] / "services" / "shared_search" / "adapters"
    files = list(adapters_dir.glob("*.py"))

    duplicate_patterns = {
        # Each of these must be defined ONCE across adapters/
        # and IMPORTED wherever needed.
        "def _canonical_str_list":       0,  # lives in document.py — never here
        "def _canonical_subjects":       0,
        "def _canonical_context":        0,
        "def compute_content_hash":      0,
        "def sha256":                    0,
        "supabase.table(":               0,  # adapters must not talk to Supabase
        "search_documents.upsert":       0,
        "search_rebuild_runs.insert":    0,
        "promote_search_rebuild":        0,
    }

    for f in files:
        text = f.read_text(encoding="utf-8")
        for pattern in duplicate_patterns:
            duplicate_patterns[pattern] += text.count(pattern)

    for pattern, count in duplicate_patterns.items():
        assert count == 0, (
            f"Pattern {pattern!r} appears {count} time(s) in adapters/; "
            "must live in a shared module (writer, hash_utils, or store) "
            "and be imported.")


def test_expected_hashes_uses_shared_helper():
    """Every adapter's `iter_expected_hashes` must delegate to the
    shared `expected_hashes_from_documents` helper — no re-implementation
    per Domain."""
    adapters_dir = pathlib.Path(__file__).resolve().parents[1] / "services" / "shared_search" / "adapters"
    domain_files = [
        adapters_dir / n for n in (
            "guide.py", "safety_material.py", "csi_accident.py",
            "chem.py", "knowledge.py", "precedent.py",
            "legal.py", "risk.py",
        )
    ]
    for f in domain_files:
        text = f.read_text(encoding="utf-8")
        assert "expected_hashes_from_documents" in text, (
            f"{f.name} must import + use expected_hashes_from_documents "
            "from adapters._common — no per-Domain reimplementation.")


# ---------------------------------------------------------------------------
# No LLM audit (extends F1 §53)
# ---------------------------------------------------------------------------


def test_no_llm_dependency_in_f2_layer():
    root = pathlib.Path(__file__).resolve().parents[1] / "services" / "shared_search"
    banned = re.compile(r"^\s*(?:import|from)\s+"
                        r"(openai|anthropic|langchain|llama_index|sentence_transformers)\b",
                        re.MULTILINE)
    for py in root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert not banned.search(text), f"LLM SDK import in {py}"


# ---------------------------------------------------------------------------
# End-to-end sanity: rebuild → object reindex → reconcile all clean
# ---------------------------------------------------------------------------


def test_e2e_rebuild_reindex_reconcile(monkeypatch):
    store = MemoryStore()
    indexer = Indexer(store)
    monkeypatch.setenv("KOSHA_MSDS_PUBLIC_MODE", "seo_preview")

    # First rebuild — all 7 Domains + RISK.
    all_adapters = _all_adapters(monkeypatch) + [RiskAdapter()]
    result = indexer.full_rebuild(all_adapters)
    assert result.status == "PROMOTED"
    assert store.count_current() == 7   # RISK contributes 0

    # OBJECT REINDEX on KNOWLEDGE — status change to DRAFT should tombstone.
    kn_adapter = KnowledgeAdapter(
        fetch_current=lambda: [],
        fetch_by_id=lambda _id: _help_row(doc_id=_id, status="DRAFT"),
    )
    result_reindex = indexer.object_reindex(kn_adapter, "h-001")
    # DRAFT → normalize returns None → tombstone
    assert result_reindex is None or result_reindex is False
    assert store.get_current("KNOWLEDGE", "h-001") is None

    # RECONCILE — GUIDE should still be OK.
    guide_adapter = GuideAdapter(fetch_current=lambda: [_guide_row()])
    report = indexer.reconcile_domain(guide_adapter)
    assert report.ok is True
