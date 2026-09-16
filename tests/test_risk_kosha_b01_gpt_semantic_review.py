"""WO-RISK-KOSHA-B01-REVIEW-001 GPT semantic decision freeze tests.

Transcription contract only — no semantic assertions on the reviewer's
judgment. skip = 0 in CI (everything is committed repository evidence).
"""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kosha_b01_gpt_review_freeze as freeze
from tools.risk_map.kosha_b01_semantic_evidence import (
    B01_EVIDENCE_PATH,
    b01_evidence_sha,
)

GENERATOR = Path("tools/risk_map/kosha_b01_gpt_review_freeze.py")
DECISION_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B01_GPT_SEMANTIC_REVIEW_v1.tsv")
CENSUS_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B01_GPT_SEMANTIC_CENSUS_v1.tsv")
REPORT_MD = Path("docs/knowledge/risk/OBJ_risk-kosha-b01-gpt-semantic-review_v1.md")

FROZEN_B01_EVIDENCE_SHA = (
    "bfa75ed7cb87368f9b0744188bd07ac87a495d641945e0e731565fda6517fde8"
)
FROZEN_CANONICAL_TASK_REFERENCE_SHA = (
    "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
)
FROZEN_DECISION_SHA = (
    "4b39776f3404f100a182fa23727c74f5cb239036b78ac25d99c82b46662f8bfd"
)
FROZEN_CENSUS_SHA = (
    "0526eb95dea6892b3493c754c1cff774d5e900c978756d413399cf24e52ad89b"
)


def test_manifest_frozen_size_and_uniqueness():
    assert len(freeze.GPT_DECISIONS) == 100
    # Union of the group lists must be 100 with zero overlap.
    grouped = (
        list(freeze._EXACT_EQUIVALENT_KEYS)
        + list(freeze._AMBIGUOUS_BLASTING_KEYS)
        + [k for k, _, _ in freeze._AMBIGUOUS_OTHER]
        + [k for k, _, _ in freeze._NARROWER_THAN]
        + [k for k, _, _ in freeze._POSSIBLE_RELATED]
        + list(freeze._CANONICAL_GAP_KEYS)
        + list(freeze._NO_MATCH_KEYS)
    )
    assert len(grouped) == 100
    assert len(set(grouped)) == 100


def test_manifest_group_counts():
    assert len(freeze._EXACT_EQUIVALENT_KEYS) == 6
    assert len(freeze._AMBIGUOUS_BLASTING_KEYS) == 6
    assert len(freeze._AMBIGUOUS_OTHER) == 6
    assert len(freeze._NARROWER_THAN) == 3
    assert len(freeze._POSSIBLE_RELATED) == 6
    assert len(freeze._CANONICAL_GAP_KEYS) == 29
    assert len(freeze._NO_MATCH_KEYS) == 44


def test_frozen_input_shas():
    assert freeze.FROZEN_B01_EVIDENCE_SHA == FROZEN_B01_EVIDENCE_SHA
    assert (
        freeze.FROZEN_CANONICAL_TASK_REFERENCE_SHA
        == FROZEN_CANONICAL_TASK_REFERENCE_SHA
    )


def test_manifest_source_set_matches_b01_exactly():
    b01 = load_tsv(B01_EVIDENCE_PATH)
    assert b01_evidence_sha(b01) == FROZEN_B01_EVIDENCE_SHA
    b01_keys = {r["source_key"] for r in b01}
    manifest_keys = set(freeze.GPT_DECISIONS)
    assert b01_keys == manifest_keys, (
        f"missing={b01_keys - manifest_keys} unexpected={manifest_keys - b01_keys}"
    )


def test_decision_rows_deterministic():
    a = freeze.build_decisions()
    b = freeze.build_decisions()
    assert a == b
    assert freeze.decision_sha(a) == freeze.decision_sha(b) == FROZEN_DECISION_SHA


def test_decision_row_shape():
    rows = freeze.build_decisions()
    assert len(rows) == 100
    assert list(rows[0].keys()) == list(freeze.DECISION_FIELDS)
    for r in rows:
        assert r["review_authority"] == "GPT"
        assert r["review_batch"] == "B01"
        assert r["input_evidence_sha"] == FROZEN_B01_EVIDENCE_SHA
        assert r["canonical_reference_sha"] == FROZEN_CANONICAL_TASK_REFERENCE_SHA


def test_census():
    rows = freeze.build_decisions()
    seen = Counter(
        (r["gpt_semantic_decision"], r["gpt_mapping_type"]) for r in rows
    )
    assert dict(seen) == {
        ("MAP_EXISTING_CANONICAL", "EXACT_EQUIVALENT"): 6,
        ("MAP_EXISTING_CANONICAL", "NARROWER_THAN"): 3,
        ("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"): 6,
        ("AMBIGUOUS", "AMBIGUOUS"): 12,
        ("CANONICAL_GAP", ""): 29,
        ("NO_MATCH", "NO_MATCH"): 44,
    }


