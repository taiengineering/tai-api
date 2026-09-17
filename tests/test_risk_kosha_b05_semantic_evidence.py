"""WO-RISK-KOSHA-B05-EVIDENCE-001 B05 mechanical evidence + B01-B04 regression."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kosha_b01_semantic_evidence as b01
from tools.risk_map import kosha_b02_semantic_evidence as b02
from tools.risk_map import kosha_b03_semantic_evidence as b03
from tools.risk_map import kosha_b04_semantic_evidence as b04
from tools.risk_map import kosha_b05_semantic_evidence as b05
from tools.risk_map.kosha_map001_review_universe import GPT_REVIEW_PACK_PATH

GENERATOR = Path("tools/risk_map/kosha_b05_semantic_evidence.py")
EVIDENCE_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B05_SEMANTIC_EVIDENCE_v1.tsv")
REPORT_MD = Path("docs/knowledge/risk/OBJ_risk-kosha-b05-semantic-evidence_v1.md")

FROZEN_B05_EVIDENCE_SHA = (
    "67a0a8a09af59772c61cad93af3b2dd3fcf818dfde794e972ea0c74fb0fc3ed0"
)
FROZEN_B04_EVIDENCE_SHA = (
    "c44be9c0edac197b175e84a2647497747a636ad71b27dfaa8308492a4616014a"
)
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
FROZEN_B03_GPT_REVIEW_SHA = (
    "4dda24f4d3c930249e23c36f3062117cde3063f5182a7fa7a08d1d9fa1e69885"
)
FROZEN_B04_GPT_REVIEW_SHA = (
    "5d76544dae6c2f509a842baf8f8d394db339d62ffb3f9b6789091f637856815b"
)


def test_expected_constants():
    assert b05.BATCH_ID == "B05"
    assert b05.EXPECTED_B05_ROWS == 100
    assert b05.EXPECTED_B05_EXACT_NAME == 0
    assert b05.EXPECTED_B05_SEMANTIC_SEARCH == 100
    assert b05.B05_EVIDENCE_FIELDS == b01.B01_EVIDENCE_FIELDS


def test_b05_uses_shared_batch_helper():
    src = GENERATOR.read_text(encoding="utf-8")
    assert "from tools.risk_map.kosha_b01_semantic_evidence import" in src
    assert "build_batch_evidence" in src
    assert "_score_candidate" not in src
    assert "_canonical_index" not in src


def test_b05_deterministic_and_shape():
    rows_a, ref_a = b05.build_b05_evidence()
    rows_b, ref_b = b05.build_b05_evidence()
    assert rows_a == rows_b
    assert ref_a == ref_b
    assert b05.b05_evidence_sha(rows_a) == b05.b05_evidence_sha(rows_b) == FROZEN_B05_EVIDENCE_SHA
    assert len(rows_a) == 100
    assert len({r["review_key"] for r in rows_a}) == 100
    assert len({r["source_key"] for r in rows_a}) == 100


def test_b05_composition_is_all_semantic_search():
    rows, _ = b05.build_b05_evidence()
    assert all(r["candidate_class"] == "SEMANTIC_SEARCH_REQUIRED" for r in rows)
    assert all(r["exact_name_hit_count"] == "0" for r in rows)
    assert all(r["exact_name_canonical_id"] == "" for r in rows)


def test_b05_gpt_decision_fields_blank():
    rows, _ = b05.build_b05_evidence()
    for r in rows:
        assert r["gpt_semantic_decision"] == ""
        assert r["gpt_target_canonical_id"] == ""
        assert r["gpt_mapping_type"] == ""
        assert r["gpt_reason"] == ""
        assert r["gpt_confidence_class"] == ""


def test_b05_candidates_are_tasks_and_capped():
    rows, ref = b05.build_b05_evidence()
    valid = {r["canonical_id"] for r in ref}
    for r in rows:
        n = int(r["mechanical_candidate_count"])
        assert 0 <= n <= b05.CANDIDATE_CAP
        prev_score = float("inf")
        for i in range(1, b05.CANDIDATE_CAP + 1):
            score_s = r.get(f"candidate_{i}_mechanical_score", "")
            if not score_s:
                continue
            score = int(score_s)
            assert score > 0
            assert score <= prev_score
            prev_score = score
            can_id = r.get(f"candidate_{i}_canonical_id", "")
            assert can_id in valid, f"unknown canonical {can_id}"


def test_b05_no_premature_decisions():
    rows, _ = b05.build_b05_evidence()
    forbidden = {"EXACT_EQUIVALENT", "APPROVED", "NO_MATCH", "CANONICAL_GAP", "AMBIGUOUS"}
    for r in rows:
        assert r["gpt_semantic_decision"] not in forbidden
        assert r["gpt_mapping_type"] not in forbidden


def test_b05_batch_boundary_exact_set_equality():
    """WO §5: B05 evidence source_key set equals frozen review-pack B05 set,
    with zero overlap against B04 and B06."""
    pack = load_tsv(GPT_REVIEW_PACK_PATH)
    b05_pack_keys = {r["source_key"] for r in pack if r["batch_no"] == "B05"}
    b04_pack_keys = {r["source_key"] for r in pack if r["batch_no"] == "B04"}
    b06_pack_keys = {r["source_key"] for r in pack if r["batch_no"] == "B06"}
    rows, _ = b05.build_b05_evidence()
    ev_keys = {r["source_key"] for r in rows}
    assert ev_keys == b05_pack_keys
    assert not (ev_keys & b04_pack_keys)
    assert not (ev_keys & b06_pack_keys)


def test_b05_source_side_columns_preserved_from_pack():
    pack = [r for r in load_tsv(GPT_REVIEW_PACK_PATH) if r["batch_no"] == "B05"]
    by_key = {r["review_key"]: r for r in pack}
    assert len(by_key) == 100
    rows, _ = b05.build_b05_evidence()
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
# B01-B04 regression — must survive B05 addition unchanged.
# ---------------------------------------------------------------------------


def test_b01_semantic_evidence_sha_regression():
    rows, _ = b01.build_b01_evidence()
    assert b01.b01_evidence_sha(rows) == FROZEN_B01_EVIDENCE_SHA


def test_b02_semantic_evidence_sha_regression():
    rows, _ = b02.build_b02_evidence()
    assert b02.b02_evidence_sha(rows) == FROZEN_B02_EVIDENCE_SHA


def test_b03_semantic_evidence_sha_regression():
    rows, _ = b03.build_b03_evidence()
    assert b03.b03_evidence_sha(rows) == FROZEN_B03_EVIDENCE_SHA


def test_b04_semantic_evidence_sha_regression():
    rows, _ = b04.build_b04_evidence()
    assert b04.b04_evidence_sha(rows) == FROZEN_B04_EVIDENCE_SHA


def test_b01_b04_gpt_review_files_unchanged():
    from tools.risk04.seed_review import universe_sha
    from tools.risk_map.kosha_b01_gpt_review_freeze import DECISION_FIELDS
    for path, sha in (
        (Path("docs/knowledge/risk/RISK_KOSHA_B01_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B01_GPT_REVIEW_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B02_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B02_GPT_REVIEW_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B03_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B03_GPT_REVIEW_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B04_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B04_GPT_REVIEW_SHA),
    ):
        rows = load_tsv(path)
        assert universe_sha(rows, *DECISION_FIELDS) == sha, path


# ---------------------------------------------------------------------------
# Written artifact assertions
# ---------------------------------------------------------------------------


def test_written_b05_evidence_when_present():
    if not EVIDENCE_TSV.exists():
        return
    rows = load_tsv(EVIDENCE_TSV)
    assert len(rows) == 100
    assert list(rows[0].keys()) == list(b05.B05_EVIDENCE_FIELDS)
    assert b05.b05_evidence_sha(rows) == FROZEN_B05_EVIDENCE_SHA


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
    assert FROZEN_B05_EVIDENCE_SHA in text
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
