"""WO-TAI-SHARED-SEARCH-F1 — Shared Search Foundation tests.

Covers the six required test surfaces from the WO:
- identity (§44)
- contract validation (§45)
- hash determinism (§46)
- full rebuild (§47)
- object reindex (§48)
- reconcile (§49)

Plus the four safety audits (§50 RISK / §51 legal / §52 tenant / §53 no LLM).
Plus an end-to-end integration chain (§54).

Every test is pure-Python + MemoryStore. Zero DB / zero deploy /
zero env change.
"""
from __future__ import annotations

import datetime as _dt
import importlib
import pathlib
import re
from typing import Any

import pytest

from services.shared_search import (
    MemoryStore, Writer, WriterRejected,
    RebuildFramework, RebuildAborted,
    SearchContractError,
    reconcile,
    content_hash,
    normalize_document,
    PUBLICATION_STATUS_PUBLISHED,
    PUBLICATION_STATUS_HOLD,
    PUBLICATION_STATUS_REMOVED,
    VISIBILITY_PUBLIC, VISIBILITY_SAAS, VISIBILITY_PAID,
    RUN_STATUS_RUNNING, RUN_STATUS_VALIDATED,
    RUN_STATUS_PROMOTED, RUN_STATUS_FAILED,
)


UTC = _dt.timezone.utc
NOW = _dt.datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


def _payload(
    *,
    object_type="GUIDE",
    canonical_id="guide-0001",
    source_id="KOSHA_OFFICIAL_GUIDE",
    source_key="guide-0001",
    title="산업안전보건 관리 지침",
    summary="공정별 관리 요령",
    search_text="산업안전보건 관리 지침 공정별 관리 요령",
    aliases=None,
    keywords=None,
    subjects=None,
    context=None,
    public_url="https://kosha.or.kr/g/0001",
    saas_url="/saas/guide/guide-0001",
    publication_status=PUBLICATION_STATUS_PUBLISHED,
    visibility_scopes=None,
    source_updated_at=NOW,
    extra: dict[str, Any] | None = None,
):
    p = {
        "object_type": object_type,
        "canonical_id": canonical_id,
        "source_id": source_id,
        "source_key": source_key,
        "title": title,
        "summary": summary,
        "search_text": search_text,
        "aliases": list(aliases or []),
        "keywords": list(keywords or []),
        "subjects": list(subjects or []),
        "context": list(context or []),
        "public_url": public_url,
        "saas_url": saas_url,
        "publication_status": publication_status,
        "visibility_scopes": list(visibility_scopes or [VISIBILITY_PUBLIC, VISIBILITY_SAAS, VISIBILITY_PAID]),
        "source_updated_at": source_updated_at,
    }
    if extra:
        p.update(extra)
    return p


# ---------------------------------------------------------------------------
# §44 IDENTITY
# ---------------------------------------------------------------------------


def test_identity_one_current_row_per_pair():
    store = MemoryStore()
    w = Writer(store)
    w.upsert_current(_payload())
    w.upsert_current(_payload())        # same pair, upsert again
    assert store.count_current() == 1


def test_identity_same_canonical_id_different_object_type_ok():
    store = MemoryStore()
    w = Writer(store)
    w.upsert_current(_payload(object_type="GUIDE", canonical_id="c-1"))
    w.upsert_current(_payload(object_type="CHEM", canonical_id="c-1",
                              source_id="KOSHA_MSDS", source_key="c-1"))
    assert store.count_current() == 2


def test_identity_source_key_null_allowed():
    """CSI-style: source_key MUST be nullable."""
    store = MemoryStore()
    w = Writer(store)
    w.upsert_current(_payload(
        object_type="CSI_ACCIDENT",
        canonical_id="CSI:abcd1234",
        source_id="CSI",
        source_key=None,
    ))
    row = store.get_current("CSI_ACCIDENT", "CSI:abcd1234")
    assert row is not None
    assert row["source_key"] is None


def test_identity_missing_source_id_rejected():
    store = MemoryStore()
    w = Writer(store)
    with pytest.raises(SearchContractError, match="source_id"):
        w.upsert_current(_payload(source_id=""))


# ---------------------------------------------------------------------------
# §45 CONTRACT VALIDATION
# ---------------------------------------------------------------------------


