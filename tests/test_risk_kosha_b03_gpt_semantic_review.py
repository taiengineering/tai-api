"""WO-RISK-KOSHA-B03-REVIEW-001 B03 GPT semantic decision freeze tests. skip = 0."""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kosha_b03_gpt_review_freeze as freeze
from tools.risk_map.kosha_b03_semantic_evidence import B03_EVIDENCE_PATH, b03_evidence_sha

GENERATOR = Path("tools/risk_map/kosha_b03_gpt_review_freeze.py")
DECISION_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B03_GPT_SEMANTIC_REVIEW_v1.tsv")
CENSUS_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B03_GPT_SEMANTIC_CENSUS_v1.tsv")
REPORT_MD = Path("docs/knowledge/risk/OBJ_risk-kosha-b03-gpt-semantic-review_v1.md")

FROZEN_B03_EVIDENCE_SHA = (
    "22214590663745d75223bcaec284c8f28c0339345703958839952331e1817895"
)
FROZEN_CANONICAL_TASK_REFERENCE_SHA = (
    "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
)
FROZEN_B03_DECISION_SHA = (
    "4dda24f4d3c930249e23c36f3062117cde3063f5182a7fa7a08d1d9fa1e69885"
)
FROZEN_B03_CENSUS_SHA = (
    "0590d355c0d8063eca2fe82a45a8efbdac21f663d68c9ea8aa523a47922b3dbd"
)
FROZEN_B01_EVIDENCE_SHA = (
    "bfa75ed7cb87368f9b0744188bd07ac87a495d641945e0e731565fda6517fde8"
)
FROZEN_B01_DECISION_SHA = (
    "4b39776f3404f100a182fa23727c74f5cb239036b78ac25d99c82b46662f8bfd"
)
FROZEN_B02_EVIDENCE_SHA = (
    "402fafe9e1026838ffd0c2fb15b6b685b3554c15aa07999329a6c073752f71dd"
)
FROZEN_B02_DECISION_SHA = (
    "59dbdf26645b536aac2cd16b3cdaac477de29be793aa3d0a2c209b210e20b787"
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
    assert len(freeze._POSSIBLE_RELATED) == 4
    assert len(freeze._AMBIGUOUS) == 18
    assert len(freeze._CANONICAL_GAP_KEYS) == 36
    assert len(freeze._NO_MATCH_KEYS) == 36


def test_frozen_input_shas():
    assert freeze.FROZEN_B03_EVIDENCE_SHA == FROZEN_B03_EVIDENCE_SHA
    assert freeze.FROZEN_CANONICAL_TASK_REFERENCE_SHA == FROZEN_CANONICAL_TASK_REFERENCE_SHA


def test_manifest_source_set_matches_b03_exactly():
    b03 = load_tsv(B03_EVIDENCE_PATH)
    assert b03_evidence_sha(b03) == FROZEN_B03_EVIDENCE_SHA
    b03_keys = {r["source_key"] for r in b03}
    manifest_keys = set(freeze.GPT_DECISIONS)
    assert b03_keys == manifest_keys, (
        f"missing={b03_keys - manifest_keys} unexpected={manifest_keys - b03_keys}"
    )


def test_decision_rows_deterministic():
    a = freeze.build_decisions()
    b = freeze.build_decisions()
    assert a == b
    assert freeze.decision_sha(a) == freeze.decision_sha(b) == FROZEN_B03_DECISION_SHA


def test_decision_row_shape():
    rows = freeze.build_decisions()
    assert len(rows) == 100
    assert list(rows[0].keys()) == list(freeze.DECISION_FIELDS)
    for r in rows:
        assert r["review_authority"] == "GPT"
        assert r["review_batch"] == "B03"
        assert r["input_evidence_sha"] == FROZEN_B03_EVIDENCE_SHA
        assert r["canonical_reference_sha"] == FROZEN_CANONICAL_TASK_REFERENCE_SHA


def test_census():
    rows = freeze.build_decisions()
    seen = Counter(
        (r["gpt_semantic_decision"], r["gpt_mapping_type"]) for r in rows
    )
    assert dict(seen) == {
        ("MAP_EXISTING_CANONICAL", "NARROWER_THAN"): 6,
        ("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"): 4,
        ("AMBIGUOUS", "AMBIGUOUS"): 18,
        ("CANONICAL_GAP", ""): 36,
        ("NO_MATCH", "NO_MATCH"): 36,
    }
    # Explicit "EXACT_EQUIVALENT = 0" guard.
    assert sum(1 for r in rows if r["gpt_mapping_type"] == "EXACT_EQUIVALENT") == 0


def test_targeted_and_blank_target_counts():
    rows = freeze.build_decisions()
    targeted = [r for r in rows if r["gpt_target_canonical_id"]]
    blank = [r for r in rows if not r["gpt_target_canonical_id"]]
    assert len(targeted) == 10
    assert len(blank) == 90
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


def test_target_universe_is_6_distinct_uuids():
    rows = freeze.build_decisions()
    distinct = {r["gpt_target_canonical_id"] for r in rows if r["gpt_target_canonical_id"]}
    assert distinct == {
        "bae014b7-2474-48f7-b5c0-0e9f30a0ff56",  # 발파
        "5bb130b1-f1ab-4cdb-86d8-9b0985bf9a81",  # 일반부지정지
        "813be6a8-13c4-4c96-9c90-36bd04348fb5",  # 바닥판깔기
        "af9b0594-96e9-4564-bea6-f80a261c55fc",  # 건축철골조립및설치
        "be965f09-464b-4d53-9be4-d72f44d3d1ee",  # 철근가공및조립
        "0ca62c6e-768e-4f68-8198-9abed44589b1",  # 그라우팅천공
    }


def test_specific_gpt_targets_match_manifest():
    rows = freeze.build_decisions()
    by_key = {r["source_key"]: r for r in rows}

    # NARROWER_THAN
    assert by_key["641919de6e83ffb96c9ca7a6cf041a5defe192a379ca46b9dbdc92db4576a9f5"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
    assert by_key["c24324369b26b27ab179942337a72783dc87fc46c97e2f6e5ce296025a9329f4"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
    assert by_key["7efc915d5a83fd9a932fef678784a410008457f2e355f3c249e90f18393b1faf"]["gpt_target_canonical_id"] == "5bb130b1-f1ab-4cdb-86d8-9b0985bf9a81"
    assert by_key["044cd69cac9e0eee8d561010be2296bdbf0163125f3e67ff40eaf8098bb83964"]["gpt_target_canonical_id"] == "813be6a8-13c4-4c96-9c90-36bd04348fb5"
    assert by_key["8305162695fd8b6264d3bfb4ba1339e6cf9d4b1166202b1b723f5dfb5f27003b"]["gpt_target_canonical_id"] == "af9b0594-96e9-4564-bea6-f80a261c55fc"
    assert by_key["b95ce311e9ca694ae6390886be6f640d03463a19c93613107684f97881e6ca5a"]["gpt_target_canonical_id"] == "be965f09-464b-4d53-9be4-d72f44d3d1ee"

    # POSSIBLE_RELATED
    assert by_key["4111216b25c72b30f66021e3293e45aa37a8ef71272a8fa2e2092394f2bb44dd"]["gpt_target_canonical_id"] == "0ca62c6e-768e-4f68-8198-9abed44589b1"
    assert by_key["87afd5a166ca917afa304f192a68292050ebd4ed90717d059accf459a896b981"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
    assert by_key["70ffac8dcffb8e1b8ab004f6596dda93e798963b82f1742bd37c04a6cf046fc3"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
    assert by_key["f9e364e5d200df306ba374afc3c060a3a65c8c963eb440e2270ca3f32591b09b"]["gpt_target_canonical_id"] == "be965f09-464b-4d53-9be4-d72f44d3d1ee"


def test_ambiguous_confidence_high_keys():
    """§7.1: 굴착 and 콘크리트타설 rows carry HIGH; the other 16 MEDIUM."""
    rows = freeze.build_decisions()
    by_key = {r["source_key"]: r for r in rows}
    high_keys = {
        "7eb696e29d8a77d6bf88a8fdaf074b983d3cd8001d05c45b06d0e06290ce4276",  # 굴착
        "8167d0552e3fe6125d19227d0dee39fd50b236a1741d3a841d52c5e3dfae7df1",  # 콘크리트타설
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
    assert freeze.decision_sha(rows) == FROZEN_B03_DECISION_SHA


def test_written_census_when_present():
    if not CENSUS_TSV.exists():
        return
    rows = load_tsv(CENSUS_TSV)
    by_bucket = {(r["gpt_semantic_decision"], r["gpt_mapping_type"]): int(r["count"]) for r in rows}
    assert by_bucket[("MAP_EXISTING_CANONICAL", "NARROWER_THAN")] == 6
    assert by_bucket[("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED")] == 4
    assert by_bucket[("AMBIGUOUS", "AMBIGUOUS")] == 18
    assert by_bucket[("CANONICAL_GAP", "")] == 36
    assert by_bucket[("NO_MATCH", "NO_MATCH")] == 36
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
    assert FROZEN_B03_DECISION_SHA in text
    assert FROZEN_B03_EVIDENCE_SHA in text
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


def test_source_side_fields_echoed_from_b03_evidence():
    b03 = {r["source_key"]: r for r in load_tsv(B03_EVIDENCE_PATH)}
    rows = freeze.build_decisions()
    for r in rows:
        src = b03[r["source_key"]]
        for f in ("review_key", "project_kind", "work_type", "source_name", "source_path"):
            assert r[f] == src[f], f


# ---------------------------------------------------------------------------
# Prior artifacts immutability regression (§25/§26)
# ---------------------------------------------------------------------------


def test_b01_and_b02_evidence_sha_unchanged():
    from tools.risk_map.kosha_b01_semantic_evidence import B01_EVIDENCE_PATH, b01_evidence_sha
    from tools.risk_map.kosha_b02_semantic_evidence import B02_EVIDENCE_PATH as B02EP, b02_evidence_sha
    assert b01_evidence_sha(load_tsv(B01_EVIDENCE_PATH)) == FROZEN_B01_EVIDENCE_SHA
    assert b02_evidence_sha(load_tsv(B02EP)) == FROZEN_B02_EVIDENCE_SHA


def test_b01_and_b02_gpt_review_sha_unchanged():
    from tools.risk04.seed_review import universe_sha
    from tools.risk_map.kosha_b01_gpt_review_freeze import DECISION_FIELDS as B01_FIELDS
    b01 = load_tsv(Path("docs/knowledge/risk/RISK_KOSHA_B01_GPT_SEMANTIC_REVIEW_v1.tsv"))
    b02 = load_tsv(Path("docs/knowledge/risk/RISK_KOSHA_B02_GPT_SEMANTIC_REVIEW_v1.tsv"))
    assert universe_sha(b01, *B01_FIELDS) == FROZEN_B01_DECISION_SHA
    assert universe_sha(b02, *B01_FIELDS) == FROZEN_B02_DECISION_SHA
