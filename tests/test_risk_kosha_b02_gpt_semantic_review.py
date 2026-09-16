"""WO-RISK-KOSHA-B02-REVIEW-001 B02 GPT semantic decision freeze tests. skip = 0."""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kosha_b02_gpt_review_freeze as freeze
from tools.risk_map.kosha_b02_semantic_evidence import B02_EVIDENCE_PATH, b02_evidence_sha

GENERATOR = Path("tools/risk_map/kosha_b02_gpt_review_freeze.py")
DECISION_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B02_GPT_SEMANTIC_REVIEW_v1.tsv")
CENSUS_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B02_GPT_SEMANTIC_CENSUS_v1.tsv")
REPORT_MD = Path("docs/knowledge/risk/OBJ_risk-kosha-b02-gpt-semantic-review_v1.md")

FROZEN_B02_EVIDENCE_SHA = (
    "402fafe9e1026838ffd0c2fb15b6b685b3554c15aa07999329a6c073752f71dd"
)
FROZEN_CANONICAL_TASK_REFERENCE_SHA = (
    "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
)
FROZEN_B02_DECISION_SHA = (
    "59dbdf26645b536aac2cd16b3cdaac477de29be793aa3d0a2c209b210e20b787"
)
FROZEN_B02_CENSUS_SHA = (
    "15ec1c0a0dc9939c750d88a135cb670b9361d23a165568fd364e5f835215fbc3"
)
FROZEN_B01_DECISION_SHA = (
    "4b39776f3404f100a182fa23727c74f5cb239036b78ac25d99c82b46662f8bfd"
)
FROZEN_B01_EVIDENCE_SHA = (
    "bfa75ed7cb87368f9b0744188bd07ac87a495d641945e0e731565fda6517fde8"
)


def test_manifest_frozen_size_and_uniqueness():
    assert len(freeze.GPT_DECISIONS) == 100
    grouped = (
        [k for k, _, _, _ in freeze._NARROWER_THAN]
        + [k for k, _, _ in freeze._POSSIBLE_RELATED]
        + [k for k, _, _ in freeze._AMBIGUOUS]
        + list(freeze._CANONICAL_GAP_KEYS)
        + list(freeze._NO_MATCH_KEYS)
    )
    assert len(grouped) == 100
    assert len(set(grouped)) == 100


def test_manifest_group_counts():
    assert len(freeze._NARROWER_THAN) == 6
    assert len(freeze._POSSIBLE_RELATED) == 5
    assert len(freeze._AMBIGUOUS) == 8
    assert len(freeze._CANONICAL_GAP_KEYS) == 25
    assert len(freeze._NO_MATCH_KEYS) == 56


def test_frozen_input_shas():
    assert freeze.FROZEN_B02_EVIDENCE_SHA == FROZEN_B02_EVIDENCE_SHA
    assert freeze.FROZEN_CANONICAL_TASK_REFERENCE_SHA == FROZEN_CANONICAL_TASK_REFERENCE_SHA


def test_manifest_source_set_matches_b02_exactly():
    b02 = load_tsv(B02_EVIDENCE_PATH)
    assert b02_evidence_sha(b02) == FROZEN_B02_EVIDENCE_SHA
    b02_keys = {r["source_key"] for r in b02}
    manifest_keys = set(freeze.GPT_DECISIONS)
    assert b02_keys == manifest_keys, (
        f"missing={b02_keys - manifest_keys} unexpected={manifest_keys - b02_keys}"
    )


def test_decision_rows_deterministic():
    a = freeze.build_decisions()
    b = freeze.build_decisions()
    assert a == b
    assert freeze.decision_sha(a) == freeze.decision_sha(b) == FROZEN_B02_DECISION_SHA


def test_decision_row_shape():
    rows = freeze.build_decisions()
    assert len(rows) == 100
    assert list(rows[0].keys()) == list(freeze.DECISION_FIELDS)
    for r in rows:
        assert r["review_authority"] == "GPT"
        assert r["review_batch"] == "B02"
        assert r["input_evidence_sha"] == FROZEN_B02_EVIDENCE_SHA
        assert r["canonical_reference_sha"] == FROZEN_CANONICAL_TASK_REFERENCE_SHA


def test_census():
    rows = freeze.build_decisions()
    seen = Counter(
        (r["gpt_semantic_decision"], r["gpt_mapping_type"]) for r in rows
    )
    assert dict(seen) == {
        ("MAP_EXISTING_CANONICAL", "NARROWER_THAN"): 6,
        ("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"): 5,
        ("AMBIGUOUS", "AMBIGUOUS"): 8,
        ("CANONICAL_GAP", ""): 25,
        ("NO_MATCH", "NO_MATCH"): 56,
    }
    # Explicit "EXACT_EQUIVALENT = 0" guard for B02.
    assert (
        sum(1 for r in rows if r["gpt_mapping_type"] == "EXACT_EQUIVALENT") == 0
    )


def test_targeted_and_blank_target_counts():
    rows = freeze.build_decisions()
    targeted = [r for r in rows if r["gpt_target_canonical_id"]]
    blank = [r for r in rows if not r["gpt_target_canonical_id"]]
    assert len(targeted) == 11
    assert len(blank) == 89
    for r in targeted:
        assert r["gpt_target_canonical_name"]
        assert r["gpt_semantic_decision"] == "MAP_EXISTING_CANONICAL"
        assert r["gpt_mapping_type"] in {"NARROWER_THAN", "POSSIBLE_RELATED"}


