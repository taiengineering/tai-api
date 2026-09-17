"""WO-RISK-KOSHA-B01-EVIDENCE-001 KOSHA B01 semantic evidence contract tests.

CI must run with skip = 0. All inputs are committed repository TSVs, so no
frozen source artifacts are required.
"""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kosha_b01_semantic_evidence as ev

GENERATOR = Path("tools/risk_map/kosha_b01_semantic_evidence.py")
EVIDENCE_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B01_SEMANTIC_EVIDENCE_v1.tsv")
REFERENCE_TSV = Path(
    "docs/knowledge/risk/RISK_KOSHA_B01_CANONICAL_TASK_REFERENCE_v1.tsv"
)
REPORT_MD = Path("docs/knowledge/risk/OBJ_risk-kosha-b01-semantic-evidence_v1.md")

FROZEN_EVIDENCE_SHA = "bfa75ed7cb87368f9b0744188bd07ac87a495d641945e0e731565fda6517fde8"
FROZEN_REFERENCE_SHA = "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
FROZEN_GPT_REVIEW_PACK_SHA = (
    "20bcdf3a7827a2446dae933a1d055463176478cccf86f7ad8c607c23fe29f9b5"
)
FROZEN_CANONICAL_RECEIPT_SHA = (
    "c8c4232bf924b52636c9dc33fb1891473d548e09ed15de35f33764fe18603f3c"
)
FROZEN_CICW_PROPOSAL_SHA = (
    "036d293c6e2fa506922c53ffcfdd44476ec903fdc639e2c12b73815d4401f026"
)
FROZEN_MAP_MATERIALIZATION_RECEIPT_SHA = (
    "8aa2efc056ac9873db108c07bce72ce691308badb7d413cc45cf306c110cc61b"
)


def test_expected_constants():
    assert ev.EXPECTED_B01_ROWS == 100
    assert ev.EXPECTED_EXACT_NAME_ROWS == 12
    assert ev.EXPECTED_SEMANTIC_SEARCH_ROWS == 88
    assert ev.EXPECTED_CANONICAL_TASK_ROWS == 554
    assert ev.CANDIDATE_CAP == 10
    assert ev.SCORE_EXACT_NORMALIZED_NAME == 1000
    assert ev.SCORE_SHARED_NAME_TOKEN == 50


def test_frozen_anchor_shas():
    assert ev.FROZEN_GPT_REVIEW_PACK_SHA == FROZEN_GPT_REVIEW_PACK_SHA
    assert ev.FROZEN_CANONICAL_RECEIPT_SHA == FROZEN_CANONICAL_RECEIPT_SHA
    assert ev.FROZEN_PROPOSAL_SHA == FROZEN_CICW_PROPOSAL_SHA
    assert (
        ev.FROZEN_MAP_MATERIALIZATION_RECEIPT_SHA
        == FROZEN_MAP_MATERIALIZATION_RECEIPT_SHA
    )


def test_generator_deterministic():
    a, ref_a = ev.build_b01_evidence()
    b, ref_b = ev.build_b01_evidence()
    assert a == b
    assert ref_a == ref_b
    assert ev.b01_evidence_sha(a) == ev.b01_evidence_sha(b) == FROZEN_EVIDENCE_SHA
    assert (
        ev.canonical_task_reference_sha(ref_a)
        == ev.canonical_task_reference_sha(ref_b)
        == FROZEN_REFERENCE_SHA
    )


def test_b01_shape():
    rows, ref = ev.build_b01_evidence()
    assert len(rows) == 100
    assert len(ref) == 554
    assert len({r["review_key"] for r in rows}) == 100
    assert len({r["source_key"] for r in rows}) == 100

    exact = sum(1 for r in rows if r["candidate_class"] == "EXACT_NAME_CANDIDATE")
    semantic = sum(
        1 for r in rows if r["candidate_class"] == "SEMANTIC_SEARCH_REQUIRED"
    )
    assert exact == 12
    assert semantic == 88


def test_all_gpt_decision_fields_blank():
    rows, _ = ev.build_b01_evidence()
    for r in rows:
        assert r["gpt_semantic_decision"] == ""
        assert r["gpt_target_canonical_id"] == ""
        assert r["gpt_mapping_type"] == ""
        assert r["gpt_reason"] == ""
        assert r["gpt_confidence_class"] == ""


def test_exact_name_preserved_as_candidate_1():
    """WO §16: exact-name candidates must appear as candidate #1."""
    rows, _ = ev.build_b01_evidence()
    exact = [r for r in rows if r["candidate_class"] == "EXACT_NAME_CANDIDATE"]
    assert len(exact) == 12
    for r in exact:
        assert r["candidate_1_canonical_id"] == r["exact_name_canonical_id"]
        assert "EXACT_NORMALIZED_NAME" in r["candidate_1_reasons"]


def test_candidate_ids_exist_in_reference_and_are_tasks():
    rows, ref = ev.build_b01_evidence()
    valid = {r["canonical_id"] for r in ref}
    for r in rows:
        for i in range(1, ev.CANDIDATE_CAP + 1):
            can_id = r.get(f"candidate_{i}_canonical_id", "")
            if not can_id:
                continue
            assert can_id in valid, (
                f"candidate {can_id} not in canonical TASK reference "
                f"for {r['review_key']}"
            )


