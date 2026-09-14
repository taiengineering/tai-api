"""WO-RISK-04-CHG1 semantic kind gate. No approval, no canonical UUID."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.risk02.contract import SOURCE_CIC_W, SOURCE_KALIS
from tools.risk02.identity import path_source_key
from tools.risk04.review_batch import batch_sha
from tools.risk04.review_decisions import (
    APPROVAL_STATE,
    CHG1_RESULT_PATH,
    GPT_MANIFEST_PATH,
    MERGE_PAIRS,
    SEMANTIC_KINDS,
    build_gpt_manifest,
    load_tsv,
    merge_partner_map,
)
from tools.risk04.review_evidence import FROZEN_BATCH_SHA, REVIEW_INPUT_PATH, load_frozen_batch, review_input_sha
from tools.risk04.semantic_gate import (
    apply_semantic_gate,
    build_chg1_plan,
    build_gated_mappings,
)
from tools.risk04.seed_review import build_seed_proposals

ARTIFACTS = Path("artifacts/risk01")
BATCH_TSV = Path("docs/knowledge/risk/RISK04_BATCH001.tsv")
REVIEW_INPUT_SHA = "c28fa67368ff3af3d05f7b771cebca455c6cf5cd94884bbff44dd1bd5087df1b"


def _node(source_id, node_type, name, path, source_key=None):
    return {
        "source_id": source_id,
        "source_key": source_key or path_source_key(*path.split(" > ")),
        "node_type": node_type,
        "name_raw": name,
        "name_normalized": name,
        "path_normalized": path,
        "path_raw": path,
    }


def test_frozen_batch_and_review_input_unchanged():
    frozen = load_frozen_batch()
    assert batch_sha(frozen) == FROZEN_BATCH_SHA
    keys = [row["seed_proposal_key"] for row in frozen]
    assert len(keys) == 100
    assert keys == [row["seed_proposal_key"] for row in load_frozen_batch(BATCH_TSV)]
    review_rows = list(__import__("csv").DictReader(REVIEW_INPUT_PATH.open(encoding="utf-8"), delimiter="\t"))
    assert review_input_sha(review_rows) == REVIEW_INPUT_SHA
    assert [row["seed_proposal_key"] for row in review_rows] == keys


def test_gpt_manifest_counts_and_approval_not_approved():
    rows = load_tsv(GPT_MANIFEST_PATH) if GPT_MANIFEST_PATH.exists() else build_gpt_manifest()
    assert len(rows) == 100
    assert len({row["batch_no"] for row in rows}) == 100
    assert len({row["seed_proposal_key"] for row in rows}) == 100
    frozen_keys = [row["seed_proposal_key"] for row in load_frozen_batch()]
    assert [row["seed_proposal_key"] for row in rows] == frozen_keys
    counts = {}
    for row in rows:
        counts[row["semantic_review_decision"]] = counts.get(row["semantic_review_decision"], 0) + 1
    assert counts["KEEP_AS_DISTINCT"] == 49
    assert counts["MERGE_CANDIDATE"] == 22
    assert counts["HOLD"] == 17
    assert counts["REJECT"] == 12
    assert all(row["approval_state"] == APPROVAL_STATE for row in rows)
    assert set(SEMANTIC_KINDS) >= {row["semantic_kind_override"] for row in rows}


def test_merge_pairs_are_reciprocal():
    rows = load_tsv(GPT_MANIFEST_PATH) if GPT_MANIFEST_PATH.exists() else build_gpt_manifest()
    by_no = {int(row["batch_no"]): row for row in rows}
    partners = merge_partner_map()
    assert len(MERGE_PAIRS) == 11
    assert len(partners) == 22
    for left, right in MERGE_PAIRS:
        assert by_no[left]["semantic_review_decision"] == "MERGE_CANDIDATE"
        assert by_no[right]["semantic_review_decision"] == "MERGE_CANDIDATE"
        assert by_no[left]["merge_partner_batch"] == str(right)
        assert by_no[right]["merge_partner_batch"] == str(left)
        assert by_no[left]["semantic_kind_override"] == "TASK"


def test_reviewed_kalis_fixture_decisions():
    rows = load_tsv(GPT_MANIFEST_PATH) if GPT_MANIFEST_PATH.exists() else build_gpt_manifest()
    by_no = {int(row["batch_no"]): row for row in rows}
    assert by_no[1]["semantic_review_decision"] == "MERGE_CANDIDATE"
    assert by_no[5]["semantic_review_decision"] == "MERGE_CANDIDATE"
    assert by_no[31]["semantic_review_decision"] == "HOLD"
    assert by_no[32]["semantic_review_decision"] == "REJECT"
    assert by_no[39]["semantic_review_decision"] == "REJECT"
    assert by_no[50]["semantic_review_decision"] == "KEEP_AS_DISTINCT"


def test_kalis_multi_parent_is_flag_not_hold():
    nodes = [
        _node(SOURCE_KALIS, "TASK", "설치작업", "토목 > 가설공사 > 설치작업"),
        _node(SOURCE_KALIS, "TASK", "설치작업", "건축 > 가설공사 > 설치작업"),
    ]
    proposals = apply_semantic_gate(build_seed_proposals(nodes), manifest=[])
    assert all(row["metadata"]["same_name_multi_parent"] is True for row in proposals)
    assert all(row["review_status"] != "HOLD" for row in proposals)
    assert all(row["semantic_kind"] == "TASK" for row in proposals)
    mappings = build_gated_mappings(proposals)
    assert all(row["recommended_mapping_type"] != "APPROVED" for row in mappings)


def test_unreviewed_cic_w_is_ambiguous_not_process():
    node = _node(SOURCE_CIC_W, "W_LEAF", "ALC블록", "조적공사 > ALC공사 > ALC블록", source_key="4141")
    proposals = apply_semantic_gate(build_seed_proposals([node]), manifest=[])
    assert proposals[0]["semantic_kind"] == "AMBIGUOUS"
    assert proposals[0]["seed_candidate_state"] == "PENDING_SEMANTIC_REVIEW"
    mapping = build_gated_mappings(proposals)[0]
    assert mapping["target_seed_proposal_key"] is None
    assert mapping["recommended_mapping_type"] != "POSSIBLE_RELATED"
    assert mapping["recommended_mapping_type"] != "NO_MATCH"


def test_chg1_no_llm_or_uuid():
    blob = Path("tools/risk04/semantic_gate.py").read_text(encoding="utf-8")
    blob += Path("tools/risk04/review_decisions.py").read_text(encoding="utf-8")
    assert "openai" not in blob.lower()
    assert "embedding" not in blob.lower()
    assert "rapidfuzz" not in blob.lower()
    assert "uuid4" not in blob
    assert "datetime" not in blob.lower()


@pytest.mark.skipif(
    not (ARTIFACTS / "source_c/kalis_risk_profile.csv").exists(),
    reason="local RISK-01 artifacts required for CHG1 census",
)
def test_chg1_full_gate_census_and_determinism():
    first = build_chg1_plan(ARTIFACTS)
    second = build_chg1_plan(ARTIFACTS)
    dist = first["distribution"]
    assert dist["source_proposal_universe"] == 3103
    assert dist["CIC_W"] == 1722
    assert dist["CIC_W_reviewed"] == 50
    assert dist["CIC_W_unreviewed"] == 1672
    assert dist["CIC_W_unreviewed_PROCESS"] == 0
    assert dist["CIC_W_unreviewed_AMBIGUOUS"] == 1672
    assert dist["CIC_W_reviewed_PROCESS"] == 24
    assert dist["CIC_W_reviewed_AMBIGUOUS"] == 16
    assert dist["CIC_W_reviewed_MATERIAL_COMPONENT"] == 7
    assert dist["CIC_W_reviewed_FACILITY_EQUIPMENT"] == 2
    assert dist["CIC_W_reviewed_CLASSIFICATION"] == 1
    assert dist["KALIS"] == 761
    assert dist["KALIS_same_name_multi_parent_auto_HOLD"] == 0
    assert dist["AUTO_APPROVED"] == 0
    assert dist["AUTO_MERGED"] == 0
    assert dist["OWNER_APPROVED_SEEDS"] == 0
    assert dist["CANONICAL_UUID_CREATED"] == 0
    assert first["mapping_approval_coverage"] == 0
    assert first["source_relation_review_universe"] == 3103
    assert first["semantic_sha"] == second["semantic_sha"]
    assert first["relation_sha"] == second["relation_sha"]
    assert first["source_plan"]["A"]["nodes"] == 1722
    assert first["source_plan"]["B"]["rows"] == 626
    assert first["source_plan"]["B"]["path_identities"] == 620
    assert first["source_plan"]["B"]["identity"] == "HOLD"
    assert first["source_plan"]["B"]["leaf_occurrence_sum"] == 626
    assert first["source_plan"]["C"]["unique_content"] == 30696
    assert first["source_plan"]["C"]["occurrence_sum"] == 47559
    committed = load_tsv(CHG1_RESULT_PATH)
    assert len(committed) == 100
    assert all(row["approval_state"] == APPROVAL_STATE for row in committed)
    result_by_key = {row["seed_proposal_key"]: row for row in first["result_rows"]}
    for row in committed:
        live = result_by_key[row["seed_proposal_key"]]
        assert row["semantic_kind_after"] == live["semantic_kind_after"]
        assert row["semantic_review_decision"] == live["semantic_review_decision"]
        assert row["seed_candidate_state"] == live["seed_candidate_state"]
    ambiguous = [row for row in first["mappings"] if row["evidence"].get("semantic_kind") == "AMBIGUOUS"]
    assert ambiguous
    assert all(row["recommended_mapping_type"] != "NO_MATCH" for row in ambiguous)
    assert all(row["target_seed_proposal_key"] is None for row in ambiguous)
    material = [
        row
        for row in first["proposals"]
        if row["semantic_kind"] == "MATERIAL_COMPONENT"
    ]
    assert len(material) == 7
    material_keys = {row["seed_proposal_key"] for row in material}
    for mapping in first["mappings"]:
        if mapping["source_id"] == SOURCE_CIC_W and any(
            p["origin_source_key"] == mapping["source_key"] for p in material
        ):
            assert mapping["target_seed_proposal_key"] is None
            assert mapping["recommended_mapping_type"] != "POSSIBLE_RELATED"
    del material_keys
    assert not any(row["review_status"] == "APPROVED" for row in first["mappings"])
    assert not any(row.get("canonical_uuid") for row in first["proposals"])