def test_unknown_publication_status_rejected():
    with pytest.raises(SearchContractError, match="publication_status"):
        normalize_document(_payload(publication_status="DRAFT"))


def test_unknown_visibility_scope_rejected():
    with pytest.raises(SearchContractError, match="visibility_scopes"):
        normalize_document(_payload(visibility_scopes=["ADMIN"]))


def test_unknown_context_type_rejected():
    with pytest.raises(SearchContractError, match="context_type"):
        normalize_document(_payload(context=[
            {"context_type": "employee", "context_key": "e-1"},
        ]))


def test_malformed_subject_rejected():
    with pytest.raises(SearchContractError, match="subject"):
        normalize_document(_payload(subjects=[
            {"subject_type": "LEGAL_TERM"},   # missing subject_key
        ]))


def test_duplicate_subjects_dedup_deterministic():
    doc = normalize_document(_payload(subjects=[
        {"subject_type": "LEGAL_TERM", "subject_key": "산업안전보건법"},
        {"subject_type": "LEGAL_TERM", "subject_key": "산업안전보건법"},
    ]))
    assert doc.subjects == (
        {"subject_type": "LEGAL_TERM", "subject_key": "산업안전보건법"},
    )


def test_duplicate_context_dedup_deterministic():
    doc = normalize_document(_payload(context=[
        {"context_type": "task", "context_key": "welding"},
        {"context_type": "sector", "context_key": "construction"},
        {"context_type": "task", "context_key": "welding"},
    ]))
    assert doc.context == (
        {"context_type": "sector", "context_key": "construction"},
        {"context_type": "task", "context_key": "welding"},
    )


# ---------------------------------------------------------------------------
# §46 HASH DETERMINISM
# ---------------------------------------------------------------------------


def test_hash_same_input_same_sha():
    a = normalize_document(_payload())
    a.content_hash = content_hash(a)
    b = normalize_document(_payload())
    b.content_hash = content_hash(b)
    assert a.content_hash == b.content_hash


def test_hash_aliases_order_irrelevant():
    a = normalize_document(_payload(aliases=["x", "y", "z"]))
    b = normalize_document(_payload(aliases=["z", "x", "y"]))
    assert content_hash(a) == content_hash(b)


def test_hash_subjects_order_irrelevant():
    a = normalize_document(_payload(subjects=[
        {"subject_type": "LEGAL_TERM", "subject_key": "산업안전보건법"},
        {"subject_type": "ACCIDENT_TERM", "subject_key": "추락"},
    ]))
    b = normalize_document(_payload(subjects=[
        {"subject_type": "ACCIDENT_TERM", "subject_key": "추락"},
        {"subject_type": "LEGAL_TERM", "subject_key": "산업안전보건법"},
    ]))
    assert content_hash(a) == content_hash(b)


def test_hash_context_order_irrelevant():
    a = normalize_document(_payload(context=[
        {"context_type": "task", "context_key": "welding"},
        {"context_type": "sector", "context_key": "construction"},
    ]))
    b = normalize_document(_payload(context=[
        {"context_type": "sector", "context_key": "construction"},
        {"context_type": "task", "context_key": "welding"},
    ]))
    assert content_hash(a) == content_hash(b)


def test_hash_title_change_flips_sha():
    a = normalize_document(_payload(title="A"))
    b = normalize_document(_payload(title="B"))
    assert content_hash(a) != content_hash(b)


def test_hash_source_updated_at_change_does_not_flip_sha():
    later = NOW + _dt.timedelta(days=7)
    a = normalize_document(_payload())
    b = normalize_document(_payload(source_updated_at=later))
    assert content_hash(a) == content_hash(b)   # source_updated_at excluded


# ---------------------------------------------------------------------------
# §47 FULL REBUILD
# ---------------------------------------------------------------------------


def test_rebuild_promotion_success():
    store = MemoryStore()
    fw = RebuildFramework(store)
    run = fw.begin(expected_domains=["GUIDE", "CHEM"])
    fw.stage(run, _payload(object_type="GUIDE", canonical_id="g1"))
    fw.stage(run, _payload(object_type="CHEM", canonical_id="c1",
                            source_id="KOSHA_MSDS", source_key="c1"))
    fw.mark_domain_done(run, "GUIDE")
    fw.mark_domain_done(run, "CHEM")
    fw.validate(run)
    assert run.status == RUN_STATUS_VALIDATED
    promoted = fw.promote(run)
    assert promoted == 2
    assert run.status == RUN_STATUS_PROMOTED
    assert store.count_current() == 2


