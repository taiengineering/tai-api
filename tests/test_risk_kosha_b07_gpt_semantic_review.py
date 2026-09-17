"""WO-RISK-KOSHA-B07-REVIEW-001 B07 GPT semantic decision freeze tests.

Lean scope per WO §13: verify the 20-row manifest / evidence contract, the
census, the (review_key, source_key) pair preservation, and confirm the
B01-B06 frozen artifacts remain byte-identical. skip = 0.
"""
from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kosha_b07_gpt_review_freeze as freeze
from tools.risk_map.kosha_b07_semantic_evidence import B07_EVIDENCE_PATH, b07_evidence_sha

GENERATOR = Path("tools/risk_map/kosha_b07_gpt_review_freeze.py")
DECISION_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B07_GPT_SEMANTIC_REVIEW_v1.tsv")
CENSUS_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B07_GPT_SEMANTIC_CENSUS_v1.tsv")
REPORT_MD = Path("docs/knowledge/risk/OBJ_risk-kosha-b07-gpt-semantic-review_v1.md")

FROZEN_B07_EVIDENCE_SHA = (
    "b1c9ed4280fc971257561a2696df5748c9411c50a0c9330805375d7114af0060"
)
FROZEN_CANONICAL_TASK_REFERENCE_SHA = (
    "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
)
FROZEN_B07_DECISION_SHA = (
    "a2d64c551c1104eb304859773a0a74417560410c3d58f5cf3112d4c6abb2d5ba"
)
FROZEN_B07_CENSUS_SHA = (
    "1f3fde3dd58b4e7950e8b45ce73788ffcfcc86c8d37162d689d7033b47cf1714"
)

FROZEN_B01_EVIDENCE_SHA = (
    "bfa75ed7cb87368f9b0744188bd07ac87a495d641945e0e731565fda6517fde8"
)
FROZEN_B02_EVIDENCE_SHA = (
    "402fafe9e1026838ffd0c2fb15b6b685b3554c15aa07999329a6c073752f71dd"
)
FROZEN_B03_EVIDENCE_SHA = (
    "22214590663745d75223bcaec284c8f28c0339345703958839952331e1817895"
)
FROZEN_B04_EVIDENCE_SHA = (
    "c44be9c0edac197b175e84a2647497747a636ad71b27dfaa8308492a4616014a"
)
FROZEN_B05_EVIDENCE_SHA = (
    "67a0a8a09af59772c61cad93af3b2dd3fcf818dfde794e972ea0c74fb0fc3ed0"
)
FROZEN_B06_EVIDENCE_SHA = (
    "b0df9c2e77642184bc98fa67bc94e5073a41913ccc9a867da1ec5bf3bbfc34c2"
)

FROZEN_B01_DECISION_SHA = (
    "4b39776f3404f100a182fa23727c74f5cb239036b78ac25d99c82b46662f8bfd"
)
FROZEN_B02_DECISION_SHA = (
    "59dbdf26645b536aac2cd16b3cdaac477de29be793aa3d0a2c209b210e20b787"
)
FROZEN_B03_DECISION_SHA = (
    "4dda24f4d3c930249e23c36f3062117cde3063f5182a7fa7a08d1d9fa1e69885"
)
FROZEN_B04_DECISION_SHA = (
    "5d76544dae6c2f509a842baf8f8d394db339d62ffb3f9b6789091f637856815b"
)
FROZEN_B05_DECISION_SHA = (
    "feb52cb79c36abb1f1fad96f4b7f61d3b04d57e9550696d17d85b69f6b37cda2"
)
FROZEN_B06_DECISION_SHA = (
    "2d4015cf8f5c8e38d55e7fecaae48b0f07b088a23199363e332ac8b717def581"
)

_TARGET_REBAR = "be965f09-464b-4d53-9be4-d72f44d3d1ee"
_TARGET_TUNNEL_BLAST_EXCAVATION = "473d69ee-4433-487f-bc43-c35c1f2ea28f"
_TARGET_TUNNEL_WATERPROOF = "30fe37a0-0bd8-4c44-bd9b-76b3625115f5"


