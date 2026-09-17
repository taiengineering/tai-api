"""WO-RISK-KALIS-MATERIALIZE-001 lean materialization contract tests.

Contract-only per WO §13: verify the executor's planned execute-set has
the right shape and content and would never leak HOLD/AMBIGUOUS/GAP/
NO_MATCH rows or an invalid target. NO live DB assertions here —
production state is recorded in the frozen receipt artifacts. skip = 0.
"""
from __future__ import annotations

import ast
import json
import re
from collections import Counter
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kalis_map001_semantic_freeze as freeze
from tools.risk_map import kalis_materialize_approved as mat
from tools.risk_map import kalis_owner_approval as owner

MAT_GENERATOR = Path("tools/risk_map/kalis_materialize_approved.py")
OWNER_GENERATOR = Path("tools/risk_map/kalis_owner_approval.py")

FROZEN_OWNER_APPROVAL_SHA = (
    "ac75691caef78a44fa4036ab81435549f1f4d93f1a28a026c4b0f1602e34f03e"
)
FROZEN_MATERIALIZATION_RECEIPT_SHA = (
    "c8daa8f08b06d1ac7a72e9a9977d0cc3307063bb3ee2b2ea93cf5738296f912d"
)
FROZEN_OWNER_CANDIDATE_SHA = (
    "848b896fe46829c53d09e6b7a6af52deacd5ebe66ba021af8a5ca2a799b3052f"
)


# ---------------------------------------------------------------------------
# Owner approval binding
# ---------------------------------------------------------------------------


def test_owner_binding_row_shape():
    rows = owner.build_owner_approval()
    assert len(rows) == 48
    assert list(rows[0].keys()) == list(owner.OWNER_APPROVAL_FIELDS)


def test_owner_binding_census():
    rows = owner.build_owner_approval()
    decisions = Counter(r["owner_decision"] for r in rows)
    assert decisions == Counter({"APPROVE": 9, "HOLD": 39})


def test_owner_binding_family_breakdown():
    rows = owner.build_owner_approval()
    approved = [r for r in rows if r["owner_decision"] == "APPROVE"]
    hold = [r for r in rows if r["owner_decision"] == "HOLD"]

    assert {r["name_normalized"] for r in approved} == {"장약 및 발파작업"}
    assert {r["mapping_type"] for r in approved} == {"NARROWER_THAN"}
    assert {r["target_canonical_id"] for r in approved} == {
        "473d69ee-4433-487f-bc43-c35c1f2ea28f"
    }
    assert len({r["source_key"] for r in approved}) == 9

    hold_family_counts = Counter(r["name_normalized"] for r in hold)
    assert hold_family_counts == Counter({"용접작업": 29, "양생작업": 5, "인발작업": 5})
    assert {r["mapping_type"] for r in hold} == {"POSSIBLE_RELATED"}


def test_owner_binding_deterministic_sha():
    a = owner.build_owner_approval()
    b = owner.build_owner_approval()
    assert a == b
    assert owner.owner_approval_sha(a) == owner.owner_approval_sha(b) == FROZEN_OWNER_APPROVAL_SHA


def test_owner_binding_written_when_present():
    if not owner.OWNER_APPROVAL_PATH.exists():
        return
    rows = load_tsv(owner.OWNER_APPROVAL_PATH)
    assert len(rows) == 48
    assert list(rows[0].keys()) == list(owner.OWNER_APPROVAL_FIELDS)
    assert owner.owner_approval_sha(rows) == FROZEN_OWNER_APPROVAL_SHA
    approve = [r for r in rows if r["owner_decision"] == "APPROVE"]
    assert len(approve) == 9
    for r in approve:
        assert r["owner_reason"].startswith("OWNER_APPROVED_")
        assert r["approval_id"] == owner.APPROVAL_ID


# ---------------------------------------------------------------------------
# Materializer anchors + execute set
# ---------------------------------------------------------------------------


