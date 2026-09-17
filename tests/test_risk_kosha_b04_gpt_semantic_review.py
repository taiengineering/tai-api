"""WO-RISK-KOSHA-B04-REVIEW-001 B04 GPT semantic decision freeze tests. skip = 0."""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kosha_b04_gpt_review_freeze as freeze
from tools.risk_map.kosha_b04_semantic_evidence import B04_EVIDENCE_PATH, b04_evidence_sha

GENERATOR = Path("tools/risk_map/kosha_b04_gpt_review_freeze.py")
DECISION_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B04_GPT_SEMANTIC_REVIEW_v1.tsv")
CENSUS_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B04_GPT_SEMANTIC_CENSUS_v1.tsv")
REPORT_MD = Path("docs/knowledge/risk/OBJ_risk-kosha-b04-gpt-semantic-review_v1.md")

FROZEN_B04_EVIDENCE_SHA = (
    "c44be9c0edac197b175e84a2647497747a636ad71b27dfaa8308492a4616014a"
)
FROZEN_CANONICAL_TASK_REFERENCE_SHA = (
    "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
)
FROZEN_B04_DECISION_SHA = (
    "5d76544dae6c2f509a842baf8f8d394db339d62ffb3f9b6789091f637856815b"
)
FROZEN_B04_CENSUS_SHA = (
    "c1282d07bcdfd391dfc7f5512bbabfafa091190727acfd818c638f2510aaee1b"
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
FROZEN_B03_EVIDENCE_SHA = (
    "22214590663745d75223bcaec284c8f28c0339345703958839952331e1817895"
)
FROZEN_B03_DECISION_SHA = (
    "4dda24f4d3c930249e23c36f3062117cde3063f5182a7fa7a08d1d9fa1e69885"
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
    assert len(freeze._NARROWER_THAN) == 3
    assert len(freeze._POSSIBLE_RELATED) == 4
    assert len(freeze._AMBIGUOUS) == 16
    assert len(freeze._CANONICAL_GAP_KEYS) == 35
    assert len(freeze._NO_MATCH_KEYS) == 42


def test_frozen_input_shas():
    assert freeze.FROZEN_B04_EVIDENCE_SHA == FROZEN_B04_EVIDENCE_SHA
    assert freeze.FROZEN_CANONICAL_TASK_REFERENCE_SHA == FROZEN_CANONICAL_TASK_REFERENCE_SHA


def test_manifest_source_set_matches_b04_exactly():
    b04 = load_tsv(B04_EVIDENCE_PATH)
    assert b04_evidence_sha(b04) == FROZEN_B04_EVIDENCE_SHA
    b04_keys = {r["source_key"] for r in b04}
    manifest_keys = set(freeze.GPT_DECISIONS)
    assert b04_keys == manifest_keys, (
        f"missing={b04_keys - manifest_keys} unexpected={manifest_keys - b04_keys}"
    )


def test_decision_rows_deterministic():
    a = freeze.build_decisions()
    b = freeze.build_decisions()
    assert a == b
    assert freeze.decision_sha(a) == freeze.decision_sha(b) == FROZEN_B04_DECISION_SHA


def test_decision_row_shape():
    rows = freeze.build_decisions()
    assert len(rows) == 100
    assert list(rows[0].keys()) == list(freeze.DECISION_FIELDS)
    for r in rows:
        assert r["review_authority"] == "GPT"
        assert r["review_batch"] == "B04"
        assert r["input_evidence_sha"] == FROZEN_B04_EVIDENCE_SHA
        assert r["canonical_reference_sha"] == FROZEN_CANONICAL_TASK_REFERENCE_SHA


def test_census():
    rows = freeze.build_decisions()
    seen = Counter(
        (r["gpt_semantic_decision"], r["gpt_mapping_type"]) for r in rows
    )
    assert dict(seen) == {
        ("MAP_EXISTING_CANONICAL", "NARROWER_THAN"): 3,
        ("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"): 4,
        ("AMBIGUOUS", "AMBIGUOUS"): 16,
        ("CANONICAL_GAP", ""): 35,
        ("NO_MATCH", "NO_MATCH"): 42,
    }
    assert sum(1 for r in rows if r["gpt_mapping_type"] == "EXACT_EQUIVALENT") == 0


def test_targeted_and_blank_target_counts():
    rows = freeze.build_decisions()
    targeted = [r for r in rows if r["gpt_target_canonical_id"]]
    blank = [r for r in rows if not r["gpt_target_canonical_id"]]
    assert len(targeted) == 7
    assert len(blank) == 93
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


def test_target_universe_is_4_distinct_uuids():
    rows = freeze.build_decisions()
    distinct = {r["gpt_target_canonical_id"] for r in rows if r["gpt_target_canonical_id"]}
    assert distinct == {
        "bae014b7-2474-48f7-b5c0-0e9f30a0ff56",  # 발파
        "5bb130b1-f1ab-4cdb-86d8-9b0985bf9a81",  # 일반부지정지
        "a7106b20-76ca-427f-aa45-2f0b1d417f15",  # 표토제거
        "0ca62c6e-768e-4f68-8198-9abed44589b1",  # 그라우팅천공
    }


def test_specific_gpt_targets_match_manifest():
    rows = freeze.build_decisions()
    by_key = {r["source_key"]: r for r in rows}

    # NARROWER_THAN
    assert by_key["dac358b068a2a0d16a872cad08be58355993bdcb3f30f403b4f345fbd8ddfa46"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
    assert by_key["c627b12da00d39f633c0d5cb113cb8a8751051d207d3d5bf4e332d9b742c4fef"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
    assert by_key["f49a179de6093d47a278c11d9365575a90b90336630b7307e62e0d408bcf118e"]["gpt_target_canonical_id"] == "5bb130b1-f1ab-4cdb-86d8-9b0985bf9a81"

    # POSSIBLE_RELATED
    assert by_key["dcafdcc9bd780cc457898c8134b6beb99bd2a6c3d853b4aa2e5d3fb940cfd162"]["gpt_target_canonical_id"] == "a7106b20-76ca-427f-aa45-2f0b1d417f15"
    assert by_key["38c49be164542c0b351fb4ff3c363b57d8b4175e22ae0290eb583a8f26fcb4de"]["gpt_target_canonical_id"] == "0ca62c6e-768e-4f68-8198-9abed44589b1"
    assert by_key["c3acea604bd3cde456b9e3dbf2e132643569cb8b08a2a467166b42c0eca1b6ca"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
    assert by_key["c31ba1c6c3445549b2f8c7d07b58a07b9c70c770b0feaee67a78a3bae8d622fb"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"


def test_ambiguous_confidence_high_keys():
    """§7 HIGH: only 굴착 in B04."""
    rows = freeze.build_decisions()
    by_key = {r["source_key"]: r for r in rows}
    high_keys = {"d112394908ff4025366bff4f7a2f8e291fb2b0fba69adfb6fc87da0eb6c579e4"}
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
    assert freeze.decision_sha(rows) == FROZEN_B04_DECISION_SHA


def test_written_census_when_present():
    if not CENSUS_TSV.exists():
        return
    rows = load_tsv(CENSUS_TSV)
    by_bucket = {(r["gpt_semantic_decision"], r["gpt_mapping_type"]): int(r["count"]) for r in rows}
    assert by_bucket[("MAP_EXISTING_CANONICAL", "NARROWER_THAN")] == 3
    assert by_bucket[("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED")] == 4
    assert by_bucket[("AMBIGUOUS", "AMBIGUOUS")] == 16
    assert by_bucket[("CANONICAL_GAP", "")] == 35
    assert by_bucket[("NO_MATCH", "NO_MATCH")] == 42
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
    assert FROZEN_B04_DECISION_SHA in text
    assert FROZEN_B04_EVIDENCE_SHA in text
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


def test_source_side_fields_echoed_from_b04_evidence():
    b04 = {r["source_key"]: r for r in load_tsv(B04_EVIDENCE_PATH)}
    rows = freeze.build_decisions()
    for r in rows:
        src = b04[r["source_key"]]
        for f in ("review_key", "project_kind", "work_type", "source_name", "source_path"):
            assert r[f] == src[f], f


# ---------------------------------------------------------------------------
# Prior artifact immutability regression
# ---------------------------------------------------------------------------


def test_prior_evidence_sha_unchanged():
    from tools.risk_map.kosha_b01_semantic_evidence import B01_EVIDENCE_PATH, b01_evidence_sha
    from tools.risk_map.kosha_b02_semantic_evidence import B02_EVIDENCE_PATH as B02EP, b02_evidence_sha
    from tools.risk_map.kosha_b03_semantic_evidence import B03_EVIDENCE_PATH as B03EP, b03_evidence_sha
    assert b01_evidence_sha(load_tsv(B01_EVIDENCE_PATH)) == FROZEN_B01_EVIDENCE_SHA
    assert b02_evidence_sha(load_tsv(B02EP)) == FROZEN_B02_EVIDENCE_SHA
    assert b03_evidence_sha(load_tsv(B03EP)) == FROZEN_B03_EVIDENCE_SHA


def test_prior_gpt_review_sha_unchanged():
    from tools.risk04.seed_review import universe_sha
    from tools.risk_map.kosha_b01_gpt_review_freeze import DECISION_FIELDS as B01_FIELDS
    for path, sha in (
        (Path("docs/knowledge/risk/RISK_KOSHA_B01_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B01_DECISION_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B02_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B02_DECISION_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B03_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B03_DECISION_SHA),
    ):
        rows = load_tsv(path)
        assert universe_sha(rows, *B01_FIELDS) == sha, path
