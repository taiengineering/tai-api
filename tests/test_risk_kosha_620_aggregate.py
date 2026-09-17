"""WO-RISK-KOSHA-AGGREGATE-001 KOSHA 620 aggregate consistency tests.

Lean scope per WO §12: row counts, census, target integrity, prior-batch
SHA regression, deterministic aggregate SHA, and no LLM / production DB
surface in the generator. skip = 0.
"""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kosha_620_aggregate as agg

GENERATOR = Path("tools/risk_map/kosha_620_aggregate.py")

FROZEN_AGGREGATE_SHA = (
    "7e99b73204876cfef6c85a198430d14adfd8582b17cc2c7162a0729063aea67d"
)
FROZEN_MAPPING_SHA = (
    "4952310fafda56d620f10a53a4c4faa765c73338157e1992c6d690428e4f869a"
)
FROZEN_AMBIGUOUS_SHA = (
    "4769525cc441028c21f1326f71752479702179462b6560975d6596e8e6403fba"
)
FROZEN_GAP_SHA = (
    "7e0147924851517bb805e1844e6801ffea9b48e2f1da97b5aa3251496d862c66"
)
FROZEN_NO_MATCH_SHA = (
    "adbd594a9ffd5abed1d46d00d25d4883665591aba584ebef4a826ae6824654a0"
)
FROZEN_CONSISTENCY_SHA = (
    "59236636c9169b28ad920be5f10a7faf31bd2e43a58ff4278bd5a245fa2fbc97"
)
FROZEN_GAP_GROUPS_SHA = (
    "e506fb08f4959f77ad43fa4d5c93d79739f9035b7bc27b0c0e50f7296ec3f268"
)
FROZEN_NO_MATCH_GROUPS_SHA = (
    "e688c9a0cecd5ac0e007f24ba99d4f07d5e9aedd485d90ea8c4ad9d7230ec66e"
)

FROZEN_CONSISTENCY_EXCEPTION_GROUPS = 4
FROZEN_CANONICAL_GAP_GROUPS = 66
FROZEN_NO_MATCH_GROUPS = 53


def test_aggregate_row_shape_and_partition():
    rows = agg.build_aggregate()
    assert len(rows) == 620
    assert len({r["review_key"] for r in rows}) == 620
    assert len({r["source_key"] for r in rows}) == 620
    assert len({(r["review_key"], r["source_key"]) for r in rows}) == 620
    assert list(rows[0].keys()) == list(agg.AGGREGATE_FIELDS)


def test_aggregate_census():
    rows = agg.build_aggregate()
    census = Counter(
        (r["gpt_semantic_decision"], r["gpt_mapping_type"]) for r in rows
    )
    assert dict(census) == {
        ("MAP_EXISTING_CANONICAL", "EXACT_EQUIVALENT"): 6,
        ("MAP_EXISTING_CANONICAL", "NARROWER_THAN"): 40,
        ("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"): 29,
        ("AMBIGUOUS", "AMBIGUOUS"): 78,
        ("CANONICAL_GAP", ""): 196,
        ("NO_MATCH", "NO_MATCH"): 271,
    }


def test_aggregate_deterministic_sha():
    a = agg.build_aggregate()
    b = agg.build_aggregate()
    assert a == b
    assert agg.aggregate_sha(a) == agg.aggregate_sha(b) == FROZEN_AGGREGATE_SHA


def test_target_integrity():
    rows = agg.build_aggregate()
    valid = {r["canonical_id"] for r in load_tsv(agg.CANONICAL_TASK_REFERENCE_PATH)}
    for r in rows:
        dec = r["gpt_semantic_decision"]
        tgt = r["gpt_target_canonical_id"]
        mtype = r["gpt_mapping_type"]
        if dec == "MAP_EXISTING_CANONICAL":
            assert tgt, r["review_key"]
            assert tgt in valid, (r["review_key"], tgt)
            assert mtype in {"EXACT_EQUIVALENT", "NARROWER_THAN", "POSSIBLE_RELATED"}
        else:
            assert tgt == ""
            if dec == "CANONICAL_GAP":
                assert mtype == ""


def test_written_aggregate_when_present():
    if not agg.AGGREGATE_PATH.exists():
        return
    rows = load_tsv(agg.AGGREGATE_PATH)
    assert len(rows) == 620
    assert list(rows[0].keys()) == list(agg.AGGREGATE_FIELDS)
    assert agg.aggregate_sha(rows) == FROZEN_AGGREGATE_SHA