def test_targeted_canonical_ids_valid_and_task():
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

    # NARROWER_THAN targets
    assert by_key["356e247dc8ffcb04de5f66a0ea98e29b25e646b0f5ab6d9ce5f80f86ba6ad022"]["gpt_target_canonical_id"] == "be965f09-464b-4d53-9be4-d72f44d3d1ee"
    assert by_key["c79380a2d93663891d26bf3b427845f18ab58012637df588431c778cc930399e"]["gpt_target_canonical_id"] == "97cf2571-0f3a-4bb2-8a85-837bbd502bb0"
    assert by_key["f0c418636e58bcdc1e89f25952cc9948f6af85680a965f9a9fd19bb64ae27710"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
    assert by_key["eead61646f3d44d3b0f018b70f6c9a2dcd90d1836469daf4707f539da44a43a9"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
    assert by_key["18dd13b6ceb8f503f56e417710183abacead45d069088f51fb4568deeeb260bc"]["gpt_target_canonical_id"] == "5bb130b1-f1ab-4cdb-86d8-9b0985bf9a81"
    assert by_key["0620aa3261e75db6a1c3d87922764cc28204c2cb6e48deca3cbd847b267566d9"]["gpt_target_canonical_id"] == "be965f09-464b-4d53-9be4-d72f44d3d1ee"

    # POSSIBLE_RELATED targets
    assert by_key["019b2c465ec252bcbe6fe426e1af76d0be56255c03e9f24ff6609d2bfefbb6e9"]["gpt_target_canonical_id"] == "97cf2571-0f3a-4bb2-8a85-837bbd502bb0"
    assert by_key["af0b41941bc3abfb477dad8f32db3cea62f2ad82b81eeab423b9f8663c4acd77"]["gpt_target_canonical_id"] == "a7106b20-76ca-427f-aa45-2f0b1d417f15"
    assert by_key["edea1aa11b35d92d4ab96af29234e35d2a6a2a49207a223ba11b34c087e659f6"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
    assert by_key["c826a967fda0d866048a7925a1ab1119e64cb164510814d6b25ef3887ac81071"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
    assert by_key["82e7b20228f8611ddc7f3baf5857f0a3e80247526510a1e6955538bb35d18cb3"]["gpt_target_canonical_id"] == "be965f09-464b-4d53-9be4-d72f44d3d1ee"


def test_ambiguous_confidence_high_low_matches_family():
    """Generic 굴착 / 콘크리트타설 rows carry HIGH; others MEDIUM."""
    rows = freeze.build_decisions()
    by_key = {r["source_key"]: r for r in rows}
    high_keys = {
        "d1a6603ef36c99cb34ab1596f47c56495aa362cdfa86709a095977ac3ae5ed96",  # 콘크리트타설 도로
        "05f3d761f2d16da8e5629696c606cfef6416ec1ecb262322f43e4f08c829684a",  # 굴착 댐
        "ac0b554f4e3de2d03db0634535bd37f8d9bb54f52e906993d7529e507160f275",  # 콘크리트타설 댐
    }
    for key in high_keys:
        assert by_key[key]["gpt_confidence_class"] == "HIGH"
        assert by_key[key]["gpt_semantic_decision"] == "AMBIGUOUS"

    for key, _reason, _conf in freeze._AMBIGUOUS:
        if key not in high_keys:
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
    assert freeze.decision_sha(rows) == FROZEN_B02_DECISION_SHA


def test_written_census_when_present():
    if not CENSUS_TSV.exists():
        return
    rows = load_tsv(CENSUS_TSV)
    by_bucket = {(r["gpt_semantic_decision"], r["gpt_mapping_type"]): int(r["count"]) for r in rows}
    assert by_bucket[("MAP_EXISTING_CANONICAL", "NARROWER_THAN")] == 6
    assert by_bucket[("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED")] == 5
    assert by_bucket[("AMBIGUOUS", "AMBIGUOUS")] == 8
    assert by_bucket[("CANONICAL_GAP", "")] == 25
    assert by_bucket[("NO_MATCH", "NO_MATCH")] == 56
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
        "NO_MATCH IS REVIEW-ONLY UNTIL OWNER APPROVAL",
    ):
        assert tag in text
    assert FROZEN_B02_DECISION_SHA in text
    assert FROZEN_B02_EVIDENCE_SHA in text
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
    src = GENERATOR.read_text(encoding="utf-8")
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


def test_source_side_fields_echoed_from_b02_evidence():
    b02 = {r["source_key"]: r for r in load_tsv(B02_EVIDENCE_PATH)}
    rows = freeze.build_decisions()
    for r in rows:
        src = b02[r["source_key"]]
        for f in ("review_key", "project_kind", "work_type", "source_name", "source_path"):
            assert r[f] == src[f], f


# ---------------------------------------------------------------------------
# B01 immutability regression — this WO must not touch prior artifacts.
# ---------------------------------------------------------------------------


def test_b01_evidence_sha_unchanged():
    from tools.risk_map.kosha_b01_semantic_evidence import (
        B01_EVIDENCE_PATH,
        b01_evidence_sha,
    )
    rows = load_tsv(B01_EVIDENCE_PATH)
    assert b01_evidence_sha(rows) == FROZEN_B01_EVIDENCE_SHA


def test_b01_gpt_review_sha_unchanged():
    from tools.risk_map.kosha_b01_gpt_review_freeze import (
        DECISION_FIELDS as B01_DECISION_FIELDS,
    )
    b01_review_path = Path(
        "docs/knowledge/risk/RISK_KOSHA_B01_GPT_SEMANTIC_REVIEW_v1.tsv"
    )
    from tools.risk04.seed_review import universe_sha as _sha
    rows = load_tsv(b01_review_path)
    assert len(rows) == 100
    assert _sha(rows, *B01_DECISION_FIELDS) == FROZEN_B01_DECISION_SHA
