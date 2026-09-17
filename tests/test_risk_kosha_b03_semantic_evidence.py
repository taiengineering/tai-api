"""WO-RISK-KOSHA-B03-EVIDENCE-001 B03 mechanical evidence + B01/B02 regression."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kosha_b01_semantic_evidence as b01
from tools.risk_map import kosha_b02_semantic_evidence as b02
from tools.risk_map import kosha_b03_semantic_evidence as b03

GENERATOR = Path("tools/risk_map/kosha_b03_semantic_evidence.py")
EVIDENCE_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B03_SEMANTIC_EVIDENCE_v1.tsv")
REPORT_MD = Path("docs/knowledge/risk/OBJ_risk-kosha-b03-semantic-evidence_v1.md")

FROZEN_B03_EVIDENCE_SHA = (
    "22214590663745d75223bcaec284c8f28c0339345703958839952331e1817895"
)
FROZEN_B02_EVIDENCE_SHA = (
    "402fafe9e1026838ffd0c2fb15b6b685b3554c15aa07999329a6c073752f71dd"
)
FROZEN_B01_EVIDENCE_SHA = (
    "bfa75ed7cb87368f9b0744188bd07ac87a495d641945e0e731565fda6517fde8"
)
FROZEN_B01_GPT_REVIEW_SHA = (
    "4b39776f3404f100a182fa23727c74f5cb239036b78ac25d99c82b46662f8bfd"
)
FROZEN_B02_GPT_REVIEW_SHA = (
    "59dbdf26645b536aac2cd16b3cdaac477de29be793aa3d0a2c209b210e20b787"
)


def test_expected_constants():
    assert b03.BATCH_ID == "B03"
    assert b03.EXPECTED_B03_ROWS == 100
    assert b03.EXPECTED_B03_EXACT_NAME == 0
    assert b03.EXPECTED_B03_SEMANTIC_SEARCH == 100
    assert b03.B03_EVIDENCE_FIELDS == b01.B01_EVIDENCE_FIELDS
    assert b03.B03_EVIDENCE_FIELDS == b02.B02_EVIDENCE_FIELDS


def test_b03_uses_shared_batch_helper():
    src = GENERATOR.read_text(encoding="utf-8")
    assert "from tools.risk_map.kosha_b01_semantic_evidence import" in src
    assert "build_batch_evidence" in src
    # B03 must NOT redefine scoring functions.
    assert "_score_candidate" not in src
    assert "_canonical_index" not in src


def test_b03_deterministic_and_shape():
    rows_a, ref_a = b03.build_b03_evidence()
    rows_b, ref_b = b03.build_b03_evidence()
    assert rows_a == rows_b
    assert ref_a == ref_b
    assert b03.b03_evidence_sha(rows_a) == b03.b03_evidence_sha(rows_b) == FROZEN_B03_EVIDENCE_SHA
    assert len(rows_a) == 100
    assert len({r["review_key"] for r in rows_a}) == 100
    assert len({r["source_key"] for r in rows_a}) == 100


def test_b03_composition_is_all_semantic_search():
    rows, _ = b03.build_b03_evidence()
    assert all(r["candidate_class"] == "SEMANTIC_SEARCH_REQUIRED" for r in rows)
    assert all(r["exact_name_hit_count"] == "0" for r in rows)
    assert all(r["exact_name_canonical_id"] == "" for r in rows)


def test_b03_gpt_decision_fields_blank():
    rows, _ = b03.build_b03_evidence()
    for r in rows:
        assert r["gpt_semantic_decision"] == ""
        assert r["gpt_target_canonical_id"] == ""
        assert r["gpt_mapping_type"] == ""
        assert r["gpt_reason"] == ""
        assert r["gpt_confidence_class"] == ""


def test_b03_candidates_are_tasks_and_capped():
    rows, ref = b03.build_b03_evidence()
    valid = {r["canonical_id"] for r in ref}
    for r in rows:
        n = int(r["mechanical_candidate_count"])
        assert 0 <= n <= b03.CANDIDATE_CAP
        prev_score = float("inf")
        for i in range(1, b03.CANDIDATE_CAP + 1):
            score_s = r.get(f"candidate_{i}_mechanical_score", "")
            if not score_s:
                continue
            score = int(score_s)
            assert score > 0
            assert score <= prev_score
            prev_score = score
            can_id = r.get(f"candidate_{i}_canonical_id", "")
            assert can_id in valid, f"unknown canonical {can_id}"


def test_b03_no_premature_decisions():
    rows, _ = b03.build_b03_evidence()
    forbidden = {"EXACT_EQUIVALENT", "APPROVED", "NO_MATCH", "CANONICAL_GAP", "AMBIGUOUS"}
    for r in rows:
        assert r["gpt_semantic_decision"] not in forbidden
        assert r["gpt_mapping_type"] not in forbidden


def test_b03_source_side_columns_preserved_from_pack():
    from tools.risk_map.kosha_map001_review_universe import GPT_REVIEW_PACK_PATH
    pack = [r for r in load_tsv(GPT_REVIEW_PACK_PATH) if r["batch_no"] == "B03"]
    by_key = {r["review_key"]: r for r in pack}
    assert len(by_key) == 100
    rows, _ = b03.build_b03_evidence()
    preserved = (
        "review_key",
        "source_key",
        "project_kind",
        "work_type",
        "detail_process",
        "source_name",
        "source_name_normalized",
        "source_path",
        "source_path_normalized",
        "source_occurrence_count",
        "duplicate_occurrence_flag",
        "candidate_class",
        "exact_name_hit_count",
        "exact_name_canonical_id",
    )
    for r in rows:
        original = by_key[r["review_key"]]
        for f in preserved:
            assert r[f] == original[f], f


# ---------------------------------------------------------------------------
# B01/B02 regression — must survive B03 addition unchanged.
# ---------------------------------------------------------------------------


def test_b01_semantic_evidence_sha_regression():
    rows, _ = b01.build_b01_evidence()
    assert b01.b01_evidence_sha(rows) == FROZEN_B01_EVIDENCE_SHA


def test_b02_semantic_evidence_sha_regression():
    rows, _ = b02.build_b02_evidence()
    assert b02.b02_evidence_sha(rows) == FROZEN_B02_EVIDENCE_SHA


def test_b01_and_b02_gpt_review_files_unchanged():
    from tools.risk04.seed_review import universe_sha
    from tools.risk_map.kosha_b01_gpt_review_freeze import DECISION_FIELDS
    b01_review = load_tsv(
        Path("docs/knowledge/risk/RISK_KOSHA_B01_GPT_SEMANTIC_REVIEW_v1.tsv")
    )
    b02_review = load_tsv(
        Path("docs/knowledge/risk/RISK_KOSHA_B02_GPT_SEMANTIC_REVIEW_v1.tsv")
    )
    assert len(b01_review) == 100
    assert len(b02_review) == 100
    assert universe_sha(b01_review, *DECISION_FIELDS) == FROZEN_B01_GPT_REVIEW_SHA
    assert universe_sha(b02_review, *DECISION_FIELDS) == FROZEN_B02_GPT_REVIEW_SHA


# ---------------------------------------------------------------------------
# Written artifact assertions
# ---------------------------------------------------------------------------


def test_written_b03_evidence_when_present():
    if not EVIDENCE_TSV.exists():
        return
    rows = load_tsv(EVIDENCE_TSV)
    assert len(rows) == 100
    assert list(rows[0].keys()) == list(b03.B03_EVIDENCE_FIELDS)
    assert b03.b03_evidence_sha(rows) == FROZEN_B03_EVIDENCE_SHA


def test_report_when_present():
    if not REPORT_MD.exists():
        return
    text = REPORT_MD.read_text(encoding="utf-8")
    for tag in (
        "THIS IS MECHANICAL EVIDENCE ONLY",
        "THIS IS NOT GPT SEMANTIC REVIEW",
        "THIS IS NOT OWNER MAPPING APPROVAL",
        "THIS IS NOT PRODUCTION MATERIALIZATION",
        "THIS DOES NOT LIFT KOSHA IDENTITY HOLD",
        "ZERO MECHANICAL CANDIDATES != NO_MATCH",
    ):
        assert tag in text
    assert FROZEN_B03_EVIDENCE_SHA in text
    assert "MERGE = NOT AUTHORIZED" in text


# ---------------------------------------------------------------------------
# Static-analysis guard
# ---------------------------------------------------------------------------


def test_no_llm_or_fuzzy_or_dbclient_imports():
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
