"""WO-RISK-KALIS-SEMANTIC-FREEZE-001 lean semantic-freeze tests.

Delta-only per WO §9: verify only what this WO produces. skip = 0.
"""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kalis_map001_semantic_freeze as freeze
from tools.risk_map import kalis_map001_review_universe as rev

GENERATOR = Path("tools/risk_map/kalis_map001_semantic_freeze.py")

FROZEN_FAMILY_FREEZE_SHA = (
    "6d22550751f8d1bd1b6fdc84ae9061dc2ed3df3dc0a246e3377142e7c0291418"
)
FROZEN_ROW_FREEZE_SHA = (
    "ef921c381c15f6b05d3214d4f7e18de33d6374f26d2001162ff5e60a4e7bd4ac"
)
FROZEN_OWNER_CANDIDATE_SHA = (
    "848b896fe46829c53d09e6b7a6af52deacd5ebe66ba021af8a5ca2a799b3052f"
)

FROZEN_REVIEW_UNIVERSE_SHA = (
    "50446a5c9fa421f09beb1425ffe8d90649b29e50bafe93f46d8913a085ed497d"
)
FROZEN_REVIEW_SUMMARY_SHA = (
    "96b5dc4403078e33c325e22265b316dc1ba970aef4ee347e2e9143caae2aa8a0"
)
FROZEN_TASK_UNIVERSE_SHA = (
    "6efd9047b4f6c001321c43496f27c21b538556b76fd2b90a6035cc2972db6ad4"
)


# ---------------------------------------------------------------------------
# Family freeze
# ---------------------------------------------------------------------------


def test_family_freeze_row_count():
    rows = freeze.build_family_freeze()
    assert len(rows) == 40


def test_family_census():
    rows = freeze.build_family_freeze()
    census = Counter(r["semantic_decision"] for r in rows)
    assert dict(census) == {
        "AMBIGUOUS": 21,
        "CANONICAL_GAP": 14,
        "POSSIBLE_RELATED": 3,
        "NARROWER_THAN": 1,
        "NO_MATCH": 1,
    }
    assert sum(1 for r in rows if r["semantic_decision"] == "EXACT_EQUIVALENT") == 0


def test_family_occurrence_sums_to_761():
    rows = freeze.build_family_freeze()
    assert sum(int(r["occurrence_count"]) for r in rows) == 761


def test_family_target_contracts():
    rows = freeze.build_family_freeze()
    mapping_families = {"POSSIBLE_RELATED", "NARROWER_THAN"}
    for r in rows:
        if r["semantic_decision"] in mapping_families:
            assert r["target_canonical_id"]
            assert r["target_canonical_name"]
        else:
            assert not r["target_canonical_id"]
            assert not r["target_canonical_name"]


def test_family_specific_target_bindings():
    """WO §3: exact target bindings for the 4 mapping-candidate families."""
    rows = freeze.build_family_freeze()
    by_name = {r["task_name_normalized"]: r for r in rows}
    assert by_name["용접작업"]["target_canonical_id"] == "bf3841d0-71ea-4464-a7d9-d0dcdc3dfa33"
    assert by_name["용접작업"]["target_canonical_name"] == "궤도현장용접"
    assert by_name["용접작업"]["semantic_decision"] == "POSSIBLE_RELATED"

    assert by_name["양생작업"]["target_canonical_id"] == "3258e587-68ab-40c8-80df-dd4fa0db60b7"
    assert by_name["양생작업"]["target_canonical_name"] == "콘크리트양생"
    assert by_name["양생작업"]["semantic_decision"] == "POSSIBLE_RELATED"

    assert by_name["인발작업"]["target_canonical_id"] == "06e686fc-0062-46af-b4f2-72027b7a4668"
    assert by_name["인발작업"]["target_canonical_name"] == "RockBolt축력및인발측정"
    assert by_name["인발작업"]["semantic_decision"] == "POSSIBLE_RELATED"

    assert by_name["장약 및 발파작업"]["target_canonical_id"] == "473d69ee-4433-487f-bc43-c35c1f2ea28f"
    assert by_name["장약 및 발파작업"]["target_canonical_name"] == "발파굴착"
    assert by_name["장약 및 발파작업"]["semantic_decision"] == "NARROWER_THAN"

    assert by_name["기타"]["semantic_decision"] == "NO_MATCH"
    assert not by_name["기타"]["target_canonical_id"]


