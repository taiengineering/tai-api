"""WO-RISK-04-REVIEW-009 GPT MERGE/HOLD resolution freeze. No new semantic decision."""
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
    HOLD_GPT_FIELDS,
    HOLD_GPT_PATH,
    HOLD_METHOD_REJECT,
    HOLD_RETAIN,
    HOLD_TASK_KEEP,
    KEEP_SEPARATE,
    MERGE_GPT_FIELDS,
    MERGE_GPT_PATH,
    REPORT_PATH,
    build_hold_gpt,
    build_merge_gpt,
    effective_counts,
    hold_gpt_sha,
    merge_gpt_sha,
)
from tools.risk04.review_decisions import load_tsv
from tools.risk04.seed_review import universe_sha

MERGE_SHA = "906ada1b158ca43915c59591a94aba0aa908476b5c6c8f19c759c2cbd1c1086f"
HOLD_SHA = "a73c2d2708eaf653a95280ab8e769d1e3c2690bddb3eb5c80d08c55d8e725dec"


def test_frozen_inputs_unchanged():
    audit = load_frozen_audit()
    assert universe_sha(audit, *AUDIT_FIELDS) == FROZEN_AUDIT_SHA
    assert lane_sha(load_tsv(LANE_PATH)) == FROZEN_LANE_SHA
    assert merge_sha(load_tsv(MERGE_EVIDENCE_PATH)) == FROZEN_MERGE_SHA
    assert hold_sha(load_tsv(HOLD_EVIDENCE_PATH)) == FROZEN_HOLD_SHA
    assert merge_context_sha(load_tsv(MERGE_CONTEXT_PATH)) == FROZEN_MERGE_CONTEXT_SHA
    assert hold_context_sha(load_tsv(HOLD_CONTEXT_PATH)) == FROZEN_HOLD_CONTEXT_SHA
    assert Counter(row["semantic_kind"] for row in audit) == EXPECTED_KINDS
    assert Counter(row["semantic_review_decision"] for row in audit) == EXPECTED_DECISIONS


def test_merge_exact():
    original = load_tsv(MERGE_CONTEXT_PATH)
    rows = load_tsv(MERGE_GPT_PATH)
    rebuilt = build_merge_gpt()
    assert list(rows[0].keys()) == list(MERGE_GPT_FIELDS)
    assert len(rows) == 58
    assert [row["seed_proposal_key"] for row in rows] == [row["seed_proposal_key"] for row in original]
    statuses = Counter(row["gpt_merge_resolution"] for row in rows)
    assert statuses["MERGE_CONFIRMED"] == 55
    assert statuses["KEEP_SEPARATE"] == 3
    assert statuses.get("PENDING", 0) == 0
    keep = [row for row in rows if row["gpt_merge_resolution"] == "KEEP_SEPARATE"]
    assert {int(row["source_review_no"]) for row in keep} == set(KEEP_SEPARATE)
    assert {(int(row["source_review_no"]), row["source_key"]) for row in keep} == {
        (664, "825"),
        (915, "1869"),
        (922, "1879"),
    }
    assert all(row["gpt_merge_target_keys"] == "EMPTY" for row in keep)
    assert all(row["approval_state"] == "NOT_APPROVED" for row in rows)
    assert merge_gpt_sha(rows) == merge_gpt_sha(rebuilt) == MERGE_SHA


def test_equivalence_groups():
    rows = load_tsv(MERGE_GPT_PATH)
    confirmed = [row for row in rows if row["gpt_merge_resolution"] == "MERGE_CONFIRMED"]
    groups = {frozenset(group) for group in EQUIVALENCE_GROUPS}
    assert len(EQUIVALENCE_GROUPS) == 28
    assert len(groups) == 28
    assert frozenset({"86", "863", "8631"}) in groups
    assert all("825" not in group for group in groups)
    assert frozenset({"831", "8311"}) in groups
    assert frozenset({"822", "8222"}) in groups
    assert frozenset({"822", "8222", "831", "8311"}) not in groups
    members = {key for group in EQUIVALENCE_GROUPS for key in group}
    assert len(members) == 57
    assert members - {row["source_key"] for row in confirmed} == {"073", "226"}
    written = {frozenset(row["resolution_group_source_keys"].split(" | ")) for row in confirmed}
    assert written == groups


