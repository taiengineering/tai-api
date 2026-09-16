"""WO-RISK-04-REVIEW-003 Batch002 GPT freeze + remaining W_MID evidence. No semantic decision."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from tools.risk04.review_batch import batch_sha
from tools.risk04.review_decisions import GPT_MANIFEST_PATH, load_tsv
from tools.risk04.review_evidence import FROZEN_BATCH_SHA, REVIEW_INPUT_PATH, load_frozen_batch, review_input_sha
from tools.risk04.review002 import BATCH002_PATH, load_batch002, worksheet_sha
from tools.risk04.review002_decisions import (
    APPROVAL_STATE,
    BATCH002_GPT_PATH,
    BATCH002_RESULT_PATH,
    FROZEN_BATCH002_SHA,
    GPT002_FIELDS,
    batch002_manifest_sha,
    build_batch002_gpt_manifest,
    build_batch002_result,
)
from tools.risk04.review003 import (
    REVIEW003_PATH,
    WORKSHEET_FIELDS,
    build_review003,
    load_review003,
)
from tools.risk04.seed_review import universe_sha

ARTIFACTS = Path("artifacts/risk01")
REVIEW_INPUT_SHA = "c28fa67368ff3af3d05f7b771cebca455c6cf5cd94884bbff44dd1bd5087df1b"
BATCH002_GPT_SHA = "a5c124921c24a07168a587a33e874bb8760fd2519ed5cf798437ae2274e898bd"
REVIEW003_SHA = "4fb7357d0fb6396ea9f63f03d49b6c5af9c62ac7fce6f2c9b510652c5e2ee72b"
FAMILY_STATES = {
    "NO_REVIEWED_CHILDREN",
    "PARTIAL_REVIEW_SINGLE_KIND",
    "PARTIAL_REVIEW_MULTI_KIND",
    "ALL_REVIEWED_SINGLE_KIND",
    "ALL_REVIEWED_MULTI_KIND",
}


def test_frozen_batch001_and_batch002_input_unchanged():
    frozen = load_frozen_batch()
    assert batch_sha(frozen) == FROZEN_BATCH_SHA
    review_rows = list(__import__("csv").DictReader(REVIEW_INPUT_PATH.open(encoding="utf-8"), delimiter="\t"))
    assert review_input_sha(review_rows) == REVIEW_INPUT_SHA
    assert worksheet_sha(load_batch002()) == FROZEN_BATCH002_SHA
    assert BATCH002_PATH.exists()


def test_batch002_gpt_manifest_counts_and_not_approved():
    rows = load_tsv(BATCH002_GPT_PATH)
    rebuilt = build_batch002_gpt_manifest()
    assert len(rows) == 200
    assert [row["batch_no"] for row in rows] == [str(i) for i in range(201, 401)]
    assert [row["seed_proposal_key"] for row in rows] == [row["seed_proposal_key"] for row in load_batch002()]
    kinds = Counter(row["semantic_kind_override"] for row in rows)
    decisions = Counter(row["semantic_review_decision"] for row in rows)
    assert kinds["PROCESS"] == 129
    assert kinds["TASK"] == 23
    assert kinds["METHOD"] == 2
    assert kinds["MATERIAL_COMPONENT"] == 13
    assert kinds["FACILITY_EQUIPMENT"] == 16
    assert kinds["CLASSIFICATION"] == 16
    assert kinds["AMBIGUOUS"] == 1
    assert decisions["KEEP_AS_DISTINCT"] == 143
    assert decisions["MERGE_CANDIDATE"] == 9
    assert decisions["HOLD"] == 1
    assert decisions["REJECT"] == 47
    assert all(row["approval_state"] == APPROVAL_STATE for row in rows)
    assert all(
        (row["merge_candidate_keys"] == "UNRESOLVED") is (row["semantic_review_decision"] == "MERGE_CANDIDATE")
        for row in rows
    )
    assert batch002_manifest_sha(rows) == BATCH002_GPT_SHA
    assert batch002_manifest_sha(rebuilt) == BATCH002_GPT_SHA
    assert batch002_manifest_sha(build_batch002_gpt_manifest()) == BATCH002_GPT_SHA
    result = load_tsv(BATCH002_RESULT_PATH)
    assert len(result) == 200
    assert [row["semantic_kind_after"] for row in result] == [row["semantic_kind_override"] for row in rows]
    assert build_batch002_result(rebuilt)[0].keys() == dict.fromkeys(
        [
            "batch_no",
            "seed_proposal_key",
            "source_id",
            "source_key",
            "semantic_kind_before",
            "semantic_kind_after",
            "semantic_review_decision",
            "merge_candidate_keys",
            "approval_state",
        ]
    ).keys()
    assert list(rows[0].keys()) == list(GPT002_FIELDS)


def test_committed_review003_pool_and_gpt_pending():
    rows = load_review003()
    assert list(rows[0].keys()) == list(WORKSHEET_FIELDS)
    assert len(rows) == 291
    assert [row["batch_no"] for row in rows] == [str(i) for i in range(401, 692)]
    assert len({row["seed_proposal_key"] for row in rows}) == 291
    assert len({row["source_key"] for row in rows}) == 291
    assert all(row["source_id"] == "CIC_W" for row in rows)
    assert all(row["source_node_type"] == "W_MID" for row in rows)
    assert all(row["depth"] == "2" for row in rows)
    assert all(row["root_source_key"] for row in rows)
    assert all(row["current_semantic_kind"] == "AMBIGUOUS" for row in rows)
    assert all(row["current_review_decision"] == "UNREVIEWED" for row in rows)
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in rows)
    assert all(row["gpt_review_decision"] == "PENDING" for row in rows)
    assert all(row["gpt_leaf_family_policy"] == "PENDING" for row in rows)
    assert all(row["merge_candidate_keys"] == "EMPTY" for row in rows)
    assert all(row["gpt_reason"] == "EMPTY" for row in rows)
    assert all(row["children_truncated"] in {"YES", "NO"} for row in rows)
    assert all(row["reviewed_child_mechanical_state"] in FAMILY_STATES for row in rows)
    for row in rows:
        assert int(row["reviewed_child_count"]) + int(row["unreviewed_child_count"]) == int(row["direct_child_count"])
    batch001 = {row["source_key"] for row in load_tsv(GPT_MANIFEST_PATH) if row["source_id"] == "CIC_W"}
    batch002 = {row["source_key"] for row in load_tsv(BATCH002_GPT_PATH)}
    review003 = {row["source_key"] for row in rows}
    assert not review003.intersection(batch001)
    assert not review003.intersection(batch002)
    kinds = Counter()
    decisions = Counter()
    for row in list(load_tsv(GPT_MANIFEST_PATH)) + list(load_tsv(BATCH002_GPT_PATH)):
        if row["source_id"] != "CIC_W":
            continue
        kinds[row["semantic_kind_override"]] += 1
        decisions[row["semantic_review_decision"]] += 1
    assert sum(kinds.values()) == 250
    assert kinds["PROCESS"] == 153
    assert kinds["TASK"] == 23
    assert kinds["METHOD"] == 2
    assert kinds["MATERIAL_COMPONENT"] == 20
    assert kinds["FACILITY_EQUIPMENT"] == 18
    assert kinds["CLASSIFICATION"] == 17
    assert kinds["AMBIGUOUS"] == 17
    assert decisions["KEEP_AS_DISTINCT"] == 167
    assert decisions["MERGE_CANDIDATE"] == 9
    assert decisions["HOLD"] == 17
    assert decisions["REJECT"] == 57
    assert universe_sha(rows, *WORKSHEET_FIELDS) == REVIEW003_SHA


def test_review003_does_not_propagate_or_classify():
    src = Path("tools/risk04/review003.py").read_text(encoding="utf-8")
    gate = Path("tools/risk04/semantic_gate.py").read_text(encoding="utf-8")
    seed = Path("tools/risk04/seed_review.py").read_text(encoding="utf-8")
    decisions = Path("tools/risk04/review_decisions.py").read_text(encoding="utf-8")
    for blob in (src,):
        assert "openai" not in blob.lower()
        assert "embedding" not in blob.lower()
        assert "rapidfuzz" not in blob.lower()
        assert "uuid4" not in blob
        assert "HOMOGENEOUS" not in blob
        assert "SAFE_SINGLE_KIND_FAMILY" not in blob
        assert "gpt_semantic_kind\": \"PENDING" in blob
        assert "gpt_leaf_family_policy\": \"PENDING" in blob
        assert "re.compile" not in blob
    assert "HOMOGENEOUS_PROCESS_FAMILY" not in src
    rows = load_review003()
    assert any(row["root_semantic_kind"] == "PROCESS" for row in rows)
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in rows)
    assert all(row["current_semantic_kind"] == "AMBIGUOUS" for row in rows)
    assert all(row["current_review_decision"] == "UNREVIEWED" for row in rows)
    process_roots = [row for row in rows if row["root_semantic_kind"] == "PROCESS"]
    assert process_roots
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in process_roots)
    assert all(row["current_semantic_kind"] == "AMBIGUOUS" for row in process_roots)
    sibling_anchors = [row for row in rows if int(row["reviewed_sibling_count"]) > 0]
    assert sibling_anchors
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in sibling_anchors)
    assert "uuid4" not in seed
    assert "uuid4" not in gate
    assert 'APPROVAL_STATE = "NOT_APPROVED"' in decisions


@pytest.mark.skipif(
    not (ARTIFACTS / "source_c/kalis_risk_profile.csv").exists(),
    reason="local RISK-01 artifacts required to rebuild REVIEW-003",
)
def test_review003_determinism_and_mid_coverage():
    first = build_review003(ARTIFACTS)
    second = build_review003(ARTIFACTS)
    assert first["sha"] == second["sha"] == REVIEW003_SHA
    assert [row["seed_proposal_key"] for row in first["rows"]] == [
        row["seed_proposal_key"] for row in second["rows"]
    ]
    facts = first["facts"]
    assert facts["CIC_W_reviewed"] == 250
    assert facts["W_MID_total"] == 373
    assert facts["W_MID_reviewed"] == 82
    assert facts["W_MID_remaining"] == 291
    assert facts["REVIEW003"] == 291
    assert facts["NO_REVIEWED_CHILDREN"] == 239
    assert facts["PARTIAL_REVIEW_SINGLE_KIND"] == 37
    assert facts["PARTIAL_REVIEW_MULTI_KIND"] == 2
    assert facts["ALL_REVIEWED_SINGLE_KIND"] == 13
    assert facts["ALL_REVIEWED_MULTI_KIND"] == 0
    assert facts["MID_with_children"] == 245
    assert facts["MID_child_min"] == 0
    assert facts["MID_child_max"] == 6
    assert facts["GLOBAL_AUTO_CLASSIFIER"] == "NOT SAFE"
    remain = set(first["remain_keys"])
    reviewed_mids = set(first["reviewed_mid_keys"])
    assert len(remain) == 291
    assert len(reviewed_mids) == 82
    assert not remain.intersection(reviewed_mids)
    assert len(remain | reviewed_mids) == 373
    for row in first["rows"]:
        assert row["source_node_type"] == "W_MID"
        assert row["depth"] == "2"
        assert row["root_source_key"]
    assert first["source_plan"]["A"]["nodes"] == 1722
    assert first["source_plan"]["B"]["identity"] == "HOLD"
    assert first["source_plan"]["B"]["path_identities"] == 620
    assert first["source_plan"]["B"]["leaf_occurrence_sum"] == 626
    assert first["source_plan"]["C"]["unique_content"] == 30696
    assert first["source_plan"]["C"]["occurrence_sum"] == 47559
    assert universe_sha(load_review003(), *WORKSHEET_FIELDS) == first["sha"]
