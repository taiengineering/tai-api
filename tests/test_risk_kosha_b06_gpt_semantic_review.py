"""WO-RISK-KOSHA-B06-REVIEW-001 B06 GPT semantic decision freeze tests. skip = 0."""
from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from tools.risk04.review_decisions import load_tsv
from tools.risk_map import kosha_b06_gpt_review_freeze as freeze
from tools.risk_map.kosha_b06_semantic_evidence import B06_EVIDENCE_PATH, b06_evidence_sha

GENERATOR = Path("tools/risk_map/kosha_b06_gpt_review_freeze.py")
DECISION_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B06_GPT_SEMANTIC_REVIEW_v1.tsv")
CENSUS_TSV = Path("docs/knowledge/risk/RISK_KOSHA_B06_GPT_SEMANTIC_CENSUS_v1.tsv")
REPORT_MD = Path("docs/knowledge/risk/OBJ_risk-kosha-b06-gpt-semantic-review_v1.md")

FROZEN_B06_EVIDENCE_SHA = (
    "b0df9c2e77642184bc98fa67bc94e5073a41913ccc9a867da1ec5bf3bbfc34c2"
)
FROZEN_CANONICAL_TASK_REFERENCE_SHA = (
    "a22f3a83f3cc2563554eb04b71ac8afc1faff44e3a6a594dd265ff04baafa2a6"
)
FROZEN_B06_DECISION_SHA = (
    "2d4015cf8f5c8e38d55e7fecaae48b0f07b088a23199363e332ac8b717def581"
)
FROZEN_B06_CENSUS_SHA = (
    "3d006b980516732fa8bcef92d654b0b3ce20f31a2badb32a01ca3bb678bc3e28"
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
FROZEN_B05_EVIDENCE_SHA = (
    "67a0a8a09af59772c61cad93af3b2dd3fcf818dfde794e972ea0c74fb0fc3ed0"
)
FROZEN_B05_DECISION_SHA = (
    "feb52cb79c36abb1f1fad96f4b7f61d3b04d57e9550696d17d85b69f6b37cda2"
)

# B06 canonical targets (7 distinct)
_TARGET_SITE_GRADING = "5bb130b1-f1ab-4cdb-86d8-9b0985bf9a81"      # 일반부지정지
_TARGET_REBAR = "be965f09-464b-4d53-9be4-d72f44d3d1ee"             # 철근가공및조립
_TARGET_TUNNEL_BLAST_EXCAVATION = "473d69ee-4433-487f-bc43-c35c1f2ea28f"  # 발파굴착
_TARGET_TUNNEL_WATERPROOF = "30fe37a0-0bd8-4c44-bd9b-76b3625115f5"        # 터널방수
_TARGET_TOPSOIL = "a7106b20-76ca-427f-aa45-2f0b1d417f15"           # 표토제거
_TARGET_GROUTING_DRILL = "0ca62c6e-768e-4f68-8198-9abed44589b1"    # 그라우팅천공
_TARGET_CONCRETE_LINING = "892b579d-42bf-4c3e-8a71-e37d8ce00e1b"   # 현장타설콘크리트라이닝


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
    assert len(freeze._NARROWER_THAN) == 10
    assert len(freeze._POSSIBLE_RELATED) == 6
    assert len(freeze._AMBIGUOUS) == 11
    assert len(freeze._CANONICAL_GAP_KEYS) == 29
    assert len(freeze._NO_MATCH_KEYS) == 44


def test_frozen_input_shas():
    assert freeze.FROZEN_B06_EVIDENCE_SHA == FROZEN_B06_EVIDENCE_SHA
    assert freeze.FROZEN_CANONICAL_TASK_REFERENCE_SHA == FROZEN_CANONICAL_TASK_REFERENCE_SHA


def test_manifest_review_set_matches_b06_exactly():
    b06 = load_tsv(B06_EVIDENCE_PATH)
    assert b06_evidence_sha(b06) == FROZEN_B06_EVIDENCE_SHA
    b06_review_keys = {r["review_key"] for r in b06}
    manifest_keys = set(freeze.GPT_DECISIONS)
    assert b06_review_keys == manifest_keys, (
        f"missing={b06_review_keys - manifest_keys} unexpected={manifest_keys - b06_review_keys}"
    )


def test_decision_rows_deterministic():
    a = freeze.build_decisions()
    b = freeze.build_decisions()
    assert a == b
    assert freeze.decision_sha(a) == freeze.decision_sha(b) == FROZEN_B06_DECISION_SHA


def test_decision_row_shape():
    rows = freeze.build_decisions()
    assert len(rows) == 100
    assert list(rows[0].keys()) == list(freeze.DECISION_FIELDS)
    for r in rows:
        assert r["review_authority"] == "GPT"
        assert r["review_batch"] == "B06"
        assert r["input_evidence_sha"] == FROZEN_B06_EVIDENCE_SHA
        assert r["canonical_reference_sha"] == FROZEN_CANONICAL_TASK_REFERENCE_SHA


def test_census():
    rows = freeze.build_decisions()
    seen = Counter(
        (r["gpt_semantic_decision"], r["gpt_mapping_type"]) for r in rows
    )
    assert dict(seen) == {
        ("MAP_EXISTING_CANONICAL", "NARROWER_THAN"): 10,
        ("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED"): 6,
        ("AMBIGUOUS", "AMBIGUOUS"): 11,
        ("CANONICAL_GAP", ""): 29,
        ("NO_MATCH", "NO_MATCH"): 44,
    }
    assert sum(1 for r in rows if r["gpt_mapping_type"] == "EXACT_EQUIVALENT") == 0


def test_targeted_and_blank_target_counts():
    rows = freeze.build_decisions()
    targeted = [r for r in rows if r["gpt_target_canonical_id"]]
    blank = [r for r in rows if not r["gpt_target_canonical_id"]]
    assert len(targeted) == 16
    assert len(blank) == 84
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
            assert r["gpt_target_canonical_id"] in valid, r["review_key"]


def test_target_universe_is_7_distinct_uuids():
    rows = freeze.build_decisions()
    distinct = {r["gpt_target_canonical_id"] for r in rows if r["gpt_target_canonical_id"]}
    assert distinct == {
        _TARGET_SITE_GRADING,
        _TARGET_REBAR,
        _TARGET_TUNNEL_BLAST_EXCAVATION,  # NEW in B06
        _TARGET_TUNNEL_WATERPROOF,        # NEW in B06
        _TARGET_TOPSOIL,
        _TARGET_GROUTING_DRILL,
        _TARGET_CONCRETE_LINING,
    }


def test_specific_gpt_targets_match_manifest():
    """§5 NARROWER_THAN + §6 POSSIBLE_RELATED — verbatim WO bindings by review_key."""
    rows = freeze.build_decisions()
    by_key = {r["review_key"]: r for r in rows}

    # §5 NARROWER_THAN (10)
    assert by_key["0fc81a44983f02fb0813bf00f72b4c31c598c36acedba4574b7c0df4d295ccf9"]["gpt_target_canonical_id"] == _TARGET_SITE_GRADING
    assert by_key["4d02f51a104ce4e5d03b78619a3583f453fc4257553c3c3eadb2310415360612"]["gpt_target_canonical_id"] == _TARGET_REBAR
    assert by_key["9d54c7749d12fab41798527831ff937f89024e5967b1d53eb632738c8783b6fe"]["gpt_target_canonical_id"] == _TARGET_TUNNEL_BLAST_EXCAVATION
    assert by_key["f7d56f58e49b5750a233b61544f079a11d1d38e1de0b5405d98790ba5bbd59e9"]["gpt_target_canonical_id"] == _TARGET_TUNNEL_BLAST_EXCAVATION
    assert by_key["b9d472e5e46bc3916f97415202c996d455d8ea24619e02e057716b14f6bb6117"]["gpt_target_canonical_id"] == _TARGET_TUNNEL_BLAST_EXCAVATION
    assert by_key["f34ddc13a28da5a08134244516427b291eaedb860b115c3e9cdd97e0de23dae6"]["gpt_target_canonical_id"] == _TARGET_TUNNEL_WATERPROOF
    assert by_key["61f1c0640b68ae4cdca7daae0a030ac6eb44b2b5be43dca5504517487fb6fd6e"]["gpt_target_canonical_id"] == _TARGET_CONCRETE_LINING
    assert by_key["9088a846120cb59ea4e7c2846405725694ad5b4a0213239f7d29c647563bf7ed"]["gpt_target_canonical_id"] == _TARGET_CONCRETE_LINING
    assert by_key["4b7f35075945ac8574382ea86b452481102745416a47c7160c069a2b8c2f3185"]["gpt_target_canonical_id"] == _TARGET_TUNNEL_BLAST_EXCAVATION
    assert by_key["5c0e45143e5a61b513dbd8599311863f3a8437c6cb93e2d6ce9b27afe30e18da"]["gpt_target_canonical_id"] == _TARGET_TUNNEL_BLAST_EXCAVATION

    # §6 POSSIBLE_RELATED (6)
    assert by_key["b2f7a39d6bc5a8eddfd2f15103d407c0559f3f6331cd5a685a26af1c8775a71d"]["gpt_target_canonical_id"] == _TARGET_REBAR
    assert by_key["2735eaa49ed2cc102f9e7b8c68804e3f50c88a4530078c1a2b9e80d5257ea48d"]["gpt_target_canonical_id"] == _TARGET_TOPSOIL
    assert by_key["f82d63a60f213d46e42cdd7ec2d7480047d3060b53246db105f8b5b2b228c06d"]["gpt_target_canonical_id"] == _TARGET_TOPSOIL
    assert by_key["b7f85fbe92d08c80b666a5eaecd48353672a011ec00e953d7ce40e883893a3b9"]["gpt_target_canonical_id"] == _TARGET_GROUTING_DRILL
    assert by_key["2737ea01efcec70667b65716ed9cf4c6376f7e6871dbaeeea7f2e0656d1674db"]["gpt_target_canonical_id"] == _TARGET_TUNNEL_BLAST_EXCAVATION
    assert by_key["ac53a96e16248a1aec21547d317bbd250bc2a6e5b3b4ee4535a589a60f80dc25"]["gpt_target_canonical_id"] == _TARGET_TUNNEL_BLAST_EXCAVATION


def test_ambiguous_confidence_high_keys():
    """§7 HIGH: 콘크리트타설 + 굴착. Other 9 = MEDIUM."""
    rows = freeze.build_decisions()
    by_key = {r["review_key"]: r for r in rows}
    high_keys = {
        "58a88edbd40a2063b2a0d97f2f9def1608cdb984c4aa7c524798c4827e8bba01",  # 콘크리트타설
        "f556d0f56dce9fa3be35cef61a4c35e92c55fddfe2b98d1c3ef3acf031e12cff",  # 굴착
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


# ---------------------------------------------------------------------------
# §22 Tunnel-specific semantic guards
# ---------------------------------------------------------------------------


def test_tunnel_blast_family_maps_to_blast_excavation_narrower():
    """터널 발파 / 터널 장약 / 터널 천공 → 발파굴착 (NARROWER_THAN)."""
    rows = freeze.build_decisions()
    by_name = {(r["project_kind"], r["source_name"]): r for r in rows}
    tunnel_blast_family = [
        ("지하철", "터널 발파"),
        ("지하철", "터널 장약"),
        ("지하철", "터널 천공"),
    ]
    for pk, name in tunnel_blast_family:
        r = by_name[(pk, name)]
        assert r["gpt_semantic_decision"] == "MAP_EXISTING_CANONICAL", name
        assert r["gpt_mapping_type"] == "NARROWER_THAN", name
        assert r["gpt_target_canonical_id"] == _TARGET_TUNNEL_BLAST_EXCAVATION, name


def test_tunnel_waterproof_sheet_narrower_of_tunnel_waterproof():
    """터널 방수쉬트설치 → 터널방수 (NARROWER_THAN)."""
    rows = freeze.build_decisions()
    by_name = {(r["project_kind"], r["source_name"]): r for r in rows}
    r = by_name[("지하철", "터널 방수쉬트설치")]
    assert r["gpt_semantic_decision"] == "MAP_EXISTING_CANONICAL"
    assert r["gpt_mapping_type"] == "NARROWER_THAN"
    assert r["gpt_target_canonical_id"] == _TARGET_TUNNEL_WATERPROOF


def test_lining_formwork_narrower_of_cast_in_place_concrete_lining():
    """라이닝거푸집 설치 / 해체 → 현장타설콘크리트라이닝 (NARROWER_THAN)."""
    rows = freeze.build_decisions()
    by_name = {(r["project_kind"], r["source_name"]): r for r in rows}
    for name in ("라이닝거푸집 설치", "라이닝거푸집 해체"):
        r = by_name[("터널", name)]
        assert r["gpt_semantic_decision"] == "MAP_EXISTING_CANONICAL", name
        assert r["gpt_mapping_type"] == "NARROWER_THAN", name
        assert r["gpt_target_canonical_id"] == _TARGET_CONCRETE_LINING, name


def test_tunnel_shotcrete_is_canonical_gap_not_portal_shotcrete():
    """터널 숏크리트 = CANONICAL_GAP, and MUST NOT bind to 갱구숏크리트.

    Portal shotcrete (갱구숏크리트) covers only the portal, not the full
    tunnel bore; treating 터널 숏크리트 as a specialization would be an
    over-promotion. Guard reserved for future name-based misbindings.
    """
    rows = freeze.build_decisions()
    by_name = {r["source_name"]: r for r in rows}
    r = by_name["터널 숏크리트"]
    assert r["gpt_semantic_decision"] == "CANONICAL_GAP"
    assert r["gpt_target_canonical_id"] == ""
    assert r["gpt_target_canonical_name"] == ""
    # Anti-promotion guard: the reference name for 갱구숏크리트 must not appear
    # anywhere on this row.
    for f in ("gpt_target_canonical_id", "gpt_target_canonical_name"):
        assert "갱구숏크리트" not in r[f]


# ---------------------------------------------------------------------------
# Written artifact regression when present
# ---------------------------------------------------------------------------


def test_written_decision_when_present():
    if not DECISION_TSV.exists():
        return
    rows = load_tsv(DECISION_TSV)
    assert len(rows) == 100
    assert list(rows[0].keys()) == list(freeze.DECISION_FIELDS)
    assert freeze.decision_sha(rows) == FROZEN_B06_DECISION_SHA


def test_written_census_when_present():
    if not CENSUS_TSV.exists():
        return
    rows = load_tsv(CENSUS_TSV)
    by_bucket = {(r["gpt_semantic_decision"], r["gpt_mapping_type"]): int(r["count"]) for r in rows}
    assert by_bucket[("MAP_EXISTING_CANONICAL", "NARROWER_THAN")] == 10
    assert by_bucket[("MAP_EXISTING_CANONICAL", "POSSIBLE_RELATED")] == 6
    assert by_bucket[("AMBIGUOUS", "AMBIGUOUS")] == 11
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
        "NO_MATCH IS REVIEW-ONLY UNTIL OWNER APPROVAL",
    ):
        assert tag in text
    assert FROZEN_B06_DECISION_SHA in text
    assert FROZEN_B06_EVIDENCE_SHA in text
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


def test_source_side_fields_echoed_from_b06_evidence():
    b06 = {r["review_key"]: r for r in load_tsv(B06_EVIDENCE_PATH)}
    rows = freeze.build_decisions()
    for r in rows:
        src = b06[r["review_key"]]
        for f in ("review_key", "source_key", "project_kind", "work_type", "source_name", "source_path"):
            assert r[f] == src[f], f


# ---------------------------------------------------------------------------
# Prior artifact immutability regression (B01-B05)
# ---------------------------------------------------------------------------


def test_prior_evidence_sha_unchanged():
    from tools.risk_map.kosha_b01_semantic_evidence import B01_EVIDENCE_PATH, b01_evidence_sha
    from tools.risk_map.kosha_b02_semantic_evidence import B02_EVIDENCE_PATH as B02EP, b02_evidence_sha
    from tools.risk_map.kosha_b03_semantic_evidence import B03_EVIDENCE_PATH as B03EP, b03_evidence_sha
    from tools.risk_map.kosha_b04_semantic_evidence import B04_EVIDENCE_PATH as B04EP, b04_evidence_sha
    from tools.risk_map.kosha_b05_semantic_evidence import B05_EVIDENCE_PATH as B05EP, b05_evidence_sha
    assert b01_evidence_sha(load_tsv(B01_EVIDENCE_PATH)) == FROZEN_B01_EVIDENCE_SHA
    assert b02_evidence_sha(load_tsv(B02EP)) == FROZEN_B02_EVIDENCE_SHA
    assert b03_evidence_sha(load_tsv(B03EP)) == FROZEN_B03_EVIDENCE_SHA
    assert b04_evidence_sha(load_tsv(B04EP)) == FROZEN_B04_EVIDENCE_SHA
    assert b05_evidence_sha(load_tsv(B05EP)) == FROZEN_B05_EVIDENCE_SHA


def test_prior_gpt_review_sha_unchanged():
    from tools.risk04.seed_review import universe_sha
    from tools.risk_map.kosha_b01_gpt_review_freeze import DECISION_FIELDS as B01_FIELDS
    for path, sha in (
        (Path("docs/knowledge/risk/RISK_KOSHA_B01_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B01_DECISION_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B02_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B02_DECISION_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B03_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B03_DECISION_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B04_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B04_DECISION_SHA),
        (Path("docs/knowledge/risk/RISK_KOSHA_B05_GPT_SEMANTIC_REVIEW_v1.tsv"), FROZEN_B05_DECISION_SHA),
    ):
        rows = load_tsv(path)
        assert universe_sha(rows, *B01_FIELDS) == sha, path