def test_merge_targets():
    audit = load_frozen_audit()
    rows = load_tsv(MERGE_GPT_PATH)
    proposals = {row["seed_proposal_key"] for row in audit}
    confirmed = [row for row in rows if row["gpt_merge_resolution"] == "MERGE_CONFIRMED"]
    keep = [row for row in rows if row["gpt_merge_resolution"] == "KEEP_SEPARATE"]
    assert all(row["gpt_merge_target_keys"] != "EMPTY" for row in confirmed)
    assert all(row["gpt_merge_target_keys"] == "EMPTY" for row in keep)
    invalid = 0
    for row in confirmed:
        for key in row["gpt_merge_target_keys"].split(" | "):
            if key not in proposals or key == row["seed_proposal_key"]:
                invalid += 1
    assert invalid == 0


def test_hold_exact():
    original = load_tsv(HOLD_CONTEXT_PATH)
    rows = load_tsv(HOLD_GPT_PATH)
    rebuilt = build_hold_gpt()
    assert list(rows[0].keys()) == list(HOLD_GPT_FIELDS)
    assert len(rows) == 25
    assert [row["seed_proposal_key"] for row in rows] == [row["seed_proposal_key"] for row in original]
    task = [
        int(row["source_review_no"])
        for row in rows
        if row["gpt_resolved_semantic_kind"] == "TASK" and row["gpt_resolved_review_decision"] == "KEEP_AS_DISTINCT"
    ]
    method = [
        int(row["source_review_no"])
        for row in rows
        if row["gpt_resolved_semantic_kind"] == "METHOD" and row["gpt_resolved_review_decision"] == "REJECT"
    ]
    retain = [int(row["source_review_no"]) for row in rows if row["gpt_hold_resolution"] == "RETAIN_HOLD"]
    assert len(task) == 8 and set(task) == set(HOLD_TASK_KEEP)
    assert len(method) == 7 and set(method) == set(HOLD_METHOD_REJECT)
    assert len(retain) == 10 and set(retain) == set(HOLD_RETAIN)
    assert all(row["gpt_hold_resolution"] != "PENDING" for row in rows)
    names = {row["name"] for row in rows if row["gpt_hold_resolution"] == "RETAIN_HOLD"}
    assert "Attiplugite슬러리월" in names
    assert "연질토사(N=" in names
    assert "자갈석인경질토(N=" in names
    assert all(row["approval_state"] == "NOT_APPROVED" for row in rows)
    assert hold_gpt_sha(rows) == hold_gpt_sha(rebuilt) == HOLD_SHA


def test_effective_aggregates_and_lanes():
    derived = effective_counts(load_frozen_audit(), load_tsv(MERGE_GPT_PATH), load_tsv(HOLD_GPT_PATH))
    assert derived["kinds"]["PROCESS"] == 579
    assert derived["kinds"]["TASK"] == 561
    assert derived["kinds"]["METHOD"] == 39
    assert derived["kinds"]["MATERIAL_COMPONENT"] == 222
    assert derived["kinds"]["FACILITY_EQUIPMENT"] == 210
    assert derived["kinds"]["CLASSIFICATION"] == 101
    assert derived["kinds"]["AMBIGUOUS"] == 10
    assert sum(derived["kinds"].values()) == 1722
    assert derived["lanes"]["DISTINCT_CANDIDATE"] == 1085
    assert derived["lanes"]["MERGE_CONFIRMED"] == 55
    assert derived["lanes"]["HOLD_RETAIN"] == 10
    assert derived["lanes"]["REFERENCE_ONLY"] == 572
    assert sum(derived["lanes"].values()) == 1722
    assert derived["group_members"] == 57
    assert derived["groups"] == 28
    assert derived["reduction"] == 29
    assert derived["canonical_kind_rows"] == 1140
    assert derived["concept_candidates"] == 1111


def test_no_classifier_or_approval():
    src = Path("tools/risk04/review009_resolution_freeze.py").read_text(encoding="utf-8")
    lowered = src.lower()
    assert "openai" not in lowered
    assert "embedding" not in lowered
    assert "rapidfuzz" not in lowered
    assert "levenshtein" not in lowered
    assert "semantic_auto_merge" not in lowered
    assert "uuid4" not in src
    assert "approved_seed_manifest" not in src
    assert "canonical_nodes" not in src
    assert "This is an explicit GPT freeze overlay, not a classifier." in src
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "THIS IS NOT OWNER APPROVAL" in report
    assert "RISK-04-APPROVE-001 = NOT OPENED" in report
    assert "pre-approval review concept candidates = 1111" in report
    assert "vector model calls = 0" in report


def test_determinism_two_runs():
    merge1 = build_merge_gpt()
    merge2 = build_merge_gpt()
    hold1 = build_hold_gpt()
    hold2 = build_hold_gpt()
    assert merge_gpt_sha(merge1) == merge_gpt_sha(merge2) == MERGE_SHA
    assert hold_gpt_sha(hold1) == hold_gpt_sha(hold2) == HOLD_SHA