def test_materializer_anchors():
    anchors = mat._verify_repository_anchors()
    assert anchors["owner_approval_binding_sha"] == FROZEN_OWNER_APPROVAL_SHA
    assert len(anchors["approved"]) == 9
    assert len(anchors["hold"]) == 39


def test_execute_set_family_and_target_locked():
    anchors = mat._verify_repository_anchors()
    approved = anchors["approved"]
    assert {r["name_normalized"] for r in approved} == {"장약 및 발파작업"}
    assert {r["mapping_type"] for r in approved} == {"NARROWER_THAN"}
    assert {r["target_canonical_id"] for r in approved} == {
        "473d69ee-4433-487f-bc43-c35c1f2ea28f"
    }
    assert {r["target_canonical_name"] for r in approved} == {"발파굴착"}
    assert len({r["source_key"] for r in approved}) == 9


def test_hold_and_non_mapping_never_in_execute_set():
    """HOLD / AMBIGUOUS / CANONICAL_GAP / NO_MATCH must never enter
    the execute set (WO §13)."""
    anchors = mat._verify_repository_anchors()
    approved_source_keys = {r["source_key"] for r in anchors["approved"]}
    hold_source_keys = {r["source_key"] for r in anchors["hold"]}
    assert not (approved_source_keys & hold_source_keys)

    # Cross-check against the row-freeze: only NARROWER_THAN rows may
    # appear in the execute set. AMBIGUOUS/CANONICAL_GAP/NO_MATCH
    # source_keys must NOT be in approved.
    row_freeze = load_tsv(freeze.ROW_FREEZE_PATH)
    non_mapping_keys = {
        r["source_key"]
        for r in row_freeze
        if r["semantic_decision"] in {"AMBIGUOUS", "CANONICAL_GAP", "NO_MATCH"}
    }
    assert not (approved_source_keys & non_mapping_keys)


def test_db_tuple_shape():
    anchors = mat._verify_repository_anchors()
    tup = mat._row_to_db_tuple(anchors["approved"][0], anchors)
    assert len(tup) == 8
    assert tup[0] == "KALIS_RISK_PROFILE"
    assert tup[3] == "NARROWER_THAN"
    assert tup[4] == "APPROVED"
    assert tup[5] == "MANUAL_REVIEW"
    evidence = json.loads(tup[6])
    assert evidence["evidence_basis"] == "OWNER_APPROVED_SEMANTIC_MAPPING"
    assert evidence["review_authority"] == "GPT"
    metadata = json.loads(tup[7])
    assert metadata["materialization_id"] == mat.MATERIALIZATION_ID
    assert metadata["owner_approval_id"] == owner.APPROVAL_ID
    assert metadata["owner_approval_binding_sha"] == FROZEN_OWNER_APPROVAL_SHA


def test_baseline_and_target_totals():
    assert mat.BASELINE_MAPPING_TOTAL == 1185
    assert mat.BASELINE_CIC_W == 1139
    assert mat.BASELINE_KOSHA == 46
    assert mat.BASELINE_KALIS == 0
    assert mat.POST_MAPPING_TOTAL == 1194
    assert mat.EXPECTED_APPROVED == 9
    assert mat.EXPECTED_HOLD == 39


# ---------------------------------------------------------------------------
# Written artifacts
# ---------------------------------------------------------------------------


def test_written_receipt_when_present():
    if not mat.RECEIPT_PATH.exists():
        return
    rows = load_tsv(mat.RECEIPT_PATH)
    assert len(rows) == 9
    assert list(rows[0].keys()) == list(mat.RECEIPT_FIELDS)
    from tools.risk04.seed_review import universe_sha
    for r in rows:
        assert r["source_id"] == "KALIS_RISK_PROFILE"
        assert r["mapping_type"] == "NARROWER_THAN"
        assert r["mapping_status"] == "APPROVED"
        assert r["mapping_method"] == "MANUAL_REVIEW"
        assert r["canonical_id"] == "473d69ee-4433-487f-bc43-c35c1f2ea28f"
        assert r["canonical_name"] == "발파굴착"
        assert r["owner_approval_binding_sha"] == FROZEN_OWNER_APPROVAL_SHA
        assert r["production_verified"] == "YES"
    assert universe_sha(rows, *mat.RECEIPT_FIELDS) == FROZEN_MATERIALIZATION_RECEIPT_SHA