def test_rebuild_validation_failure_keeps_current():
    store = MemoryStore()
    w = Writer(store)
    # Seed a pre-existing current row.
    w.upsert_current(_payload(object_type="GUIDE", canonical_id="pre-existing"))
    assert store.count_current() == 1

    fw = RebuildFramework(store)
    run = fw.begin(expected_domains=["GUIDE", "CHEM"])
    fw.stage(run, _payload(object_type="GUIDE", canonical_id="g1"))
    # Only GUIDE marks done; CHEM never completes.
    fw.mark_domain_done(run, "GUIDE")
    with pytest.raises(RebuildAborted, match="did not complete"):
        fw.validate(run)
    # current projection unchanged.
    assert store.count_current() == 1
    assert store.get_current("GUIDE", "pre-existing") is not None


def test_rebuild_promotion_failure_keeps_current(monkeypatch):
    store = MemoryStore()
    w = Writer(store)
    w.upsert_current(_payload(object_type="GUIDE", canonical_id="pre-existing"))
    fw = RebuildFramework(store)
    run = fw.begin(expected_domains=["GUIDE"])
    fw.stage(run, _payload(object_type="GUIDE", canonical_id="g1"))
    fw.mark_domain_done(run, "GUIDE")
    fw.validate(run)

    # Inject a failure inside the swap.
    def _boom(self, run_id):
        raise RuntimeError("simulated staging read failure")
    monkeypatch.setattr(MemoryStore, "iter_staging", _boom)

    with pytest.raises(RuntimeError):
        fw.promote(run)
    assert store.count_current() == 1
    assert store.get_current("GUIDE", "pre-existing") is not None
    # And the run is FAILED, not stuck in VALIDATED.
    run_row = store.get_run(run.run_id)
    assert run_row["status"] == RUN_STATUS_FAILED


def test_rebuild_repeat_deterministic():
    """Same input twice → same staged content hash."""
    store = MemoryStore()
    fw = RebuildFramework(store)
    run_a = fw.begin(expected_domains=["GUIDE"])
    fw.stage(run_a, _payload(object_type="GUIDE", canonical_id="g1"))
    hash_a = next(store.iter_staging(run_a.run_id))["content_hash"]

    run_b = fw.begin(expected_domains=["GUIDE"])
    fw.stage(run_b, _payload(object_type="GUIDE", canonical_id="g1"))
    hash_b = next(store.iter_staging(run_b.run_id))["content_hash"]

    assert hash_a == hash_b


def test_rebuild_only_published_promoted():
    """HOLD / REMOVED staged docs are NOT promoted into current."""
    store = MemoryStore()
    fw = RebuildFramework(store)
    run = fw.begin(expected_domains=["GUIDE"])
    fw.stage(run, _payload(object_type="GUIDE", canonical_id="live"))
    fw.stage(run, _payload(object_type="GUIDE", canonical_id="held",
                            publication_status=PUBLICATION_STATUS_HOLD,
                            visibility_scopes=[]))
    fw.stage(run, _payload(object_type="GUIDE", canonical_id="gone",
                            publication_status=PUBLICATION_STATUS_REMOVED,
                            visibility_scopes=[]))
    fw.mark_domain_done(run, "GUIDE")
    fw.validate(run)
    fw.promote(run)
    assert store.count_current() == 1
    assert store.get_current("GUIDE", "live") is not None
    assert store.get_current("GUIDE", "held") is None
    assert store.get_current("GUIDE", "gone") is None


# ---------------------------------------------------------------------------
# §48 OBJECT REINDEX
# ---------------------------------------------------------------------------


def test_reindex_insert():
    store = MemoryStore()
    w = Writer(store)
    w.upsert_current(_payload(canonical_id="new"))
    assert store.count_current() == 1


def test_reindex_update_changes_hash():
    store = MemoryStore()
    w = Writer(store)
    doc1 = w.upsert_current(_payload(canonical_id="upd", title="Old"))
    doc2 = w.upsert_current(_payload(canonical_id="upd", title="New"))
    assert doc1.content_hash != doc2.content_hash
    row = store.get_current(doc2.object_type, doc2.canonical_id)
    assert row["title"] == "New"


