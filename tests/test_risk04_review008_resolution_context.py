"""WO-RISK-04-REVIEW-008 MERGE/HOLD resolution context. No new semantic decision."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review006_completion_audit import (
    AUDIT_FIELDS,
    BATCH002_UNRESOLVED,
    EXPECTED_DECISIONS,
    EXPECTED_KINDS,
)
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
    HOLD_CONTEXT_FIELDS,
    HOLD_CONTEXT_PATH,
    MERGE_CONTEXT_FIELDS,
    MERGE_CONTEXT_PATH,
    REPORT_PATH,
    build_hold_context,
    build_merge_context,
    hold_context_sha,
    merge_context_sha,
    unresolved_evidence_counts,
)
from tools.risk04.review_decisions import load_tsv
from tools.risk04.seed_review import universe_sha

MERGE_SHA = "bc4314e740fb9d3f6a8c18bd5c055137662d989ff94c0f733e6479c75b4d299e"
HOLD_SHA = "0bd7fcb7a2b7a47ef2d8ecc3a6df9ae4092c546048f0bce35da2b4a4b54edf3d"
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
TRUNCATED = (
    "연질토사(N=",
    "저층(",
    "중층(",
    "고층(",
    "중질토사(N=",
    "경질토사(N=",
    "최경질토사(N=",
    "자갈석인연질토사(N=",
    "자갈석인경질토(N=",
)


def test_frozen_anchors_unchanged():
    audit = load_frozen_audit()
    assert universe_sha(audit, *AUDIT_FIELDS) == FROZEN_AUDIT_SHA
    assert lane_sha(load_tsv(LANE_PATH)) == FROZEN_LANE_SHA
    assert merge_sha(load_tsv(MERGE_EVIDENCE_PATH)) == FROZEN_MERGE_SHA
    assert hold_sha(load_tsv(HOLD_EVIDENCE_PATH)) == FROZEN_HOLD_SHA


def test_merge_identity_and_status():
    original = load_tsv(MERGE_EVIDENCE_PATH)
    rows = load_tsv(MERGE_CONTEXT_PATH)
    rebuilt = build_merge_context()
    assert list(rows[0].keys()) == list(MERGE_CONTEXT_FIELDS)
    assert len(rows) == 58
    assert len({row["seed_proposal_key"] for row in rows}) == 58
    assert {row["seed_proposal_key"] for row in rows} == {row["seed_proposal_key"] for row in original}
    assert [row["seed_proposal_key"] for row in rows] == [row["seed_proposal_key"] for row in original]
    statuses = Counter(row["reference_status"] for row in rows)
    assert statuses["EXPLICIT_REFERENCE"] == 49
    assert statuses["UNRESOLVED"] == 9
    unresolved = {int(row["source_review_no"]) for row in rows if row["reference_status"] == "UNRESOLVED"}
    assert unresolved == set(BATCH002_UNRESOLVED)
    assert merge_context_sha(rows) == merge_context_sha(rebuilt) == MERGE_SHA


def test_merge_gpt_pending():
    rows = load_tsv(MERGE_CONTEXT_PATH)
    assert all(row["gpt_merge_resolution"] == "PENDING" for row in rows)
    assert all(row["gpt_merge_target_keys"] == "EMPTY" for row in rows)
    assert all(row["gpt_merge_reason"] == "EMPTY" for row in rows)


def test_unresolved_not_resolved():
    rows = [row for row in load_tsv(MERGE_CONTEXT_PATH) if row["reference_status"] == "UNRESOLVED"]
    assert len(rows) == 9
    assert all(row["merge_candidate_keys"] == "UNRESOLVED" for row in rows)
    assert all(row["counterpart_count"] == "0" for row in rows)
    row_207 = next(row for row in rows if row["source_review_no"] == "207")
    assert row_207["name"] == "건축품질시험"
    assert row_207["counterpart_proposal_keys"] == "NOT_AVAILABLE"
    assert row_207["reverse_reference_count"] == "0"
    assert int(row_207["exact_raw_name_peer_count"]) >= 0


def test_reverse_reference_integrity():
    rows = load_tsv(MERGE_CONTEXT_PATH)
    by_proposal = {row["seed_proposal_key"]: row for row in rows}
    for row in rows:
        if row["reverse_reference_count"] == "0":
            continue
        keys = [part for part in row["reverse_reference_proposal_keys"].split(" | ") if part]
        assert str(len(keys)) == row["reverse_reference_count"]
        for key in keys:
            found = by_proposal[key]
            assert found["seed_proposal_key"] != row["seed_proposal_key"]
            assert row["seed_proposal_key"] in found["merge_candidate_keys"]


def test_hold_identity():
    original = load_tsv(HOLD_EVIDENCE_PATH)
    rows = load_tsv(HOLD_CONTEXT_PATH)
    rebuilt = build_hold_context()
    assert list(rows[0].keys()) == list(HOLD_CONTEXT_FIELDS)
    assert len(rows) == 25
    assert len({row["seed_proposal_key"] for row in rows}) == 25
    assert {row["seed_proposal_key"] for row in rows} == {row["seed_proposal_key"] for row in original}
    assert [row["seed_proposal_key"] for row in rows] == [row["seed_proposal_key"] for row in original]
    assert all(row["semantic_kind"] == "AMBIGUOUS" for row in rows)
    assert all(row["semantic_review_decision"] == "HOLD" for row in rows)
    names = {row["name"] for row in rows}
    assert set(TRUNCATED) <= names
    assert hold_context_sha(rows) == hold_context_sha(rebuilt) == HOLD_SHA


def test_hold_gpt_pending():
    rows = load_tsv(HOLD_CONTEXT_PATH)
    assert all(row["gpt_hold_resolution"] == "PENDING" for row in rows)
    assert all(row["gpt_resolved_semantic_kind"] == "PENDING" for row in rows)
    assert all(row["gpt_resolved_review_decision"] == "PENDING" for row in rows)
    assert all(row["gpt_hold_reason"] == "EMPTY" for row in rows)


def test_no_semantic_mutation():
    audit = load_frozen_audit()
    lanes = load_tsv(LANE_PATH)
    assert Counter(row["semantic_kind"] for row in audit) == EXPECTED_KINDS
    assert Counter(row["semantic_review_decision"] for row in audit) == EXPECTED_DECISIONS
    assert Counter(row["semantic_kind"] for row in lanes) == EXPECTED_KINDS
    assert Counter(row["semantic_review_decision"] for row in lanes) == EXPECTED_DECISIONS
    assert all(row["approval_state"] == "NOT_APPROVED" for row in lanes)


def test_no_classifier_or_resolution():
    src = Path("tools/risk04/review008_resolution_context.py").read_text(encoding="utf-8")
    lowered = src.lower()
    assert "openai" not in lowered
    assert "embedding" not in lowered
    assert "rapidfuzz" not in lowered
    assert "levenshtein" not in lowered
    assert "semantic_auto_merge" not in lowered
    assert "uuid4" not in src
    assert "approved_seed_manifest" not in src
    assert "canonical_nodes" not in src
    assert "This is an explicit evidence pack, not a classifier." in src
    report = REPORT_PATH.read_text(encoding="utf-8")
    assert "THIS IS NOT OWNER APPROVAL" in report
    assert "RISK-04-APPROVE-001 = NOT OPENED" in report
    assert "vector model calls = 0" in report
    assert "unresolved with reverse reference = 7" in report
    assert "unresolved with exact raw-name peer = 8" in report
    assert "unresolved with no deterministic candidate evidence = 0" in report
    for path in FROZEN_GPT:
        assert path.exists()


def test_unresolved_evidence_counts():
    counts = unresolved_evidence_counts(load_tsv(MERGE_CONTEXT_PATH))
    assert counts["reverse"] == 7
    assert counts["peer"] == 8
    assert counts["neither"] == 0


def test_determinism_two_runs():
    merge1 = build_merge_context()
    merge2 = build_merge_context()
    hold1 = build_hold_context()
    hold2 = build_hold_context()
    assert merge_context_sha(merge1) == merge_context_sha(merge2) == MERGE_SHA
    assert hold_context_sha(hold1) == hold_context_sha(hold2) == HOLD_SHA
