"""WO-RISK-KOSHA-B02-EVIDENCE-001 B02 mechanical evidence contract + B01 regression."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kosha_b01_semantic_evidence as b01
from tools.risk_map import kosha_b02_semantic_evidence as b02

GENERATOR = Path("tools/risk_map/kosha_b02_semantic_evidence.py")
EVIDENCE_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B02_SEMANTIC_EVIDENCE_v1.tsv")
REPORT_MD = Path("docs/knowledge/risk/OBJ_risk-kosha-b02-semantic-evidence_v1.md")

FROZEN_B02_EVIDENCE_SHA = (
    "402fafe9e1026838ffd0c2fb15b6b685b3554c15aa07999329a6c073752f71dd"
)
FROZEN_B01_EVIDENCE_SHA = (
    "bfa75ed7cb87368f9b0744188bd07ac87a495d641945e0e731565fda6517fde8"
)
FROZEN_B01_GPT_REVIEW_SHA = (
    "4b39776f3404f100a182fa23727c74f5cb239036b78ac25d99c82b46662f8bfd"
)


def test_expected_constants():
    assert b02.BATCH_ID == "B02"
    assert b02.EXPECTED_B02_ROWS == 100
    assert b02.EXPECTED_B02_EXACT_NAME == 0
    assert b02.EXPECTED_B02_SEMANTIC_SEARCH == 100
    assert b02.B02_EVIDENCE_FIELDS == b01.B01_EVIDENCE_FIELDS


def test_b02_uses_shared_batch_helper():
    """§10: one deterministic retrieval implementation, thin batch wrapper."""
    src = GENERATOR.read_text(encoding="utf-8")
    assert "from tools.risk_map.kosha_b01_semantic_evidence import" in src
    assert "build_batch_evidence" in src
    # B02 must NOT redefine scoring functions.
    assert "_score_candidate" not in src
    assert "_canonical_index" not in src


def test_b02_deterministic_and_shape():
    rows_a, ref_a = b02.build_b02_evidence()
    rows_b, ref_b = b02.build_b02_evidence()
    assert rows_a == rows_b
    assert ref_a == ref_b
    assert b02.b02_evidence_sha(rows_a) == b02.b02_evidence_sha(rows_b) == FROZEN_B02_EVIDENCE_SHA
    assert len(rows_a) == 100
    assert len({r["review_key"] for r in rows_a}) == 100
    assert len({r["source_key"] for r in rows_a}) == 100


def test_b02_composition_is_all_semantic_search():
    # source_id is enforced by load_gpt_pack_batch on the pack itself (scope
    # guard). The emitted evidence schema mirrors B01 and omits source_id.
    rows, _ = b02.build_b02_evidence()
    assert all(r["candidate_class"] == "SEMANTIC_SEARCH_REQUIRED" for r in rows)
    assert all(r["exact_name_hit_count"] == "0" for r in rows)
    assert all(r["exact_name_canonical_id"] == "" for r in rows)


def test_b02_gpt_decision_fields_blank():
    rows, _ = b02.build_b02_evidence()
    for r in rows:
        assert r["gpt_semantic_decision"] == ""
        assert r["gpt_target_canonical_id"] == ""
        assert r["gpt_mapping_type"] == ""
        assert r["gpt_reason"] == ""
        assert r["gpt_confidence_class"] == ""


def test_b02_candidates_are_tasks_and_capped():
    rows, ref = b02.build_b02_evidence()
    valid = {r["canonical_id"] for r in ref}
    for r in rows:
        n = int(r["mechanical_candidate_count"])
        assert 0 <= n <= b02.CANDIDATE_CAP
        # sort order & no zero-scored candidates
        prev_score = float("inf")
        for i in range(1, b02.CANDIDATE_CAP + 1):
            score_s = r.get(f"candidate_{i}_mechanical_score", "")
            if not score_s:
                continue
            score = int(score_s)
            assert score > 0
            assert score <= prev_score
            prev_score = score
            can_id = r.get(f"candidate_{i}_canonical_id", "")
            assert can_id in valid, f"unknown canonical {can_id}"


def test_b02_no_premature_decisions():
    rows, _ = b02.build_b02_evidence()
    forbidden = {"EXACT_EQUIVALENT", "APPROVED", "NO_MATCH", "CANONICAL_GAP", "AMBIGUOUS"}
    for r in rows:
        assert r["gpt_semantic_decision"] not in forbidden
        assert r["gpt_mapping_type"] not in forbidden


# ---------------------------------------------------------------------------
# B01 regression — refactor must not drift the B01 SHAs.
# ---------------------------------------------------------------------------


def test_b01_semantic_evidence_sha_regression():
    rows, _ = b01.build_b01_evidence()
    assert len(rows) == 100
    assert b01.b01_evidence_sha(rows) == FROZEN_B01_EVIDENCE_SHA


def test_b01_canonical_task_reference_sha_regression():
    _, ref = b01.build_b01_evidence()
    assert len(ref) == 554
    assert b01.canonical_task_reference_sha(ref) == b01.FROZEN_CANONICAL_TASK_REFERENCE_SHA if hasattr(b01, "FROZEN_CANONICAL_TASK_REFERENCE_SHA") else (
        b01.canonical_task_reference_sha(ref)
        == "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
    )


def test_b01_frozen_evidence_and_gpt_review_files_unchanged():
    b01_ev = load_tsv(b01.B01_EVIDENCE_PATH)
    assert b01.b01_evidence_sha(b01_ev) == FROZEN_B01_EVIDENCE_SHA
    gpt_review_path = Path(
        "docs/knowledge/risk/RISK_KOSHA_B01_GPT_SEMANTIC_REVIEW_v1.tsv"
    )
    from tools.risk_map.kosha_b01_gpt_review_freeze import DECISION_FIELDS
    gpt_rows = load_tsv(gpt_review_path)
    assert len(gpt_rows) == 100
    from tools.risk04.seed_review import universe_sha
    assert universe_sha(gpt_rows, *DECISION_FIELDS) == FROZEN_B01_GPT_REVIEW_SHA


# ---------------------------------------------------------------------------
# Written artifact assertions
# ---------------------------------------------------------------------------


def test_written_b02_evidence_when_present():
    if not EVIDENCE_TSV.exists():
        return
    rows = load_tsv(EVIDENCE_TSV)
    assert len(rows) == 100
    assert list(rows[0].keys()) == list(b02.B02_EVIDENCE_FIELDS)
    assert b02.b02_evidence_sha(rows) == FROZEN_B02_EVIDENCE_SHA


def test_report_when_present():
    if not REPORT_MD.exists():
        return
    text = REPORT_MD.read_text(encoding="utf-8")
    for tag in (
        "THIS IS MECHANICAL EVIDENCE ONLY",
        "THIS IS NOT GPT SEMANTIC REVIEW",
        "THIS IS NOT MAPPING APPROVAL",
        "THIS IS NOT PRODUCTION MATERIALIZATION",
        "THIS DOES NOT LIFT KOSHA IDENTITY HOLD",
        "ZERO MECHANICAL CANDIDATES != NO_MATCH",
    ):
        assert tag in text
    assert FROZEN_B02_EVIDENCE_SHA in text
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


def test_b02_source_side_columns_preserved_from_pack():
    from tools.risk_map.kosha_map001_review_universe import GPT_REVIEW_PACK_PATH
    pack = [r for r in load_tsv(GPT_REVIEW_PACK_PATH) if r["batch_no"] == "B02"]
    by_key = {r["review_key"]: r for r in pack}
    assert len(by_key) == 100
    rows, _ = b02.build_b02_evidence()
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