def test_reindex_no_op_same_hash():
    store = MemoryStore()
    w = Writer(store)
    a = w.upsert_current(_payload(canonical_id="noop"))
    b = w.upsert_current(_payload(canonical_id="noop"))
    assert a.content_hash == b.content_hash


def test_reindex_hold_removes_from_current():
    store = MemoryStore()
    w = Writer(store)
    w.upsert_current(_payload(canonical_id="x"))
    assert store.count_current() == 1
    w.upsert_current(_payload(canonical_id="x",
                              publication_status=PUBLICATION_STATUS_HOLD,
                              visibility_scopes=[]))
    assert store.count_current() == 0


def test_reindex_removed_removes_from_current():
    store = MemoryStore()
    w = Writer(store)
    w.upsert_current(_payload(canonical_id="y"))
    assert store.count_current() == 1
    w.upsert_current(_payload(canonical_id="y",
                              publication_status=PUBLICATION_STATUS_REMOVED,
                              visibility_scopes=[]))
    assert store.count_current() == 0


def test_explicit_tombstone():
    store = MemoryStore()
    w = Writer(store)
    w.upsert_current(_payload(canonical_id="z"))
    assert w.tombstone("GUIDE", "z") is True
    assert store.count_current() == 0
    # idempotent second tombstone returns False.
    assert w.tombstone("GUIDE", "z") is False


# ---------------------------------------------------------------------------
# §49 RECONCILE
# ---------------------------------------------------------------------------


def test_reconcile_match():
    store = MemoryStore()
    w = Writer(store)
    doc = w.upsert_current(_payload(canonical_id="a"))
    report = reconcile(store, "GUIDE", [
        {"canonical_id": "a", "content_hash": doc.content_hash},
    ])
    assert report.ok is True
    assert report.match == 1
    assert report.missing == ()
    assert report.extra == ()
    assert report.stale_by_hash == ()


def test_reconcile_missing():
    store = MemoryStore()
    report = reconcile(store, "GUIDE", [
        {"canonical_id": "a", "content_hash": "sha-a"},
    ])
    assert report.missing == ("a",)
    assert report.ok is False


def test_reconcile_extra():
    store = MemoryStore()
    w = Writer(store)
    w.upsert_current(_payload(canonical_id="extra-only"))
    report = reconcile(store, "GUIDE", [])
    assert report.extra == ("extra-only",)
    assert report.ok is False


def test_reconcile_stale_hash():
    store = MemoryStore()
    w = Writer(store)
    doc = w.upsert_current(_payload(canonical_id="drift"))
    report = reconcile(store, "GUIDE", [
        {"canonical_id": "drift", "content_hash": doc.content_hash + "!"},
    ])
    assert report.stale_by_hash == ("drift",)
    assert report.ok is False


def test_reconcile_no_mutation():
    store = MemoryStore()
    w = Writer(store)
    doc = w.upsert_current(_payload(canonical_id="a"))
    before = list(store.iter_current())
    reconcile(store, "GUIDE", [
        {"canonical_id": "a", "content_hash": doc.content_hash + "!"},
        {"canonical_id": "b", "content_hash": "sha-b"},
    ])
    after = list(store.iter_current())
    assert after == before   # reconcile did not touch the projection


# ---------------------------------------------------------------------------
# §50 RISK DRAFT NEGATIVE — never becomes discoverable
# ---------------------------------------------------------------------------


def test_risk_draft_never_indexed_via_upsert():
    """A RISK canonical in DRAFT (adapter maps to HOLD + no scopes)
    must not sit in the current projection."""
    store = MemoryStore()
    w = Writer(store)
    w.upsert_current(_payload(
        object_type="RISK",
        canonical_id="risk-uuid-1",
        source_id="risk_source",
        source_key="src-key-1",
        title="draft risk canonical",
        publication_status=PUBLICATION_STATUS_HOLD,
        visibility_scopes=[],
    ))
    assert store.count_current() == 0


def test_risk_draft_never_promoted_via_rebuild():
    store = MemoryStore()
    fw = RebuildFramework(store)
    run = fw.begin(expected_domains=["RISK"])
    fw.stage(run, _payload(
        object_type="RISK",
        canonical_id="risk-uuid-2",
        source_id="risk_source",
        source_key="src-key-2",
        title="draft risk canonical 2",
        publication_status=PUBLICATION_STATUS_HOLD,
        visibility_scopes=[],
    ))
    fw.mark_domain_done(run, "RISK")
    fw.validate(run)
    fw.promote(run)
    assert store.count_current() == 0