# ---------------------------------------------------------------------------
# Manifest / evidence contract
# ---------------------------------------------------------------------------


def test_manifest_frozen_size_and_uniqueness():
    assert len(freeze.GPT_DECISIONS) == 20
    grouped = (
        [k for k, _, _, _ in freeze._NARROWER_THAN]
        + [k for k, _, _ in freeze._POSSIBLE_RELATED]
        + [k for k, _, _ in freeze._AMBIGUOUS]
        + list(freeze._CANONICAL_GAP_KEYS)
        + list(freeze._NO_MATCH_KEYS)
    )
    assert len(grouped) == 20
    assert len(set(grouped)) == 20


def test_manifest_group_counts():
    assert len(freeze._NARROWER_THAN) == 5
    assert len(freeze._POSSIBLE_RELATED) == 1
    assert len(freeze._AMBIGUOUS) == 2
    assert len(freeze._CANONICAL_GAP_KEYS) == 7
    assert len(freeze._NO_MATCH_KEYS) == 5


def test_frozen_input_shas():
    assert freeze.FROZEN_B07_EVIDENCE_SHA == FROZEN_B07_EVIDENCE_SHA
    assert freeze.FROZEN_CANONICAL_TASK_REFERENCE_SHA == FROZEN_CANONICAL_TASK_REFERENCE_SHA


def test_manifest_review_set_matches_b07_exactly():
    b07 = load_tsv(B07_EVIDENCE_PATH)
    assert b07_evidence_sha(b07) == FROZEN_B07_EVIDENCE_SHA
    b07_review_keys = {r["review_key"] for r in b07}
    manifest_keys = set(freeze.GPT_DECISIONS)
    assert b07_review_keys == manifest_keys, (
        f"missing={b07_review_keys - manifest_keys} unexpected={manifest_keys - b07_review_keys}"
    )


def test_review_source_pair_preservation():
    """WO §2/§11: (review_key, source_key) output pairs must equal the
    frozen B07 evidence pairs — 20 / 20 exact."""
    b07 = load_tsv(B07_EVIDENCE_PATH)
    ev_pairs = {(r["review_key"], r["source_key"]) for r in b07}
    assert len(ev_pairs) == 20
    rows = freeze.build_decisions()
    out_pairs = {(r["review_key"], r["source_key"]) for r in rows}
    assert out_pairs == ev_pairs


# ---------------------------------------------------------------------------
# Deterministic freeze + row shape
# ---------------------------------------------------------------------------


def test_decision_rows_deterministic():
    a = freeze.build_decisions()
    b = freeze.build_decisions()
    assert a == b
    assert freeze.decision_sha(a) == freeze.decision_sha(b) == FROZEN_B07_DECISION_SHA


def test_decision_row_shape():
    rows = freeze.build_decisions()
    assert len(rows) == 20
    assert list(rows[0].keys()) == list(freeze.DECISION_FIELDS)
    for r in rows:
        assert r["review_authority"] == "GPT"
        assert r["review_batch"] == "B07"
        assert r["input_evidence_sha"] == FROZEN_B07_EVIDENCE_SHA
        assert r["canonical_reference_sha"] == FROZEN_CANONICAL_TASK_REFERENCE_SHA


# ---------------------------------------------------------------------------
# Census + target universe
# ---------------------------------------------------------------------------


def test_census():
    rows = freeze.build_decisions()
    seen = Counter(
        (r["gpt_semantic_decision"], r["gpt_mapping_type"]) for r in rows
    )
    assert dict(seen) == {
        ("MAP_EXISTING_CANONICAL", "NARROWER_THAN"): 5,
        ("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"): 1,
        ("AMBIGUOUS", "AMBIGUOUS"): 2,
        ("CANONICAL_GAP", ""): 7,
        ("NO_MATCH", "NO_MATCH"): 5,
    }
    assert sum(1 for r in rows if r["gpt_mapping_type"] == "EXACT_EQUIVALENT") == 0