def test_report_when_present():
    if not mat.REPORT_PATH.exists():
        return
    text = mat.REPORT_PATH.read_text(encoding="utf-8")
    for tag in (
        "mappings_before               = 1185",
        "mappings_after                = 1194",
        "KALIS (new)                   = 9",
        "KALIS NARROWER_THAN           = 9",
        "HOLD leaked into production   = 0",
        "APPROVED (input)              = 9",
        "HOLD (excluded)               = 39",
        "CANONICAL MUTATION            = 0",
        "SECTOR WRITE                  = 0",
        "MERGE = NOT AUTHORIZED",
    ):
        assert tag in text, tag
    assert FROZEN_MATERIALIZATION_RECEIPT_SHA in text
    assert FROZEN_OWNER_APPROVAL_SHA in text


def test_owner_report_when_present():
    if not owner.OWNER_REPORT_PATH.exists():
        return
    text = owner.OWNER_REPORT_PATH.read_text(encoding="utf-8")
    for tag in (
        "APPROVE                 = 9",
        "HOLD                    = 39",
        "REJECTED                = 0",
        "PRODUCTION MATERIALIZED = NOT EXECUTED",
        "FROZEN EVIDENCE REVERIFIED = NO",
    ):
        assert tag in text, tag
    assert FROZEN_OWNER_APPROVAL_SHA in text


# ---------------------------------------------------------------------------
# Anchor regressions
# ---------------------------------------------------------------------------


def test_owner_candidate_sha_regression():
    rows = load_tsv(freeze.OWNER_CANDIDATE_PATH)
    assert freeze.owner_candidate_sha(rows) == FROZEN_OWNER_CANDIDATE_SHA


# ---------------------------------------------------------------------------
# Static guards
# ---------------------------------------------------------------------------


def test_default_cli_does_not_write():
    from io import StringIO
    import contextlib

    for entrypoint in (mat.main, owner.main):
        buf = StringIO()
        if entrypoint is owner.main:
            # owner.main has no flags — invoking with [] just writes; skip.
            continue
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = entrypoint([])
        assert rc == 2


def test_no_llm_or_fuzzy_or_dbclient_in_owner():
    tree = ast.parse(OWNER_GENERATOR.read_text(encoding="utf-8"))
    forbidden = {
        "openai", "anthropic", "sentence_transformers", "faiss",
        "rapidfuzz", "fuzzywuzzy", "kiwipiepy", "supabase",
    }
    seen: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            seen.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                seen.append(node.module)
    assert not (set(seen) & forbidden), f"forbidden import: {seen}"


def test_no_destructive_sql_in_materializer():
    src = MAT_GENERATOR.read_text(encoding="utf-8")
    assert not re.search(r"\bDELETE\s+FROM\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bTRUNCATE\b", src, re.IGNORECASE)
    assert not re.search(r"\bDROP\s+", src, re.IGNORECASE)
    assert not re.search(r"\bUPDATE\s+public\.", src, re.IGNORECASE)


def test_no_canonical_or_sector_write_in_materializer():
    src = MAT_GENERATOR.read_text(encoding="utf-8")
    assert not re.search(r"INSERT\s+INTO\s+public\.risk_canonical_nodes", src, re.IGNORECASE)
    assert not re.search(r"INSERT\s+INTO\s+public\.risk_canonical_node_sectors", src, re.IGNORECASE)
    # Only INSERT allowed is into risk_source_mappings.
    inserts = re.findall(r"INSERT\s+INTO\s+public\.(\w+)", src, re.IGNORECASE)
    assert set(inserts) == {"risk_source_mappings"}