# ---------------------------------------------------------------------------
# Row freeze
# ---------------------------------------------------------------------------


def test_row_freeze_row_count_and_uniqueness():
    rows = freeze.build_row_freeze()
    assert len(rows) == 761
    assert len({r["review_key"] for r in rows}) == 761
    assert len({r["source_key"] for r in rows}) == 761
    # review_key ≠ source_key (identity contract lock).
    assert not any(r["review_key"] == r["source_key"] for r in rows)


def test_family_to_row_decision_conservation():
    """Every row's semantic decision must equal its family's."""
    family = {r["family_key"]: r for r in freeze.build_family_freeze()}
    rows = freeze.build_row_freeze()
    for r in rows:
        f = family[r["family_key"]]
        assert r["semantic_decision"] == f["semantic_decision"], r["review_key"]
        assert r["mapping_type"] == f["mapping_type"], r["review_key"]
        assert r["target_canonical_id"] == f["target_canonical_id"], r["review_key"]
        assert r["target_canonical_name"] == f["target_canonical_name"], r["review_key"]
        assert r["owner_default"] == f["owner_default"], r["review_key"]
        assert r["production_candidate"] == f["production_candidate"], r["review_key"]


def test_row_freeze_target_by_decision():
    rows = freeze.build_row_freeze()
    for r in rows:
        d = r["semantic_decision"]
        if d in {"POSSIBLE_RELATED", "NARROWER_THAN"}:
            assert r["target_canonical_id"], r["review_key"]
            assert r["target_canonical_name"], r["review_key"]
        else:
            assert not r["target_canonical_id"], r["review_key"]
            assert not r["target_canonical_name"], r["review_key"]


def test_row_freeze_context_preserved_from_universe():
    universe = {r["review_key"]: r for r in load_tsv(rev.REVIEW_UNIVERSE_PATH)}
    rows = freeze.build_row_freeze()
    for r in rows:
        u = universe[r["review_key"]]
        for f in ("source_key", "family_key", "work_big", "work_mid", "name_raw", "name_normalized", "path_raw"):
            assert r[f] == u[f], (r["review_key"], f)


# ---------------------------------------------------------------------------
# Owner candidate package
# ---------------------------------------------------------------------------


def test_owner_candidates_include_only_possible_and_narrower():
    rows = freeze.build_owner_candidates()
    decisions = Counter(r["semantic_decision"] for r in rows)
    assert set(decisions) == {"POSSIBLE_RELATED", "NARROWER_THAN"}
    for r in rows:
        assert r["owner_decision"] == ""
        assert r["owner_reason"] == ""
        assert r["target_canonical_id"]


def test_owner_candidate_row_sum_matches_family_occurrence():
    rows = freeze.build_owner_candidates()
    family = freeze.build_family_freeze()
    include = {"POSSIBLE_RELATED", "NARROWER_THAN"}
    expected_rows = sum(
        int(f["occurrence_count"]) for f in family if f["semantic_decision"] in include
    )
    assert len(rows) == expected_rows
    # 4 candidate families (WO §6.C).
    assert sum(1 for f in family if f["semantic_decision"] in include) == 4


# ---------------------------------------------------------------------------
# Determinism + written artifacts
# ---------------------------------------------------------------------------


def test_deterministic_shas():
    a = freeze.build_family_freeze()
    b = freeze.build_family_freeze()
    assert a == b
    assert freeze.family_freeze_sha(a) == freeze.family_freeze_sha(b) == FROZEN_FAMILY_FREEZE_SHA

    ra = freeze.build_row_freeze()
    rb = freeze.build_row_freeze()
    assert ra == rb
    assert freeze.row_freeze_sha(ra) == freeze.row_freeze_sha(rb) == FROZEN_ROW_FREEZE_SHA

    oa = freeze.build_owner_candidates()
    ob = freeze.build_owner_candidates()
    assert oa == ob
    assert freeze.owner_candidate_sha(oa) == freeze.owner_candidate_sha(ob) == FROZEN_OWNER_CANDIDATE_SHA