def test_targeted_and_blank_target_counts():
    rows = freeze.build_decisions()
    targeted = [r for r in rows if r["gpt_target_canonical_id"]]
    blank = [r for r in rows if not r["gpt_target_canonical_id"]]
    assert len(targeted) == 6
    assert len(blank) == 14
    for r in targeted:
        assert r["gpt_target_canonical_name"]
        assert r["gpt_semantic_decision"] == "MAP_EXISTING_CANONICAL"


def test_target_universe_is_3_distinct_uuids():
    rows = freeze.build_decisions()
    distinct = {r["gpt_target_canonical_id"] for r in rows if r["gpt_target_canonical_id"]}
    assert distinct == {
        _TARGET_REBAR,
        _TARGET_TUNNEL_BLAST_EXCAVATION,
        _TARGET_TUNNEL_WATERPROOF,
    }


def test_ambiguous_confidence_split():
    """§6: 콘크리트타설 HIGH, 터널 특수보강 MEDIUM."""
    rows = freeze.build_decisions()
    by_key = {r["review_key"]: r for r in rows}
    concrete = by_key["fd78399b1be303af3221c5dceaf8fd6e7c517de0ecd2794cac7c83d6fce8aecd"]
    tunnel_reinf = by_key["92e8ce3fb60173e1756f7fc5d055efb81f9800313cd07b8220c3fd3d95040a38"]
    assert concrete["gpt_semantic_decision"] == "AMBIGUOUS"
    assert concrete["gpt_confidence_class"] == "HIGH"
    assert tunnel_reinf["gpt_semantic_decision"] == "AMBIGUOUS"
    assert tunnel_reinf["gpt_confidence_class"] == "MEDIUM"


def test_canonical_gap_and_no_match_shape():
    rows = freeze.build_decisions()
    by_key = {r["review_key"]: r for r in rows}
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


def test_tunnel_shotcrete_stays_canonical_gap_not_portal_shotcrete():
    """B06 guard preserved into B07: 터널 숏크리트 = CANONICAL_GAP."""
    rows = freeze.build_decisions()
    by_key = {r["review_key"]: r for r in rows}
    tunnel_shotcrete = by_key["bc063d0af6abd966eb77a18123ab0b296d70300491236412c24ceb822183a857"]
    assert tunnel_shotcrete["source_name"] == "터널 숏크리트"
    assert tunnel_shotcrete["gpt_semantic_decision"] == "CANONICAL_GAP"
    assert tunnel_shotcrete["gpt_target_canonical_id"] == ""
    assert "갱구숏크리트" not in tunnel_shotcrete["gpt_target_canonical_name"]


# ---------------------------------------------------------------------------
# Written artifact regression
# ---------------------------------------------------------------------------


def test_written_decision_when_present():
    if not DECISION_TSV.exists():
        return
    rows = load_tsv(DECISION_TSV)
    assert len(rows) == 20
    assert list(rows[0].keys()) == list(freeze.DECISION_FIELDS)
    assert freeze.decision_sha(rows) == FROZEN_B07_DECISION_SHA


def test_written_census_when_present():
    if not CENSUS_TSV.exists():
        return
    rows = load_tsv(CENSUS_TSV)
    by_bucket = {(r["gpt_semantic_decision"], r["gpt_mapping_type"]): int(r["count"]) for r in rows}
    assert by_bucket[("MAP_EXISTING_CANONICAL", "NARROWER_THAN")] == 5
    assert by_bucket[("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED")] == 1
    assert by_bucket[("AMBIGUOUS", "AMBIGUOUS")] == 2
    assert by_bucket[("CANONICAL_GAP", "")] == 7
    assert by_bucket[("NO_MATCH", "NO_MATCH")] == 5
    assert by_bucket[("TOTAL", "")] == 20
    assert freeze.census_sha(rows) == FROZEN_B07_CENSUS_SHA