def test_no_process_candidates_leaked():
    """Reference catalog is TASK-only, so this is really an anchor sanity check."""
    _, ref = ev.build_b01_evidence()
    # Every reference row corresponds to a TASK in the frozen canonical receipt.
    from tools.risk04.review_decisions import load_tsv
    from tools.risk04.materialize001_resume_effective_plan import RECEIPT_PATH
    receipt = load_tsv(RECEIPT_PATH)
    tasks = {r["canonical_id"] for r in receipt if r["node_kind"] == "TASK"}
    processes = {r["canonical_id"] for r in receipt if r["node_kind"] == "PROCESS"}
    ref_ids = {r["canonical_id"] for r in ref}
    assert ref_ids.issubset(tasks)
    assert not (ref_ids & processes)


def test_candidate_class_and_evidence_state_consistent():
    rows, _ = ev.build_b01_evidence()
    for r in rows:
        n = int(r["mechanical_candidate_count"])
        if n == 0:
            assert r["evidence_state"] == "NO_MECHANICAL_CANDIDATE"
        else:
            assert r["evidence_state"] == "CANDIDATES_FOUND"
            assert 1 <= n <= 10


def test_no_premature_mapping_type_or_decision_ever_written():
    """No evidence row can carry EXACT_EQUIVALENT / APPROVED / NO_MATCH / CANONICAL_GAP
    in any decision field."""
    rows, _ = ev.build_b01_evidence()
    forbidden_decisions = {"EXACT_EQUIVALENT", "APPROVED", "NO_MATCH", "CANONICAL_GAP", "AMBIGUOUS"}
    for r in rows:
        for f in (
            "gpt_semantic_decision",
            "gpt_target_canonical_id",
            "gpt_mapping_type",
            "gpt_reason",
            "gpt_confidence_class",
        ):
            assert r[f] not in forbidden_decisions


def test_written_evidence_when_present():
    if not EVIDENCE_TSV.exists():
        return
    rows = load_tsv(EVIDENCE_TSV)
    assert len(rows) == 100
    assert list(rows[0].keys()) == list(ev.B01_EVIDENCE_FIELDS)
    assert ev.b01_evidence_sha(rows) == FROZEN_EVIDENCE_SHA


def test_written_reference_when_present():
    if not REFERENCE_TSV.exists():
        return
    rows = load_tsv(REFERENCE_TSV)
    assert len(rows) == 554
    assert list(rows[0].keys()) == list(ev.CANONICAL_TASK_REFERENCE_FIELDS)
    assert ev.canonical_task_reference_sha(rows) == FROZEN_REFERENCE_SHA


def test_report_when_present():
    if not REPORT_MD.exists():
        return
    text = REPORT_MD.read_text(encoding="utf-8")
    for tag in (
        "THIS IS EVIDENCE ONLY",
        "THIS IS NOT GPT SEMANTIC DECISION",
        "THIS IS NOT MAPPING APPROVAL",
        "THIS IS NOT PRODUCTION MATERIALIZATION",
        "KOSHA IDENTITY HOLD IS PRESERVED",
    ):
        assert tag in text
    assert FROZEN_EVIDENCE_SHA in text
    assert FROZEN_REFERENCE_SHA in text
    assert FROZEN_GPT_REVIEW_PACK_SHA in text
    assert "MERGE = NOT AUTHORIZED" in text


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
        "kiwi",
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


def test_candidates_sorted_and_capped():
    """WO §15: top-10 sorted by (-score, path, canonical_id). Cap 10."""
    rows, _ = ev.build_b01_evidence()
    for r in rows:
        prev_score = float("inf")
        prev_key = ("", "")
        for i in range(1, ev.CANDIDATE_CAP + 1):
            score_s = r.get(f"candidate_{i}_mechanical_score", "")
            if not score_s:
                continue
            score = int(score_s)
            path = r.get(f"candidate_{i}_path", "")
            cid = r.get(f"candidate_{i}_canonical_id", "")
            # Score never rises going down the list.
            assert score <= prev_score
            if score == prev_score:
                assert (path, cid) >= prev_key
            prev_score = score
            prev_key = (path, cid)


def test_zero_score_candidates_never_written():
    rows, _ = ev.build_b01_evidence()
    for r in rows:
        for i in range(1, ev.CANDIDATE_CAP + 1):
            score_s = r.get(f"candidate_{i}_mechanical_score", "")
            if not score_s:
                continue
            assert int(score_s) > 0


def test_source_side_columns_preserved_exactly():
    """WO §10: source-side columns from B01 pack must be echoed unchanged."""
    from tools.risk_map.kosha_map001_review_universe import GPT_REVIEW_PACK_PATH
    pack = [r for r in load_tsv(GPT_REVIEW_PACK_PATH) if r["batch_no"] == "B01"]
    by_key = {r["review_key"]: r for r in pack}
    rows, _ = ev.build_b01_evidence()
    preserved_fields = (
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
        for f in preserved_fields:
            assert r[f] == original[f], f"field {f} changed for {r['review_key']}"


def test_stopwords_are_documented():
    """Stopwords are declared as an explicit frozen set (WO §13)."""
    assert isinstance(ev.STOPWORDS, frozenset)
    # Currently we do NOT strip any stopword — token overlap is raw.
    assert ev.STOPWORDS == frozenset()