def test_written_buckets_when_present():
    if agg.MAPPING_PATH.exists():
        rows = load_tsv(agg.MAPPING_PATH)
        assert len(rows) == 75
        assert agg.bucket_sha(rows) == FROZEN_MAPPING_SHA
    if agg.AMBIGUOUS_PATH.exists():
        rows = load_tsv(agg.AMBIGUOUS_PATH)
        assert len(rows) == 78
        assert agg.bucket_sha(rows) == FROZEN_AMBIGUOUS_SHA
    if agg.GAP_PATH.exists():
        rows = load_tsv(agg.GAP_PATH)
        assert len(rows) == 196
        assert agg.bucket_sha(rows) == FROZEN_GAP_SHA
    if agg.NO_MATCH_PATH.exists():
        rows = load_tsv(agg.NO_MATCH_PATH)
        assert len(rows) == 271
        assert agg.bucket_sha(rows) == FROZEN_NO_MATCH_SHA


def test_written_consistency_when_present():
    if not agg.CONSISTENCY_PATH.exists():
        return
    rows = load_tsv(agg.CONSISTENCY_PATH)
    assert len(rows) == FROZEN_CONSISTENCY_EXCEPTION_GROUPS
    assert list(rows[0].keys()) == list(agg.CONSISTENCY_FIELDS)
    assert agg.consistency_sha(rows) == FROZEN_CONSISTENCY_SHA
    for r in rows:
        assert int(r["distinct_signatures"]) >= 2
        assert "MULTI_SIGNATURE_REVIEW_REQUIRED" in r["exception_type"]


def test_written_group_files_when_present():
    if agg.GAP_GROUPS_PATH.exists():
        rows = load_tsv(agg.GAP_GROUPS_PATH)
        assert len(rows) == FROZEN_CANONICAL_GAP_GROUPS
        assert list(rows[0].keys()) == list(agg.GAP_GROUP_FIELDS)
        assert agg.gap_group_sha(rows) == FROZEN_GAP_GROUPS_SHA
        # Sum of occurrence_rows must equal the 196 GAP rows.
        assert sum(int(r["occurrence_rows"]) for r in rows) == 196
    if agg.NO_MATCH_GROUPS_PATH.exists():
        rows = load_tsv(agg.NO_MATCH_GROUPS_PATH)
        assert len(rows) == FROZEN_NO_MATCH_GROUPS
        assert list(rows[0].keys()) == list(agg.NO_MATCH_GROUP_FIELDS)
        assert agg.gap_group_sha(rows) == FROZEN_NO_MATCH_GROUPS_SHA
        assert sum(int(r["occurrence_rows"]) for r in rows) == 271


def test_report_when_present():
    if not agg.REPORT_PATH.exists():
        return
    text = agg.REPORT_PATH.read_text(encoding="utf-8")
    for tag in (
        "THIS IS NOT OWNER APPROVAL",
        "THIS IS NOT CANONICAL CREATION",
        "THIS IS NOT PRODUCTION MATERIALIZATION",
        "THIS DOES NOT LIFT KOSHA IDENTITY HOLD",
        "TOTAL KOSHA REVIEWED = 620 / 620",
        "MERGE = NOT AUTHORIZED",
    ):
        assert tag in text
    assert FROZEN_AGGREGATE_SHA in text


# ---------------------------------------------------------------------------
# Prior batch review SHA regression — WO §2
# ---------------------------------------------------------------------------


def test_frozen_batch_shas_regression():
    from tools.risk04.seed_review import universe_sha
    from tools.risk_map.kosha_b01_gpt_review_freeze import DECISION_FIELDS
    for batch_no, review_file, _evidence_file, expected_rows, sha in agg.FROZEN_BATCHES:
        rows = load_tsv(agg._REVIEW_DIR / review_file)
        assert len(rows) == expected_rows, batch_no
        assert universe_sha(rows, *DECISION_FIELDS) == sha, batch_no


# ---------------------------------------------------------------------------
# Static-analysis guard
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


def test_no_production_sql_write_surface():
    src = GENERATOR.read_text(encoding="utf-8")
    assert not re.search(r"\bINSERT\s+INTO\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bUPDATE\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bDELETE\s+FROM\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bTRUNCATE\b", src, re.IGNORECASE)