def test_report_when_present():
    if not REPORT_MD.exists():
        return
    text = REPORT_MD.read_text(encoding="utf-8")
    for tag in (
        "THIS IS GPT SEMANTIC REVIEW",
        "THIS IS NOT OWNER MAPPING APPROVAL",
        "THIS IS NOT PRODUCTION MATERIALIZATION",
        "THIS DOES NOT LIFT KOSHA IDENTITY HOLD",
        "TOTAL KOSHA REVIEWED  = 620 / 620",
    ):
        assert tag in text
    assert FROZEN_B07_DECISION_SHA in text
    assert FROZEN_B07_EVIDENCE_SHA in text
    assert FROZEN_CANONICAL_TASK_REFERENCE_SHA in text
    assert "MERGE = NOT AUTHORIZED" in text


# ---------------------------------------------------------------------------
# Prior artifact immutability regression (B01-B06)
# ---------------------------------------------------------------------------


def test_prior_evidence_sha_unchanged():
    from tools.risk_map.kosha_b01_semantic_evidence import B01_EVIDENCE_PATH, b01_evidence_sha
    from tools.risk_map.kosha_b02_semantic_evidence import B02_EVIDENCE_PATH as B02EP, b02_evidence_sha
    from tools.risk_map.kosha_b03_semantic_evidence import B03_EVIDENCE_PATH as B03EP, b03_evidence_sha
    from tools.risk_map.kosha_b04_semantic_evidence import B04_EVIDENCE_PATH as B04EP, b04_evidence_sha
    from tools.risk_map.kosha_b05_semantic_evidence import B05_EVIDENCE_PATH as B05EP, b05_evidence_sha
    from tools.risk_map.kosha_b06_semantic_evidence import B06_EVIDENCE_PATH as B06EP, b06_evidence_sha
    assert b01_evidence_sha(load_tsv(B01_EVIDENCE_PATH)) == FROZEN_B01_EVIDENCE_SHA
    assert b02_evidence_sha(load_tsv(B02EP)) == FROZEN_B02_EVIDENCE_SHA
    assert b03_evidence_sha(load_tsv(B03EP)) == FROZEN_B03_EVIDENCE_SHA
    assert b04_evidence_sha(load_tsv(B04EP)) == FROZEN_B04_EVIDENCE_SHA
    assert b05_evidence_sha(load_tsv(B05EP)) == FROZEN_B05_EVIDENCE_SHA
    assert b06_evidence_sha(load_tsv(B06EP)) == FROZEN_B06_EVIDENCE_SHA


def test_prior_gpt_review_sha_unchanged():
    from tools.risk04.seed_review import universe_sha
    from tools.risk_map.kosha_b01_gpt_review_freeze import DECISION_FIELDS as B01_FIELDS
    for path, sha in (
        (Path("docs/knowledge/risk/RISK_KOSHA_B01_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B01_DECISION_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B02_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B02_DECISION_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B03_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B03_DECISION_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B04_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B04_DECISION_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B05_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B05_DECISION_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B06_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B06_DECISION_SHA),
    ):
        rows = load_tsv(path)
        assert universe_sha(rows, *B01_FIELDS) == sha, path


# ---------------------------------------------------------------------------
# WO §14 Full completion guard — recompute 620/620 union once.
# ---------------------------------------------------------------------------


def test_kosha_620_completion_union():
    review_union = set()
    for n in ("01", "02", "03", "04", "05", "06", "07"):
        path = Path(f"docs/knowledge/risk/RISK_KOSHA_B{n}_SEMANTIC_EVIDENCE_v1.tsv")
        review_union.update(r["review_key"] for r in load_tsv(path))
    assert len(review_union) == 620


# ---------------------------------------------------------------------------
# Static-analysis guard on generator
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
    import re
    src = GENERATOR.read_text(encoding="utf-8")
    assert not re.search(r"\bINSERT\s+INTO\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bUPDATE\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bDELETE\s+FROM\s+public\.", src, re.IGNORECASE)
    assert not re.search(r"\bTRUNCATE\b", src, re.IGNORECASE)
