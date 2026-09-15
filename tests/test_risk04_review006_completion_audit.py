"""WO-RISK-04-REVIEW-006 CIC_W full semantic completion audit. No new semantic decision."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk02.contract import SOURCE_CIC_W, SOURCE_KALIS, SOURCE_KOSHA
from tools.risk04.contract import A_NODE_COUNT, B_IDENTITY, B_PROPOSAL_NODES, C_TASK_NODES
from tools.risk04.review006_completion_audit import (
    APPROVAL_STATE,
    AUDIT_FIELDS,
    AUDIT_MANIFEST_PATH,
    AUDIT_REPORT_PATH,
    BATCH001_GPT_PATH,
    BATCH002_UNRESOLVED,
    SOURCE_PROPOSAL_UNIVERSE,
    audit_stats,
    build_audit_manifest,
    is_proposal_key,
    load_tsv,
    manifest_audit_sha,
    split_merge_keys,
)
from tools.risk04.review_decisions import GPT_MANIFEST_PATH

AUDIT_SHA = "4e37754d9fb8c62e47fbacc002c84d7b8565e3dbbcb7d4260afbb3b42606f7cb"
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


def _rows() -> list[dict]:
    return load_tsv(AUDIT_MANIFEST_PATH)


def test_cicw_exactly_1722_unique():
    rows = _rows()
    rebuilt = build_audit_manifest()
    assert len(rows) == A_NODE_COUNT == 1722
    assert len(rebuilt) == 1722
    assert len({row["source_key"] for row in rows}) == 1722
    assert len({row["seed_proposal_key"] for row in rows}) == 1722
    assert list(rows[0].keys()) == list(AUDIT_FIELDS)


def test_hierarchy_exact_62_373_1287():
    hierarchy = Counter(row["hierarchy_level"] for row in _rows())
    assert hierarchy["W_ROOT"] == 62
    assert hierarchy["W_MID"] == 373
    assert hierarchy["W_LEAF"] == 1287
    assert sum(hierarchy.values()) == 1722


def test_no_missing_duplicate_extra():
    stats = audit_stats(_rows())
    assert stats["coverage"]["missing"] == 0
    assert stats["coverage"]["duplicate"] == 0
    assert stats["coverage"]["extra"] == 0
    assert stats["coverage"]["unique_source_key"] == 1722


def test_semantic_totals_exact():
    kinds = Counter(row["semantic_kind"] for row in _rows())
    assert kinds["PROCESS"] == 579
    assert kinds["TASK"] == 553
    assert kinds["METHOD"] == 32
    assert kinds["MATERIAL_COMPONENT"] == 222
    assert kinds["FACILITY_EQUIPMENT"] == 210
    assert kinds["CLASSIFICATION"] == 101
    assert kinds["AMBIGUOUS"] == 25
    assert sum(kinds.values()) == 1722
    assert kinds["PROCESS"] + kinds["TASK"] == 1132
    assert (
        kinds["METHOD"]
        + kinds["MATERIAL_COMPONENT"]
        + kinds["FACILITY_EQUIPMENT"]
        + kinds["CLASSIFICATION"]
        + kinds["AMBIGUOUS"]
        == 590
    )


def test_decision_totals_exact():
    decisions = Counter(row["semantic_review_decision"] for row in _rows())
    assert decisions["KEEP_AS_DISTINCT"] == 1074
    assert decisions["MERGE_CANDIDATE"] == 58
    assert decisions["HOLD"] == 25
    assert decisions["REJECT"] == 565
    assert sum(decisions.values()) == 1722
    assert decisions["KEEP_AS_DISTINCT"] + decisions["MERGE_CANDIDATE"] == 1132
    assert decisions["HOLD"] + decisions["REJECT"] == 590


def test_semantic_decision_matrix_exact():
    rows = _rows()
    matrix = Counter((row["semantic_kind"], row["semantic_review_decision"]) for row in rows)
    kinds = Counter(row["semantic_kind"] for row in rows)
    assert matrix[("PROCESS", "HOLD")] == 0
    assert matrix[("PROCESS", "REJECT")] == 0
    assert matrix[("TASK", "HOLD")] == 0
    assert matrix[("TASK", "REJECT")] == 0
    assert matrix[("PROCESS", "KEEP_AS_DISTINCT")] + matrix[("PROCESS", "MERGE_CANDIDATE")] == kinds["PROCESS"]
    assert matrix[("TASK", "KEEP_AS_DISTINCT")] + matrix[("TASK", "MERGE_CANDIDATE")] == kinds["TASK"]
    assert matrix[("AMBIGUOUS", "HOLD")] == 25
    assert matrix[("AMBIGUOUS", "KEEP_AS_DISTINCT")] == 0
    assert matrix[("AMBIGUOUS", "MERGE_CANDIDATE")] == 0
    assert matrix[("AMBIGUOUS", "REJECT")] == 0
    assert matrix[("METHOD", "REJECT")] == 32
    assert matrix[("MATERIAL_COMPONENT", "REJECT")] == 222
    assert matrix[("FACILITY_EQUIPMENT", "REJECT")] == 210
    assert matrix[("CLASSIFICATION", "REJECT")] == 101


def test_merge_total_58():
    rows = [row for row in _rows() if row["semantic_review_decision"] == "MERGE_CANDIDATE"]
    assert len(rows) == 58
    assert all(row["semantic_kind"] in {"PROCESS", "TASK"} for row in rows)
    assert all(row["approval_state"] == APPROVAL_STATE for row in rows)


def test_batch002_unresolved_merge_9():
    rows = _rows()
    unresolved = [
        row
        for row in rows
        if row["source_review_stage"] == "BATCH002"
        and row["semantic_review_decision"] == "MERGE_CANDIDATE"
    ]
    assert {int(row["source_review_no"]) for row in unresolved} == set(BATCH002_UNRESOLVED)
    assert len(unresolved) == 9
    assert all(row["merge_candidate_keys"] == "UNRESOLVED" for row in unresolved)


def test_explicit_merge_reference_integrity():
    rows = _rows()
    proposal_keys = {row["seed_proposal_key"] for row in rows}
    merge_rows = [row for row in rows if row["semantic_review_decision"] == "MERGE_CANDIDATE"]
    unresolved_nos = {str(no) for no in BATCH002_UNRESOLVED}
    explicit = [
        row
        for row in merge_rows
        if not (row["source_review_stage"] == "BATCH002" and row["source_review_no"] in unresolved_nos)
    ]
    assert len(explicit) == 49
    for row in explicit:
        assert row["merge_candidate_keys"] not in {"EMPTY", "UNRESOLVED"}
        parts = split_merge_keys(row["merge_candidate_keys"])
        assert parts
        for part in parts:
            assert is_proposal_key(part)
            assert part != row["seed_proposal_key"]
            assert part in proposal_keys


def test_all_not_approved():
    rows = _rows()
    assert all(row["approval_state"] == "NOT_APPROVED" for row in rows)
    assert sum(1 for row in rows if row["approval_state"] == "NOT_APPROVED") == 1722


def test_no_canonical_uuid():
    src = Path("tools/risk04/review006_completion_audit.py").read_text(encoding="utf-8")
    assert "uuid4" not in src
    rows = _rows()
    blob = "\t".join(rows[0].keys())
    assert "uuid" not in blob.lower()
    stats = audit_stats(rows)
    assert stats["canonical_uuid_created"] == 0
    assert stats["active_canonicals"] == 0


def test_no_approved_mapping():
    stats = audit_stats(_rows())
    assert stats["approved_db_mappings"] == 0
    assert stats["mapping_approval_coverage"] == 0
    assert stats["owner_approved_seeds"] == 0
    src = Path("tools/risk04/review006_completion_audit.py").read_text(encoding="utf-8")
    assert "supabase" not in src.lower()
    assert "risk_source_mappings" not in src


def test_kosha_kalis_unchanged():
    batch001 = load_tsv(GPT_MANIFEST_PATH)
    assert BATCH001_GPT_PATH == GPT_MANIFEST_PATH
    assert sum(1 for row in batch001 if row["source_id"] == SOURCE_KALIS) == 50
    assert sum(1 for row in batch001 if row["source_id"] == SOURCE_KOSHA) == 0
    assert sum(1 for row in batch001 if row["source_id"] == SOURCE_CIC_W) == 50
    rows = _rows()
    assert all(row["source_review_stage"] in {
        "BATCH001", "BATCH002", "W_MID_REVIEW003",
        "LEAF_004A", "LEAF_004B", "LEAF_004C", "LEAF_004D", "LEAF_004E", "LEAF_004F",
    } for row in rows)
    stats = audit_stats(rows)
    assert stats["kosha_rows"] == 0
    assert stats["kalis_rows"] == 0
    assert stats["kosha_paths"] == B_PROPOSAL_NODES == 620
    assert stats["kosha_identity"] == B_IDENTITY == "HOLD"
    assert stats["kalis_tasks"] == C_TASK_NODES == 761
    assert SOURCE_PROPOSAL_UNIVERSE == 3103 == 1722 + 620 + 761


def test_no_classifier_or_auto_approval():
    src = Path("tools/risk04/review006_completion_audit.py").read_text(encoding="utf-8")
    assert "openai" not in src.lower()
    assert "rapidfuzz" not in src.lower()
    assert "re.compile" not in src
    assert "uuid4" not in src
    assert "This is an explicit completion audit, not a classifier." in src
    assert "not an Owner-approved seed" in src
    assert "Completed CIC_W semantic review audit of 1722 frozen GPT rows only." in src
    stats = audit_stats(_rows())
    assert stats["auto_merged"] == 0
    assert stats["auto_approved"] == 0
    report = AUDIT_REPORT_PATH.read_text(encoding="utf-8")
    assert "GLOBAL AUTO CLASSIFIER = NOT SAFE" in report
    assert "RISK-04-APPROVE-001 = NOT OPENED" in report
    for path in FROZEN_GPT:
        text = path.read_text(encoding="utf-8")
        assert text.splitlines()[0].startswith("batch_no\t") or text.splitlines()[0].startswith("review_no\t")


def test_audit_manifest_deterministic():
    first = build_audit_manifest()
    second = build_audit_manifest()
    sha1 = manifest_audit_sha(first)
    sha2 = manifest_audit_sha(second)
    written = manifest_audit_sha(_rows())
    assert sha1 == sha2 == written == AUDIT_SHA
    assert [row["source_key"] for row in first] == [row["source_key"] for row in second]
    stats = audit_stats(first)
    assert stats["semantic_unreviewed"] == 0
    assert stats["new_migration"] == 0
    assert stats["production_mutation"] == 0
    assert stats["llm_calls"] == 0
    assert "PASS_READY_FOR_VERIFY" in AUDIT_REPORT_PATH.read_text(encoding="utf-8")