# ---------------------------------------------------------------------------
# §51 LEGAL SAFETY — no applicability leakage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("forbidden_key", [
    "legal_applicable", "applicability_score", "is_required",
    "compliance_score", "violation",
])
def test_legal_applicability_fields_rejected(forbidden_key):
    payload = _payload(object_type="LEGAL",
                        source_id="LEG_OFFICIAL",
                        source_key="leg-1",
                        canonical_id="leg-1")
    payload[forbidden_key] = True
    with pytest.raises(SearchContractError, match="forbidden"):
        normalize_document(payload)


# ---------------------------------------------------------------------------
# §52 TENANT SECRETS — never stored
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("forbidden_key", [
    "company_id", "factory_id", "user_id",
    "diagnosis_answer", "diagnosis_answers", "diagnosis_result",
    "api_key", "api_token", "access_token", "secret",
])
def test_tenant_fields_rejected(forbidden_key):
    payload = _payload()
    payload[forbidden_key] = "some-value"
    with pytest.raises(SearchContractError, match="forbidden"):
        normalize_document(payload)


# ---------------------------------------------------------------------------
# §53 NO LLM audit — package must not import LLM SDKs
# ---------------------------------------------------------------------------


def test_no_llm_dependency_in_foundation():
    """The services.shared_search package MUST NOT import LLM SDKs."""
    root = pathlib.Path(__file__).resolve().parents[1] / "services" / "shared_search"
    banned = re.compile(r"^\s*(?:import|from)\s+(openai|anthropic|langchain|llama_index|sentence_transformers)\b",
                        re.MULTILINE)
    for py in root.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert not banned.search(text), f"LLM SDK import in {py}"


def test_no_llm_inferred_match_type_forbidden():
    """The `llm_inferred` field name is a FORBIDDEN key."""
    payload = _payload()
    payload["llm_inferred"] = True
    with pytest.raises(SearchContractError, match="forbidden"):
        normalize_document(payload)


# ---------------------------------------------------------------------------
# §54 INTEGRATION CHAIN — end-to-end
# ---------------------------------------------------------------------------


def test_end_to_end_integration_chain():
    """
    fixture -> validate -> normalize -> hash -> stage
        -> candidate validation -> promote -> current read
        -> object reindex -> reconcile
    """
    store = MemoryStore()
    fw = RebuildFramework(store)

    # 1..5: FULL rebuild path
    run = fw.begin(expected_domains=["GUIDE", "CHEM"])
    guide_doc = _payload(object_type="GUIDE", canonical_id="g-int")
    chem_doc = _payload(
        object_type="CHEM", canonical_id="c-int",
        source_id="KOSHA_MSDS", source_key="c-int",
        subjects=[{"subject_type": "CHEM_TERM",
                    "subject_key": "물질안전보건자료"}],
    )
    fw.stage(run, guide_doc)
    fw.stage(run, chem_doc)
    fw.mark_domain_done(run, "GUIDE")
    fw.mark_domain_done(run, "CHEM")
    fw.validate(run)
    promoted = fw.promote(run)
    assert promoted == 2

    # 6: current read
    g = store.get_current("GUIDE", "g-int")
    c = store.get_current("CHEM", "c-int")
    assert g is not None and c is not None
    original_g_hash = g["content_hash"]

    # 7: OBJECT REINDEX — update guide title
    w = fw.writer
    w.upsert_current(_payload(object_type="GUIDE", canonical_id="g-int",
                              title="새 제목"))
    updated = store.get_current("GUIDE", "g-int")
    assert updated["title"] == "새 제목"
    assert updated["content_hash"] != original_g_hash

    # 8: reconcile — using current hashes → OK
    expected_feed = [
        {"canonical_id": row["canonical_id"], "content_hash": row["content_hash"]}
        for row in store.iter_current(object_type="GUIDE")
    ]
    report = reconcile(store, "GUIDE", expected_feed)
    assert report.ok is True
    assert report.match == 1

    # And no mutation happened during reconcile.
    after = list(store.iter_current())
    assert len(after) == 2
