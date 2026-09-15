"""WO-RISK-04-REVIEW-010 pre-approval candidate universe. No new semantic decision."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review006_completion_audit import AUDIT_FIELDS, EXPECTED_DECISIONS, EXPECTED_KINDS
from tools.risk04.review007_preapproval_readiness import (
    FROZEN_AUDIT_SHA,
    HOLD_EVIDENCE_PATH,
    LANE_PATH,
    MERGE_EVIDENCE_PATH,
    hold_sha,
    lane_sha,
    load_frozen_audit,
    merge_sha,
)
from tools.risk04.review008_resolution_context import (
    FROZEN_HOLD_SHA,
    FROZEN_LANE_SHA,
    FROZEN_MERGE_SHA,
    HOLD_CONTEXT_PATH,
    MERGE_CONTEXT_PATH,
    hold_context_sha,
    merge_context_sha,
)
from tools.risk04.review009_resolution_freeze import (
    EQUIVALENCE_GROUPS,
    FROZEN_HOLD_CONTEXT_SHA,
    FROZEN_MERGE_CONTEXT_SHA,
    HOLD_GPT_PATH,
    MERGE_GPT_PATH,
    hold_gpt_sha,
    merge_gpt_sha,
)
from tools.risk04.review010_candidate_universe import (
    EXCLUSION_FIELDS,
    EXCLUSIONS_PATH,
    FROZEN_HOLD_GPT_SHA,
    FROZEN_MERGE_GPT_SHA,
    MEMBER_FIELDS,
    MEMBERS_PATH,
    REPORT_PATH,
    UNIVERSE_FIELDS,
    UNIVERSE_PATH,
    build_candidate_universe,
    exclusions_sha_rows,
    members_sha_rows,
    review_concept_key,
    universe_sha_rows,
)
from tools.risk04.review_decisions import load_tsv
from tools.risk04.seed_review import universe_sha

UNIVERSE_SHA = "0f05f4443cbac19b1b3fa97f1204f2c75785a027889f0be35f1e0acd0d7e61a8"
MEMBERS_SHA = "b341204156611e12057f9113a6692b2c1d04e07f63eec151a53994928b9fde84"
EXCLUSIONS_SHA = "123b8c0361d829cd751970baf138373e3f98911ab787a1e5b7dabfc27489daca"


def test_frozen_inputs_unchanged():
    audit = load_frozen_audit()
    assert universe_sha(audit, *AUDIT_FIELDS) == FROZEN_AUDIT_SHA
    assert Counter(row["semantic_kind"] for row in audit) == EXPECTED_KINDS
    assert Counter(row["semantic_review_decision"] for row in audit) == EXPECTED_DECISIONS
    assert lane_sha(load_tsv(LANE_PATH)) == FROZEN_LANE_SHA
    assert merge_sha(load_tsv(MERGE_EVIDENCE_PATH)) == FROZEN_MERGE_SHA
    assert hold_sha(load_tsv(HOLD_EVIDENCE_PATH)) == FROZEN_HOLD_SHA
    assert merge_context_sha(load_tsv(MERGE_CONTEXT_PATH)) == FROZEN_MERGE_CONTEXT_SHA
    assert hold_context_sha(load_tsv(HOLD_CONTEXT_PATH)) == FROZEN_HOLD_CONTEXT_SHA
    assert merge_gpt_sha(load_tsv(MERGE_GPT_PATH)) == FROZEN_MERGE_GPT_SHA
    assert hold_gpt_sha(load_tsv(HOLD_GPT_PATH)) == FROZEN_HOLD_GPT_SHA


def test_concept_counts():
    rows = load_tsv(UNIVERSE_PATH)
    rebuilt, _, _ = build_candidate_universe()
    assert list(rows[0].keys()) == list(UNIVERSE_FIELDS)
    assert len(rows) == 1111
    forms = Counter(row["concept_form"] for row in rows)
    kinds = Counter(row["effective_semantic_kind"] for row in rows)
    assert forms["SINGLETON"] == 1083
    assert forms["EQUIVALENCE_GROUP"] == 28
    assert kinds["PROCESS"] == 557
    assert kinds["TASK"] == 554
    assert len({row["review_concept_key"] for row in rows}) == 1111
    assert sum(int(row["member_count"]) for row in rows) == 1140
    assert all(row["owner_approval_state"] == "NOT_APPROVED" for row in rows)
    assert universe_sha_rows(rows) == universe_sha_rows(rebuilt) == UNIVERSE_SHA


def test_candidate_members_and_origins():
    rows = load_tsv(MEMBERS_PATH)
    assert list(rows[0].keys()) == list(MEMBER_FIELDS)
    assert len(rows) == 1140
    kinds = Counter(row["effective_semantic_kind"] for row in rows)
    origins = Counter(row["source_candidate_origin"] for row in rows)
    forms = Counter(row["concept_form"] for row in rows)
    assert kinds["PROCESS"] == 579
    assert kinds["TASK"] == 561
    assert origins["ORIGINAL_KEEP"] == 1074
    assert origins["MERGE_CONFIRMED"] == 55
    assert origins["MERGE_KEEP_SEPARATE"] == 3
    assert origins["HOLD_RESOLVED_TASK"] == 8
    assert forms["EQUIVALENCE_GROUP"] == 57
    assert forms["SINGLETON"] == 1083
    group_kinds = Counter(
        row["effective_semantic_kind"] for row in rows if row["concept_form"] == "EQUIVALENCE_GROUP"
    )
    assert group_kinds["PROCESS"] == 43
    assert group_kinds["TASK"] == 14
    assert all(row["owner_approval_state"] == "NOT_APPROVED" for row in rows)


def test_group_and_singleton_breakdown():
    concepts = load_tsv(UNIVERSE_PATH)
    groups = [row for row in concepts if row["concept_form"] == "EQUIVALENCE_GROUP"]
    singles = [row for row in concepts if row["concept_form"] == "SINGLETON"]
    assert len(groups) == 28
    assert Counter(row["effective_semantic_kind"] for row in groups) == {"PROCESS": 21, "TASK": 7}
    assert Counter(row["effective_semantic_kind"] for row in singles) == {"PROCESS": 536, "TASK": 547}
    written = {frozenset(row["member_source_keys"].split(" | ")) for row in groups}
    assert written == {frozenset(group) for group in EQUIVALENCE_GROUPS}
    assert all("825" not in row["member_source_keys"].split(" | ") for row in groups)
    members = load_tsv(MEMBERS_PATH)
    row_825 = next(row for row in members if row["source_key"] == "825")
    assert row_825["concept_form"] == "SINGLETON"
    for key in ("073", "226"):
        found = next(row for row in members if row["source_key"] == key)
        assert found["concept_form"] == "EQUIVALENCE_GROUP"
        assert found["source_candidate_origin"] == "ORIGINAL_KEEP"
        assert sum(1 for row in members if row["source_key"] == key) == 1


def test_exclusions():
    rows = load_tsv(EXCLUSIONS_PATH)
    assert list(rows[0].keys()) == list(EXCLUSION_FIELDS)
    assert len(rows) == 582
    lanes = Counter(row["exclusion_lane"] for row in rows)
    kinds = Counter(row["effective_semantic_kind"] for row in rows)
    assert lanes["REFERENCE_ONLY"] == 572
    assert lanes["HOLD_RETAIN"] == 10
    assert kinds["METHOD"] == 39
    assert kinds["MATERIAL_COMPONENT"] == 222
    assert kinds["FACILITY_EQUIPMENT"] == 210
    assert kinds["CLASSIFICATION"] == 101
    assert kinds["AMBIGUOUS"] == 10
    assert all(row["owner_approval_state"] == "NOT_APPROVED" for row in rows)


def test_full_coverage():
    audit = load_frozen_audit()
    members = load_tsv(MEMBERS_PATH)
    exclusions = load_tsv(EXCLUSIONS_PATH)
    concepts = load_tsv(UNIVERSE_PATH)
    cand = [row["source_key"] for row in members]
    excl = [row["source_key"] for row in exclusions]
    all_keys = [row["source_key"] for row in audit]
    assert len(cand) == 1140
    assert len(excl) == 582
    assert set(cand) & set(excl) == set()
    assert set(cand) | set(excl) == set(all_keys)
    assert len(set(cand)) == 1140
    assert len(set(excl)) == 582
    assert len(all_keys) == 1722
    known = {row["review_concept_key"] for row in concepts}
    assert all(row["review_concept_key"] in known for row in members)
    assert all(int(row["member_count"]) > 0 for row in concepts)


def test_concept_key_uses_sorted_proposal_keys_only():
    concepts = load_tsv(UNIVERSE_PATH)
    for row in concepts:
        keys = row["member_seed_proposal_keys"].split(" | ")
        assert row["review_concept_key"] == review_concept_key(keys)
        assert row["review_concept_key"] == review_concept_key(list(reversed(keys)))
    src = Path("tools/risk04/review010_candidate_universe.py").read_text(encoding="utf-8")
    assert "uuid4" not in src
    assert "supabase" not in src.lower()
    assert "approved_seed_manifest" not in src
    assert "owner_approved_manifest" not in src
    assert "approved_mapping_manifest" not in src
    assert "canonical_nodes" not in src
    assert "parent_id" not in src
    assert "canonical_parent" not in src
    lowered = src.lower()
    assert "openai" not in lowered
    assert "embedding" not in lowered
    assert "rapidfuzz" not in lowered
    assert "levenshtein" not in lowered
    assert "semantic_auto_merge" not in lowered
    assert "This is a deterministic pre-approval projection, not a classifier." in src
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "THIS IS NOT OWNER APPROVAL" in report
    assert "THIS IS NOT A CANONICAL MANIFEST" in report
    assert "candidate concepts = 1111" in report
    assert "vector model calls = 0" in report


def test_determinism_two_runs():
    c1, m1, e1 = build_candidate_universe()
    c2, m2, e2 = build_candidate_universe()
    assert universe_sha_rows(c1) == universe_sha_rows(c2) == UNIVERSE_SHA
    assert members_sha_rows(m1) == members_sha_rows(m2) == MEMBERS_SHA
    assert exclusions_sha_rows(e1) == exclusions_sha_rows(e2) == EXCLUSIONS_SHA
