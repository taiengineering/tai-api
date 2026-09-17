"""WO-RISK-KOSHA-B05-REVIEW-001 B05 GPT semantic decision freeze tests. skip = 0."""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kosha_b05_gpt_review_freeze as freeze
from tools.risk_map.kosha_b05_semantic_evidence import B05_EVIDENCE_PATH, b05_evidence_sha

GENERATOR = Path("tools/risk_map/kosha_b05_gpt_review_freeze.py")
DECISION_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B05_GPT_SEMANTIC_REVIEW_v1.tsv")
CENSUS_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B05_GPT_SEMANTIC_CENSUS_v1.tsv")
REPORT_MD = Path("docs/knowledge/risk/OBJ_risk-kosha-b05-gpt-semantic-review_v1.md")

FROZEN_B05_EVIDENCE_SHA = (
    "67a0a8a09af59772c61cad93af3b2dd3fcf818dfde794e972ea0c74fb0fc3ed0"
)
FROZEN_CANONICAL_TASK_REFERENCE_SHA = (
    "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
)
FROZEN_B05_DECISION_SHA = (
    "feb52cb79c36abb1f1fad96f4b7f61d3b04d57e9550696d17d85b69f6b37cda2"
)
FROZEN_B05_CENSUS_SHA = (
    "1b5dc36ba3410e7813621cb500e59e1d519de51cff31285c1951478dcf0f098d"
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
FROZEN_B04_EVIDENCE_SHA = (
    "c44be9c0edac197b175e84a2647497747a636ad71b27dfaa8308492a4616014a"
)
FROZEN_B04_DECISION_SHA = (
    "5d76544dae6c2f509a842baf8f8d394db339d62ffb3f9b6789091f637856815b"
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
    assert len(freeze._NARROWER_THAN) == 7
    assert len(freeze._POSSIBLE_RELATED) == 3
    assert len(freeze._AMBIGUOUS) == 11
    assert len(freeze._CANONICAL_GAP_KEYS) == 35
    assert len(freeze._NO_MATCH_KEYS) == 44


def test_frozen_input_shas():
    assert freeze.FROZEN_B05_EVIDENCE_SHA == FROZEN_B05_EVIDENCE_SHA
    assert freeze.FROZEN_CANONICAL_TASK_REFERENCE_SHA == FROZEN_CANONICAL_TASK_REFERENCE_SHA


def test_manifest_source_set_matches_b05_exactly():
    b05 = load_tsv(B05_EVIDENCE_PATH)
    assert b05_evidence_sha(b05) == FROZEN_B05_EVIDENCE_SHA
    b05_keys = {r["source_key"] for r in b05}
    manifest_keys = set(freeze.GPT_DECISIONS)
    assert b05_keys == manifest_keys, (
        f"missing={b05_keys - manifest_keys} unexpected={manifest_keys - b05_keys}"
    )


def test_decision_rows_deterministic():
    a = freeze.build_decisions()
    b = freeze.build_decisions()
    assert a == b
    assert freeze.decision_sha(a) == freeze.decision_sha(b) == FROZEN_B05_DECISION_SHA


def test_decision_row_shape():
    rows = freeze.build_decisions()
    assert len(rows) == 100
    assert list(rows[0].keys()) == list(freeze.DECISION_FIELDS)
    for r in rows:
        assert r["review_authority"] == "GPT"
        assert r["review_batch"] == "B05"
        assert r["input_evidence_sha"] == FROZEN_B05_EVIDENCE_SHA
        assert r["canonical_reference_sha"] == FROZEN_CANONICAL_TASK_REFERENCE_SHA


def test_census():
    rows = freeze.build_decisions()
    seen = Counter(
        (r["gpt_semantic_decision"], r["gpt_mapping_type"]) for r in rows
    )
    assert dict(seen) == {
        ("MAP_EXISTING_CANONICAL", "NARROWER_THAN"): 7,
        ("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"): 3,
        ("AMBIGUOUS", "AMBIGUOUS"): 11,
        ("CANONICAL_GAP", ""): 35,
        ("NO_MATCH", "NO_MATCH"): 44,
    }
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


def test_target_universe_is_5_distinct_uuids():
    rows = freeze.build_decisions()
    distinct = {r["gpt_target_canonical_id"] for r in rows if r["gpt_target_canonical_id"]}
    assert distinct == {
        "813be6a8-13c4-4c96-9c90-36bd04348fb5",  # 바닥판깔기
        "bae014b7-2474-48f7-b5c0-0e9f30a0ff56",  # 발파
        "af9b0594-96e9-4564-bea6-f80a261c55fc",  # 건축철골조립및설치
        "892b579d-42bf-4c3e-8a71-e37d8ce00e1b",  # 현장타설콘크리트라이닝 (NEW in B05)
        "be965f09-464b-4d53-9be4-d72f44d3d1ee",  # 철근가공및조립
    }


def test_specific_gpt_targets_match_manifest():
    rows = freeze.build_decisions()
    by_key = {r["source_key"]: r for r in rows}

    # NARROWER_THAN
    assert by_key["5f95e1f68791e5dc47687829a2373a43772d56d0eadc87dc4adc6cd5a999a4eb"]["gpt_target_canonical_id"] == "813be6a8-13c4-4c96-9c90-36bd04348fb5"
    assert by_key["00dbfaa40674ac08e63808ce67f5a096e61660f14dab5b31330f9fd992f91fd1"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
    assert by_key["a3cfbabe3d622390ae9a8783452c489bda011d993c92ae1cc7468afa31e4e6da"]["gpt_target_canonical_id"] == "af9b0594-96e9-4564-bea6-f80a261c55fc"
    assert by_key["96b9aaece79474e2ac748a47c1dad8c195020feaf1f7fd575a9c23b2290f3192"]["gpt_target_canonical_id"] == "892b579d-42bf-4c3e-8a71-e37d8ce00e1b"
    assert by_key["0723febc423eebfd3a26864631c8b3e27fc13221ed6a7cecb3bf646eb3c4488c"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
    assert by_key["f674b465439adee738eeb791ef13287d851431821d3197e34b66470795450273"]["gpt_target_canonical_id"] == "892b579d-42bf-4c3e-8a71-e37d8ce00e1b"
    assert by_key["8734033aadf41b2e9395e5a304eff82fe166c1ee2085d4954286dbb5e3c9fef0"]["gpt_target_canonical_id"] == "be965f09-464b-4d53-9be4-d72f44d3d1ee"

    # POSSIBLE_RELATED
    assert by_key["870480a0a4af34f3b42a13dab2b5d2b06570bed038d8dc6b12ce68376da950c8"]["gpt_target_canonical_id"] == "be965f09-464b-4d53-9be4-d72f44d3d1ee"
    assert by_key["4528b248b07014e58b1a75dc326bb1757a2da6b7f43158d2ec908ac7b8aaa51d"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"
    assert by_key["89a48e95ddff09d8c03c3038f9c846990b96bf2da2b881d35fe02908173ba561"]["gpt_target_canonical_id"] == "bae014b7-2474-48f7-b5c0-0e9f30a0ff56"


def test_ambiguous_confidence_high_keys():
    """§7 HIGH: 굴착 + 콘크리트타설."""
    rows = freeze.build_decisions()
    by_key = {r["source_key"]: r for r in rows}
    high_keys = {
        "d338979f3800ba580e63593cbd99c086c4041d99375b9e8f516a8f9b1b031509",  # 굴착
        "489e1dc03927c8581c75eba9275893bf0004c3287116cc9139d14be846e0aa54",  # 콘크리트타설
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
    assert freeze.decision_sha(rows) == FROZEN_B05_DECISION_SHA


def test_written_census_when_present():
    if not CENSUS_TSV.exists():
        return
    rows = load_tsv(CENSUS_TSV)
    by_bucket = {(r["gpt_semantic_decision"], r["gpt_mapping_type"]): int(r["count"]) for r in rows}
    assert by_bucket[("MAP_EXISTING_CANONICAL", "NARROWER_THAN")] == 7
    assert by_bucket[("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED")] == 3
    assert by_bucket[("AMBIGUOUS", "AMBIGUOUS")] == 11
    assert by_bucket[("CANONICAL_GAP", "")] == 35
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
        "NO_MATCH IS REVIEW-ONLY UNTIL OWNER APPROVAL",
    ):
        assert tag in text
    assert FROZEN_B05_DECISION_SHA in text
    assert FROZEN_B05_EVIDENCE_SHA in text
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


def test_source_side_fields_echoed_from_b05_evidence():
    b05 = {r["source_key"]: r for r in load_tsv(B05_EVIDENCE_PATH)}
    rows = freeze.build_decisions()
    for r in rows:
        src = b05[r["source_key"]]
        for f in ("review_key", "project_kind", "work_type", "source_name", "source_path"):
            assert r[f] == src[f], f


# ---------------------------------------------------------------------------
# Prior artifact immutability regression
# ---------------------------------------------------------------------------


def test_prior_evidence_sha_unchanged():
    from tools.risk_map.kosha_b01_semantic_evidence import B01_EVIDENCE_PATH, b01_evidence_sha
    from tools.risk_map.kosha_b02_semantic_evidence import B02_EVIDENCE_PATH as B02EP, b02_evidence_sha
    from tools.risk_map.kosha_b03_semantic_evidence import B03_EVIDENCE_PATH as B03EP, b03_evidence_sha
    from tools.risk_map.kosha_b04_semantic_evidence import B04_EVIDENCE_PATH as B04EP, b04_evidence_sha
    assert b01_evidence_sha(load_tsv(B01_EVIDENCE_PATH)) == FROZEN_B01_EVIDENCE_SHA
    assert b02_evidence_sha(load_tsv(B02EP)) == FROZEN_B02_EVIDENCE_SHA
    assert b03_evidence_sha(load_tsv(B03EP)) == FROZEN_B03_EVIDENCE_SHA
    assert b04_evidence_sha(load_tsv(B04EP)) == FROZEN_B04_EVIDENCE_SHA


def test_prior_gpt_review_sha_unchanged():
    from tools.risk04.seed_review import universe_sha
    from tools.risk_map.kosha_b01_gpt_review_freeze import DECISION_FIELDS as B01_FIELDS
    for path, sha in (
        (Path("docs/knowledge/risk/RISK_KOSHA_B01_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B01_DECISION_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B02_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B02_DECISION_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B03_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B03_DECISION_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B04_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B04_DECISION_SHA),
    ):
        rows = load_tsv(path)
        assert universe_sha(rows, *B01_FIELDS) == sha, path