def test_targeted_and_blank_target_counts():
    rows = freeze.build_decisions()
    targeted = [r for r in rows if r["gpt_target_canonical_id"]]
    blank = [r for r in rows if not r["gpt_target_canonical_id"]]
    assert len(targeted) == 15
    assert len(blank) == 85
    for r in targeted:
        assert r["gpt_target_canonical_name"]
        assert r["gpt_semantic_decision"] == "MAP_EXISTING_CANONICAL"
        assert r["gpt_mapping_type"] in {"EXACT_EQUIVALENT", "NARROWER_THAN", "POSSIBLE_RELATED"}
    for r in blank:
        assert r["gpt_target_canonical_id"] == ""
        assert r["gpt_target_canonical_name"] == ""


def test_targeted_canonical_ids_valid_and_task():
    """15 targeted rows all resolve inside the frozen 554-TASK reference."""
    from tools.risk_map.kosha_b01_semantic_evidence import CANONICAL_TASK_REFERENCE_PATH
    ref = load_tsv(CANONICAL_TASK_REFERENCE_PATH)
    valid = {r["canonical_id"] for r in ref}
    rows = freeze.build_decisions()
    for r in rows:
        if r["gpt_target_canonical_id"]:
            assert r["gpt_target_canonical_id"] in valid, r["source_key"]