def test_written_family_freeze_when_present():
    if not freeze.FAMILY_FREEZE_PATH.exists():
        return
    rows = load_tsv(freeze.FAMILY_FREEZE_PATH)
    assert len(rows) == 40
    assert list(rows[0].keys()) == list(freeze.FAMILY_FREEZE_FIELDS)
    assert freeze.family_freeze_sha(rows) == FROZEN_FAMILY_FREEZE_SHA


def test_written_row_freeze_when_present():
    if not freeze.ROW_FREEZE_PATH.exists():
        return
    rows = load_tsv(freeze.ROW_FREEZE_PATH)
    assert len(rows) == 761
    assert list(rows[0].keys()) == list(freeze.ROW_FREEZE_FIELDS)
    assert freeze.row_freeze_sha(rows) == FROZEN_ROW_FREEZE_SHA


def test_written_owner_candidates_when_present():
    if not freeze.OWNER_CANDIDATE_PATH.exists():
        return
    rows = load_tsv(freeze.OWNER_CANDIDATE_PATH)
    assert list(rows[0].keys()) == list(freeze.OWNER_CANDIDATE_FIELDS)
    assert freeze.owner_candidate_sha(rows) == FROZEN_OWNER_CANDIDATE_SHA
    for r in rows:
        assert r["owner_decision"] == ""
        assert r["owner_reason"] == ""


def test_report_when_present():
    if not freeze.REPORT_PATH.exists():
        return
    text = freeze.REPORT_PATH.read_text(encoding="utf-8")
    for tag in (
        "THIS IS NOT OWNER APPROVAL",
        "THIS IS NOT PRODUCTION MAPPING",
        "AMBIGUOUS          = 21",
        "CANONICAL_GAP      = 14",
        "POSSIBLE_RELATED   = 3",
        "NARROWER_THAN      = 1",
        "NO_MATCH           = 1",
        "EXACT_EQUIVALENT   = 0",
        "KALIS PRODUCTION MAPPING = 0",
        "MERGE = NOT AUTHORIZED",
    ):
        assert tag in text
    assert FROZEN_FAMILY_FREEZE_SHA in text
    assert FROZEN_ROW_FREEZE_SHA in text
    assert FROZEN_OWNER_CANDIDATE_SHA in text


# ---------------------------------------------------------------------------
# Anchor regression — R1 SHAs must remain untouched
# ---------------------------------------------------------------------------


def test_r1_anchors_unchanged():
    assert freeze.FROZEN_REVIEW_UNIVERSE_SHA == FROZEN_REVIEW_UNIVERSE_SHA
    assert freeze.FROZEN_REVIEW_SUMMARY_SHA == FROZEN_REVIEW_SUMMARY_SHA
    assert freeze.FROZEN_TASK_UNIVERSE_SHA == FROZEN_TASK_UNIVERSE_SHA


# ---------------------------------------------------------------------------
# Static guards
# ---------------------------------------------------------------------------


def test_no_llm_or_fuzzy_or_dbclient():
    tree = ast.parse(GENERATOR.read_text(encoding="utf-8"))
    forbidden = {
        "openai",
        "anthropic",
        "sentence_transformers",
        "faiss",
        "rapidfuzz",
        "fuzzywuzzy",
        "kiwipiepy",
        "psycopg2",
        "psycopg",
        "supabase",
    }
    seen: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            seen.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                seen.append(node.module)
    assert not (set(seen) & forbidden), f"forbidden import: {seen}"


def test_no_production_write_surface():
    src = GENERATOR.read_text(encoding="utf-8")
    assert not re.search(r"\bINSERT\s+INTO\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bUPDATE\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bDELETE\s+FROM\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bTRUNCATE\b", src, re.IGNORECASE)
    assert "DATABASE_URL" not in src
