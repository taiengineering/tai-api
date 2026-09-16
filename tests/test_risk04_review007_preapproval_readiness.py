"""WO-RISK-04-REVIEW-007 pre-approval review readiness. No new semantic decision."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review006_completion_audit import AUDIT_MANIFEST_PATH, BATCH002_UNRESOLVED
from tools.risk04.review007_preapproval_readiness import (
    APPROVAL_STATE,
    FROZEN_AUDIT_SHA,
    HOLD_EVIDENCE_PATH,
    LANE_FIELDS,
    LANE_PATH,
    MERGE_EVIDENCE_PATH,
    REPORT_PATH,
    build_hold_evidence,
    build_merge_evidence,
    build_review_lanes,
    hold_sha,
    lane_sha,
    load_frozen_audit,
    merge_sha,
)
from tools.risk04.review_decisions import load_tsv

LANE_SHA = "1df94aeb950601a1819fab14628b78f50c17cd499fbdc4ef758e2b13124a4ce5"
MERGE_SHA = "6c9e5292c024878135d318d1c466a231913e73eaa885d64d7597836662ad2344"
HOLD_SHA = "0e7c52fd2c4a7f2ef769b482729c96d4d4aaf5cefdeb70dce559cdcaad02f0a7"
FROZEN_GPT = (
    Path("docs/knowledge/risk/RISK04_BATCH001_GPT_REVIEW_v1.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_BATCH002_GPT_REVIEW_v1.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_MID_REVIEW003_GPT_REVIEW_v1.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004A_GPT_REVIEW_v1.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004B_GPT_REVIEW_v1.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004C_GPT_REVIEW_v1.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004D_GPT_REVIEW_v1.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004E_GPT_REVIEW_v1.tsv"),
    Path("docs/knowledge/risk/RISK04_CICW_LEAF_BATCH004F_GPT_REVIEW_v1.tsv"),
)


def test_frozen_audit_sha_unchanged():
    rows = load_frozen_audit()
    assert len(rows) == 1722
    assert universe_like(rows) == FROZEN_AUDIT_SHA
    assert AUDIT_MANIFEST_PATH.read_text(encoding="utf-8").count("\n") >= 1722


def universe_like(rows: list[dict]) -> str:
    from tools.risk04.review006_completion_audit import AUDIT_FIELDS
    from tools.risk04.seed_review import universe_sha

    return universe_sha(rows, *AUDIT_FIELDS)


def test_review_lanes_exact():
    rows = load_tsv(LANE_PATH)
    rebuilt = build_review_lanes()
    assert list(rows[0].keys()) == list(LANE_FIELDS)
    assert len(rows) == 1722
    assert len({row["source_key"] for row in rows}) == 1722
    lanes = Counter(row["review_lane"] for row in rows)
    assert lanes["DISTINCT_CANDIDATE"] == 1074
    assert lanes["MERGE_REVIEW"] == 58
    assert lanes["HOLD_REVIEW"] == 25
    assert lanes["REFERENCE_ONLY"] == 565
    assert all(row["approval_state"] == APPROVAL_STATE for row in rows)
    assert lane_sha(rows) == lane_sha(rebuilt) == LANE_SHA


def test_no_missing_duplicate_extra():
    rows = load_tsv(LANE_PATH)
    keys = [row["source_key"] for row in rows]
    assert len(keys) == 1722
    assert len(set(keys)) == 1722


def test_merge_evidence_exact():
    rows = load_tsv(MERGE_EVIDENCE_PATH)
    rebuilt = build_merge_evidence()
    assert len(rows) == 58
    statuses = Counter(row["reference_status"] for row in rows)
    assert statuses["EXPLICIT_REFERENCE"] == 49
    assert statuses["UNRESOLVED"] == 9
    unresolved = {int(row["source_review_no"]) for row in rows if row["reference_status"] == "UNRESOLVED"}
    assert unresolved == set(BATCH002_UNRESOLVED)
    assert all(row["gpt_merge_resolution"] == "PENDING" for row in rows)
    assert all(row["gpt_merge_reason"] == "EMPTY" for row in rows)
    assert all(row["semantic_kind"] in {"PROCESS", "TASK"} for row in rows)
    explicit = [row for row in rows if row["reference_status"] == "EXPLICIT_REFERENCE"]
    assert all(row["merge_candidate_keys"] not in {"EMPTY", "UNRESOLVED"} for row in explicit)
    assert merge_sha(rows) == merge_sha(rebuilt) == MERGE_SHA


def test_hold_evidence_exact():
    rows = load_tsv(HOLD_EVIDENCE_PATH)
    rebuilt = build_hold_evidence()
    assert len(rows) == 25
    assert all(row["semantic_kind"] == "AMBIGUOUS" for row in rows)
    assert all(row["semantic_review_decision"] == "HOLD" for row in rows)
    assert all(row["gpt_hold_resolution"] == "PENDING" for row in rows)
    assert all(row["gpt_hold_reason"] == "EMPTY" for row in rows)
    assert hold_sha(rows) == hold_sha(rebuilt) == HOLD_SHA


def test_approval_boundary():
    lanes = load_tsv(LANE_PATH)
    assert sum(1 for row in lanes if row["approval_state"] == "NOT_APPROVED") == 1722
    assert sum(1 for row in lanes if row["approval_state"] == "APPROVED") == 0
    src = Path("tools/risk04/review007_preapproval_readiness.py").read_text(encoding="utf-8")
    assert "uuid4" not in src
    assert "supabase" not in src.lower()
    assert "approved_seed_manifest" not in src
    assert "canonical_nodes" not in src


def test_structural_invariants():
    lanes = load_tsv(LANE_PATH)
    kinds = Counter(row["semantic_kind"] for row in lanes)
    lane_n = Counter(row["review_lane"] for row in lanes)
    assert kinds["PROCESS"] + kinds["TASK"] == 1132
    assert lane_n["DISTINCT_CANDIDATE"] + lane_n["MERGE_REVIEW"] == 1132
    assert (
        kinds["METHOD"]
        + kinds["MATERIAL_COMPONENT"]
        + kinds["FACILITY_EQUIPMENT"]
        + kinds["CLASSIFICATION"]
        + kinds["AMBIGUOUS"]
        == 590
    )
    assert lane_n["REFERENCE_ONLY"] + lane_n["HOLD_REVIEW"] == 590


def test_no_classifier_or_resolution():
    src = Path("tools/risk04/review007_preapproval_readiness.py").read_text(encoding="utf-8")
    lowered = src.lower()
    assert "openai" not in lowered
    assert "embedding" not in lowered
    assert "rapidfuzz" not in lowered
    assert "levenshtein" not in lowered
    assert "semantic_auto_merge" not in lowered
    assert "re.compile" not in src
    assert "This is an explicit evidence pack, not a classifier." in src
    merge = load_tsv(MERGE_EVIDENCE_PATH)
    hold = load_tsv(HOLD_EVIDENCE_PATH)
    assert all(row["gpt_merge_resolution"] == "PENDING" for row in merge)
    assert all(row["gpt_hold_resolution"] == "PENDING" for row in hold)
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "THIS IS NOT OWNER APPROVAL" in report
    assert "RISK-04-APPROVE-001 = NOT OPENED" in report
    assert "vector model calls = 0" in report
    for path in FROZEN_GPT:
        assert path.exists()


def test_determinism_two_runs():
    audit = load_frozen_audit()
    lane1 = build_review_lanes(audit)
    lane2 = build_review_lanes(audit)
    merge1 = build_merge_evidence(audit)
    merge2 = build_merge_evidence(audit)
    hold1 = build_hold_evidence(audit)
    hold2 = build_hold_evidence(audit)
    assert lane_sha(lane1) == lane_sha(lane2) == LANE_SHA
    assert merge_sha(merge1) == merge_sha(merge2) == MERGE_SHA
    assert hold_sha(hold1) == hold_sha(hold2) == HOLD_SHA