def test_specific_gpt_targets_match_manifest():
    rows = freeze.build_decisions()
    by_key = {r["source_key"]: r for r in rows}

    # §5 all six EXACT_EQUIVALENT → 콘크리트양생.
    for key in freeze._EXACT_EQUIVALENT_KEYS:
        r = by_key[key]
        assert r["gpt_mapping_type"] == "EXACT_EQUIVALENT"
        assert r["gpt_target_canonical_id"] == "3258e587-68ab-40c8-80df-dd4fa0db60b7"
        assert r["gpt_target_canonical_name"] == "콘크리트양생"

    # §8 NARROWER_THAN
    assert by_key["117406f2e819009f2ddab47b1f76558bb8357a553b4fed9892d713cd51954a59"]["gpt_target_canonical_id"] == "995ba818-1aac-4a5b-82cf-6e83ee485bbc"
    for key in (
        "c4b70e8dc6758d004799ee4d2983759fd58654017e1b4b421d92d4d3f84f1190",
        "af804b488a17b2ec4da7642d45e7ab537de018710aa6965d7d522287326d78da",
    ):
        assert by_key[key]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
        assert by_key[key]["gpt_mapping_type"] == "NARROWER_THAN"

    # §9 POSSIBLE_RELATED targets
    assert by_key["5f42f02170a6d35a1da1d418fb421462b2abde0949ef7fc707e447cbed5ab861"]["gpt_target_canonical_id"] == "2517aed8-23bc-4e23-a7c7-fcd8743847a7"
    assert by_key["3fbab883ebce04d2d75a4203c4e55166ffe6b8f379746511a25889702a843ab2"]["gpt_target_canonical_id"] == "2517aed8-23bc-4e23-a7c7-fcd8743847a7"
    assert by_key["a2dbb2d7ab94cf648aef33afdb32b004bea08d6b7455d44c72f7e5dd6b3ce919"]["gpt_target_canonical_id"] == "a7106b20-76ca-427f-aa45-2f0b1d417f15"
    assert by_key["15dc1da3628724396d21e84348a3638c7daa943e3c8785f9b248206402a7dfcf"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
    assert by_key["680726b3338f703a8760b842ea1a5ef3385c97ca41a477444e854583e080bb53"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
    assert by_key["aa4c8b0134ef2667a2a95ae200c4ef3a04932e39129f7821c319b09612f15838"]["gpt_target_canonical_id"] == "be965f09-464b-4d53-9be4-d72f44d3d1ee"


def test_ambiguous_blasting_confidence_high():
    rows = freeze.build_decisions()
    by_key = {r["source_key"]: r for r in rows}
    for key in freeze._AMBIGUOUS_BLASTING_KEYS:
        r = by_key[key]
        assert r["gpt_semantic_decision"] == "AMBIGUOUS"
        assert r["gpt_mapping_type"] == "AMBIGUOUS"
        assert r["gpt_confidence_class"] == "HIGH"
        assert r["gpt_target_canonical_id"] == ""


def test_ambiguous_other_confidence_special_cases():
    """§7.4 굴착 is HIGH; the other five §7 rows are MEDIUM."""
    rows = freeze.build_decisions()
    by_key = {r["source_key"]: r for r in rows}
    assert by_key["3451e54a0b6243825471230c6a013af585c16a9aab44684f888540ca9c7c79cd"]["gpt_confidence_class"] == "HIGH"
    for key in (
        "7ae6a94de7404f042d115235075024bae9fbfa9e98072428336607a3e6c10e07",
        "d36d83795e5353c29c81c891bb876a6c6dc5adac64517cf9d52d636b89968400",
        "5bca42b61bb9ff7076ad4dc7189329fd80e253af88f00e41fefae55ee87f7527",
        "901cb91207a35e91cdac2fd3bccf6583a48f7c073ed8dc79bca7f6fc698f4b7c",
        "562f0e8d7ba06c730135553e1c41cd33a4e97158ee89c332ec758ffbda516add",
    ):
        assert by_key[key]["gpt_confidence_class"] == "MEDIUM"
        assert by_key[key]["gpt_semantic_decision"] == "AMBIGUOUS"


def test_canonical_gap_and_no_match_shape():
    rows = freeze.build_decisions()
    by_key = {r["source_key"]: r for r in rows}
    for key in freeze._CANONICAL_GAP_KEYS:
        r = by_key[key]
        assert r["gpt_semantic_decision"] == "CANONICAL_GAP"
        assert r["gpt_mapping_type"] == ""
        assert r["gpt_target_canonical_id"] == ""
        assert r["gpt_confidence_class"] == "MEDIUM"
    for key in freeze._NO_MATCH_KEYS:
        r = by_key[key]
        assert r["gpt_semantic_decision"] == "NO_MATCH"
        assert r["gpt_mapping_type"] == "NO_MATCH"
        assert r["gpt_target_canonical_id"] == ""
        assert r["gpt_confidence_class"] == "HIGH"


def test_written_decision_when_present():
    if not DECISION_TSV.exists():
        return
    rows = load_tsv(DECISION_TSV)
    assert len(rows) == 100
    assert list(rows[0].keys()) == list(freeze.DECISION_FIELDS)
    assert freeze.decision_sha(rows) == FROZEN_DECISION_SHA


def test_written_census_when_present():
    if not CENSUS_TSV.exists():
        return
    rows = load_tsv(CENSUS_TSV)
    by_bucket = {(r["gpt_semantic_decision"], r["gpt_mapping_type"]): int(r["count"]) for r in rows}
    assert by_bucket[("MAP_EXISTING_CANONICAL", "EXACT_EQUIVALENT")] == 6
    assert by_bucket[("MAP_EXISTING_CANONICAL", "NARROWER_THAN")] == 3
    assert by_bucket[("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED")] == 6
    assert by_bucket[("AMBIGUOUS", "AMBIGUOUS")] == 12
    assert by_bucket[("CANONICAL_GAP", "")] == 29
    assert by_bucket[("NO_MATCH", "NO_MATCH")] == 44
    assert by_bucket[("TOTAL", "")] == 100


def test_report_when_present():
    if not REPORT_MD.exists():
        return
    text = REPORT_MD.read_text(encoding="utf-8")
    for tag in (
        "THIS IS GPT SEMANTIC REVIEW",
        "THIS IS NOT OWNER MAPPING APPROVAL",
        "THIS IS NOT PRODUCTION MATERIALIZATION",
        "THIS DOES NOT LIFT KOSHA IDENTITY HOLD",
        "CANONICAL_GAP IS REVIEW-ONLY",
    ):
        assert tag in text
    assert FROZEN_DECISION_SHA in text
    assert FROZEN_B01_EVIDENCE_SHA in text
    assert FROZEN_CANONICAL_TASK_REFERENCE_SHA in text
    assert "MERGE = NOT AUTHORIZED" in text


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


def test_no_semantic_inference_helpers():
    """Only literal manifest — no scoring, sorting-by-similarity, or fuzzy logic."""
    src = GENERATOR.read_text(encoding="utf-8")
    # Signatures that would indicate the tool is doing semantic work itself.
    for banned in (
        "levenshtein",
        "similarity",
        "embedding",
        "cosine",
        "kiwi",
        "synonym",
        "rapidfuzz",
        "fuzzywuzzy",
    ):
        assert banned not in src.lower(), f"forbidden token {banned!r} in generator"


def test_canonical_gap_is_not_a_db_mapping_type():
    """WO §15: CANONICAL_GAP must NOT reach a real DB mapping_type column."""
    rows = freeze.build_decisions()
    for r in rows:
        # In this artifact CANONICAL_GAP goes into gpt_semantic_decision,
        # not gpt_mapping_type — so gpt_mapping_type stays blank.
        if r["gpt_semantic_decision"] == "CANONICAL_GAP":
            assert r["gpt_mapping_type"] == ""


def test_source_side_fields_echoed_from_b01_evidence():
    """Preserved fields must equal the corresponding B01 evidence row."""
    b01 = {r["source_key"]: r for r in load_tsv(B01_EVIDENCE_PATH)}
    rows = freeze.build_decisions()
    for r in rows:
        src = b01[r["source_key"]]
        for f in ("review_key", "project_kind", "work_type", "source_name", "source_path"):
            assert r[f] == src[f], f
