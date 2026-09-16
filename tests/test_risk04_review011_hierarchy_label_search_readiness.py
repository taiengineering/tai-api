"""WO-RISK-04-REVIEW-011 hierarchy/label/search readiness. No new semantic decision."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review010_candidate_universe import (
    EXCLUSIONS_PATH,
    MEMBERS_PATH,
    UNIVERSE_PATH,
    exclusions_sha_rows,
    members_sha_rows,
    universe_sha_rows,
)
from tools.risk04.review011_hierarchy_label_search_readiness import (
    CONCEPT_HIERARCHY_FIELDS,
    CONCEPT_HIERARCHY_PATH,
    CRITICAL_QUEUE_PATH,
    FROZEN_EXCLUSIONS_SHA,
    FROZEN_MEMBERS_SHA,
    FROZEN_UNIVERSE_SHA,
    LABEL_FIELDS,
    LABEL_PATH,
    MEMBER_HIERARCHY_FIELDS,
    MEMBER_HIERARCHY_PATH,
    REPORT_PATH,
    SEARCH_EXPORT_PATH,
    SEARCH_FIELDS,
    build_concept_hierarchy,
    build_critical_queue,
    build_label_readiness,
    build_member_hierarchy,
    build_search_export,
    concept_hierarchy_sha,
    critical_queue_sha,
    label_sha,
    member_hierarchy_sha,
    search_export_sha,
)
from tools.risk04.review_decisions import load_tsv

MEMBER_SHA = "fc1df8e5c8995243f0c1c95e10e916e90c9d6457106a9bcb49ece5cbcd9fb755"
CONCEPT_SHA = "430e00b2bebf531b71df6103d2619ce9d3764132ceafdc749ecdd05807bd2818"
LABEL_SHA = "25f05dc6aaea0438f95acdf3a7f6fff617016e9632ab9888666a809ffbcc43c6"
EXPORT_SHA = "4032472101c6a7180bdb5402c9bfae1fe3da656b24769be7c920229156edf4c0"
QUEUE_SHA = "7784bc16fe8d4b13cc1c7770cd76bbba84e2d83e27aeae5a13dd94f09db7c971"


def test_frozen_review010_unchanged():
    assert universe_sha_rows(load_tsv(UNIVERSE_PATH)) == FROZEN_UNIVERSE_SHA
    assert members_sha_rows(load_tsv(MEMBERS_PATH)) == FROZEN_MEMBERS_SHA
    assert exclusions_sha_rows(load_tsv(EXCLUSIONS_PATH)) == FROZEN_EXCLUSIONS_SHA
    assert len(load_tsv(UNIVERSE_PATH)) == 1111
    assert len(load_tsv(MEMBERS_PATH)) == 1140
    assert len(load_tsv(EXCLUSIONS_PATH)) == 582


def test_member_hierarchy():
    rows = load_tsv(MEMBER_HIERARCHY_PATH)
    rebuilt = build_member_hierarchy()
    assert list(rows[0].keys()) == list(MEMBER_HIERARCHY_FIELDS)
    assert len(rows) == 1140
    assert len({row["source_key"] for row in rows}) == 1140
    lookup = Counter(row["source_parent_lookup_status"] for row in rows)
    assert lookup["ROOT"] == 58
    assert lookup["EXACT_UNIQUE"] == 1082
    assert lookup["AMBIGUOUS_PATH"] == 0
    assert lookup["NOT_FOUND"] == 0
    assert all(row["hierarchy_evidence_status"] not in {"", "EMPTY"} for row in rows)
    assert member_hierarchy_sha(rows) == member_hierarchy_sha(rebuilt) == MEMBER_SHA


def test_concept_hierarchy():
    rows = load_tsv(CONCEPT_HIERARCHY_PATH)
    rebuilt = build_concept_hierarchy()
    assert list(rows[0].keys()) == list(CONCEPT_HIERARCHY_FIELDS)
    assert len(rows) == 1111
    assert len({row["review_concept_key"] for row in rows}) == 1111
    cats = Counter(row["hierarchy_readiness"] for row in rows)
    assert sum(cats.values()) == 1111
    assert cats["ROOT_READY"] == 56
    assert cats["SINGLE_PARENT_EVIDENCE"] == 1026
    assert cats["NO_CANDIDATE_PARENT"] == 23
    assert cats["MULTI_PARENT_REVIEW_REQUIRED"] == 4
    assert cats["CROSS_ROOT_REVIEW_REQUIRED"] == 2
    assert cats["SOURCE_PARENT_AMBIGUOUS"] == 0
    assert cats["SOURCE_PARENT_NOT_FOUND"] == 0
    assert sum(1 for row in rows if row["concept_form"] == "EQUIVALENCE_GROUP") == 28
    assert all(row["owner_approval_state"] == "NOT_APPROVED" for row in rows)
    assert concept_hierarchy_sha(rows) == concept_hierarchy_sha(rebuilt) == CONCEPT_SHA


def test_label_readiness():
    rows = load_tsv(LABEL_PATH)
    rebuilt = build_label_readiness()
    assert list(rows[0].keys()) == list(LABEL_FIELDS)
    assert len(rows) == 1111
    cats = Counter(row["label_readiness"] for row in rows)
    assert sum(cats.values()) == 1111
    assert cats["SINGLE_RAW_NAME"] == 1074
    assert cats["MULTI_MEMBER_SAME_RAW_NAME"] == 25
    assert cats["MULTI_RAW_NAME_VARIANTS"] == 2
    assert cats["LEXICAL_NOISE_REVIEW_REQUIRED"] == 10
    assert all(row["canonical_label_candidate"] == "EMPTY" for row in rows)
    assert all(row["canonical_label_status"] == "NOT_SELECTED" for row in rows)
    assert all(row["owner_approval_state"] == "NOT_APPROVED" for row in rows)
    assert label_sha(rows) == label_sha(rebuilt) == LABEL_SHA


def test_search_export_coverage():
    members = load_tsv(MEMBERS_PATH)
    exclusions = load_tsv(EXCLUSIONS_PATH)
    concepts = load_tsv(UNIVERSE_PATH)
    rows = load_tsv(SEARCH_EXPORT_PATH)
    rebuilt = build_search_export()
    assert list(rows[0].keys()) == list(SEARCH_FIELDS)
    assert len(rows) == 1140
    assert all(row["term_role"] == "SOURCE_NAME" for row in rows)
    assert all(row["term_evidence_status"] == "SOURCE_EVIDENCE" for row in rows)
    assert all(row["dictionary_review_status"] == "PROPOSED" for row in rows)
    assert all(row["canonical_link_status"] == "PREAPPROVAL_CONCEPT_ONLY" for row in rows)
    assert {row["seed_proposal_key"] for row in rows} == {row["seed_proposal_key"] for row in members}
    assert {row["review_concept_key"] for row in rows} == {row["review_concept_key"] for row in concepts}
    assert {row["source_key"] for row in rows} & {row["source_key"] for row in exclusions} == set()
    assert all(row["source_name"] == members[idx]["name"] for idx, row in enumerate(rows))
    assert search_export_sha(rows) == search_export_sha(rebuilt) == EXPORT_SHA


def test_critical_queue():
    queue = load_tsv(CRITICAL_QUEUE_PATH)
    rebuilt = build_critical_queue(load_tsv(CONCEPT_HIERARCHY_PATH), load_tsv(LABEL_PATH))
    assert len(queue) == 16
    assert len({row["review_concept_key"] for row in queue}) == 16
    assert all(row["gpt_resolution_status"] == "PENDING" for row in queue)
    assert all(row["gpt_resolution_notes"] == "EMPTY" for row in queue)
    for row in queue:
        reasons = set(row["review_reasons"].split(" | "))
        assert reasons & {
            "MULTI_PARENT_REVIEW_REQUIRED",
            "CROSS_ROOT_REVIEW_REQUIRED",
            "SOURCE_PARENT_AMBIGUOUS",
            "SOURCE_PARENT_NOT_FOUND",
            "LEXICAL_NOISE_REVIEW_REQUIRED",
        }
    assert critical_queue_sha(queue) == critical_queue_sha(rebuilt) == QUEUE_SHA


def test_no_kiwi_or_semantic_automation():
    src = Path("tools/risk04/review011_hierarchy_label_search_readiness.py").read_text(encoding="utf-8")
    lowered = src.lower()
    assert "kiwipiepy" not in lowered
    assert "kiwi(" not in src
    assert "add_user_word" not in src
    assert "openai" not in lowered
    assert "embedding" not in lowered
    assert "rapidfuzz" not in lowered
    assert "levenshtein" not in lowered
    assert "semantic_auto_merge" not in lowered
    assert "uuid4" not in src
    assert "canonical_nodes" not in src
    assert "approved_seed_manifest" not in src
    assert "This is a deterministic pre-approval readiness pack, not a classifier." in src
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "THIS IS NOT OWNER APPROVAL" in report
    assert "THIS IS NOT A CANONICAL HIERARCHY" in report
    assert "THIS IS NOT A CANONICAL LABEL MANIFEST" in report
    assert "THIS IS NOT AN APPROVED SEARCH DICTIONARY" in report
    assert "vector model calls = 0" in report or "Kiwi runtime calls = 0" in report


def test_determinism_two_runs():
    m1 = build_member_hierarchy()
    m2 = build_member_hierarchy()
    c1 = build_concept_hierarchy()
    c2 = build_concept_hierarchy()
    l1 = build_label_readiness()
    l2 = build_label_readiness()
    s1 = build_search_export()
    s2 = build_search_export()
    q1 = build_critical_queue(c1, l1)
    q2 = build_critical_queue(c2, l2)
    assert member_hierarchy_sha(m1) == member_hierarchy_sha(m2) == MEMBER_SHA
    assert concept_hierarchy_sha(c1) == concept_hierarchy_sha(c2) == CONCEPT_SHA
    assert label_sha(l1) == label_sha(l2) == LABEL_SHA
    assert search_export_sha(s1) == search_export_sha(s2) == EXPORT_SHA
    assert critical_queue_sha(q1) == critical_queue_sha(q2) == QUEUE_SHA
