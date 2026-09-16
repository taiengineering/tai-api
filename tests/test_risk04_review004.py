"""WO-RISK-04-REVIEW-004 W_MID GPT freeze + W_LEAF full-review routing. No leaf semantic decision."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from tools.risk04.review_batch import batch_sha
from tools.risk04.review_decisions import GPT_MANIFEST_PATH, load_tsv
from tools.risk04.review_evidence import FROZEN_BATCH_SHA, REVIEW_INPUT_PATH, load_frozen_batch, review_input_sha
from tools.risk04.review002 import BATCH002_PATH, load_batch002, worksheet_sha
from tools.risk04.review002_decisions import BATCH002_GPT_PATH, FROZEN_BATCH002_SHA
from tools.risk04.review003 import REVIEW003_PATH, WORKSHEET_FIELDS, load_review003
from tools.risk04.review003_decisions import (
    APPROVAL_STATE,
    FROZEN_REVIEW003_SHA,
    GPT003_FIELDS,
    REVIEW003_GPT_PATH,
    REVIEW003_RESULT_PATH,
    build_review003_gpt_manifest,
    review003_manifest_sha,
)
from tools.risk04.review004_leaf_routing import (
    BATCH_LABELS,
    BATCH_SIZES,
    LEAF_FIELDS,
    LEAF_PATHS,
    build_leaf_routing,
    load_leaf_batch,
    load_leaf_universe,
)
from tools.risk04.seed_review import universe_sha

ARTIFACTS = Path("artifacts/risk01")
REVIEW_INPUT_SHA = "c28fa67368ff3af3d05f7b771cebca455c6cf5cd94884bbff44dd1bd5087df1b"
W_MID_MANIFEST_SHA = "4acfce3392d6dd805a85f95fe19b8a72864f23c5c1e74f0f043ba8fa37ab3436"
LEAF_ROUTING_SHA = "5e1630916ad9004d9e854bbce82fce62061b4c181eec1eb4f5021a48d5c2a2fc"
BATCH_SHAS = {
    "004A": "23e15185bc004c62432f8044596995a1106759d2f1febe399bd76c6b9265c894",
    "004B": "bfe98e52c4e6f812a09e44260b4f23bc7020bdbefa9a0c3eece281ab096b858c",
    "004C": "665a3c376c218315d4adceb32ff3d5a81da72af90eda76442d823fd6ac8e1f72",
    "004D": "f0cdea5c724fb5c7d66104a3fe72aa3aceaa550c9239fb5fe065eb58d3cfa047",
    "004E": "2a2a973666b7144045272adbcd8a3456218e83e5f5c4c876fc94480c8c20ab64",
    "004F": "c8ddb8b0e997005b3d6fe40f4b88ad1590e12012ba811f46c688773b2df3e100",
}


def test_frozen_prior_evidence_unchanged():
    frozen = load_frozen_batch()
    assert batch_sha(frozen) == FROZEN_BATCH_SHA
    review_rows = list(__import__("csv").DictReader(REVIEW_INPUT_PATH.open(encoding="utf-8"), delimiter="\t"))
    assert review_input_sha(review_rows) == REVIEW_INPUT_SHA
    assert worksheet_sha(load_batch002()) == FROZEN_BATCH002_SHA
    assert BATCH002_PATH.exists()
    assert universe_sha(load_review003(), *WORKSHEET_FIELDS) == FROZEN_REVIEW003_SHA
    assert REVIEW003_PATH.exists()


def test_review003_gpt_manifest_counts():
    rows = load_tsv(REVIEW003_GPT_PATH)
    assert list(rows[0].keys()) == list(GPT003_FIELDS)
    assert len(rows) == 291
    assert [row["batch_no"] for row in rows] == [str(i) for i in range(401, 692)]
    assert len({row["batch_no"] for row in rows}) == 291
    assert len({row["seed_proposal_key"] for row in rows}) == 291
    kinds = Counter(row["semantic_kind_after"] for row in rows)
    decisions = Counter(row["semantic_review_decision"] for row in rows)
    policies = Counter(row["gpt_leaf_family_policy"] for row in rows)
    assert kinds["PROCESS"] == 230
    assert kinds["TASK"] == 2
    assert kinds["METHOD"] == 2
    assert kinds["MATERIAL_COMPONENT"] == 17
    assert kinds["FACILITY_EQUIPMENT"] == 29
    assert kinds["CLASSIFICATION"] == 11
    assert kinds["AMBIGUOUS"] == 0
    assert decisions["KEEP_AS_DISTINCT"] == 212
    assert decisions["MERGE_CANDIDATE"] == 20
    assert decisions["HOLD"] == 0
    assert decisions["REJECT"] == 59
    assert policies["SAFE_SINGLE_KIND_FAMILY"] == 13
    assert policies["MIXED_FAMILY"] == 2
    assert policies["INSUFFICIENT_EVIDENCE"] == 230
    assert policies["NO_CHILDREN"] == 46
    assert sum(policies.values()) == 291
    assert all(row["approval_state"] == APPROVAL_STATE for row in rows)
    merge_rows = [row for row in rows if row["semantic_review_decision"] == "MERGE_CANDIDATE"]
    assert len(merge_rows) == 20
    assert all(row["merge_candidate_keys"] not in {"", "EMPTY"} for row in merge_rows)
    assert all(
        row["merge_candidate_keys"] == "EMPTY"
        for row in rows
        if row["semantic_review_decision"] != "MERGE_CANDIDATE"
    )
    assert review003_manifest_sha(rows) == W_MID_MANIFEST_SHA
    result = load_tsv(REVIEW003_RESULT_PATH)
    assert len(result) == 291
    assert [row["semantic_kind_after"] for row in result] == [row["semantic_kind_after"] for row in rows]
    assert [row["gpt_leaf_family_policy"] for row in result] == [row["gpt_leaf_family_policy"] for row in rows]


def test_cicw_reviewed_aggregate_541():
    rows = []
    for path in (GPT_MANIFEST_PATH, BATCH002_GPT_PATH, REVIEW003_GPT_PATH):
        for row in load_tsv(path):
            if row["source_id"] != "CIC_W":
                continue
            kind = row.get("semantic_kind_after") or row["semantic_kind_override"]
            rows.append((row["source_key"], kind, row["semantic_review_decision"]))
    assert len({key for key, _, _ in rows}) == 541
    kinds = Counter(kind for _, kind, _ in rows)
    decisions = Counter(decision for _, _, decision in rows)
    assert kinds["PROCESS"] == 383
    assert kinds["TASK"] == 25
    assert kinds["METHOD"] == 4
    assert kinds["MATERIAL_COMPONENT"] == 37
    assert kinds["FACILITY_EQUIPMENT"] == 47
    assert kinds["CLASSIFICATION"] == 28
    assert kinds["AMBIGUOUS"] == 17
    assert decisions["KEEP_AS_DISTINCT"] == 379
    assert decisions["MERGE_CANDIDATE"] == 29
    assert decisions["HOLD"] == 17
    assert decisions["REJECT"] == 116
    assert sum(decisions.values()) == 541


def test_leaf_routing_universe_and_partition():
    rows = load_leaf_universe()
    assert list(rows[0].keys()) == list(LEAF_FIELDS)
    assert len(rows) == 1181
    assert [row["review_no"] for row in rows] == [str(i) for i in range(692, 1873)]
    assert len({row["seed_proposal_key"] for row in rows}) == 1181
    assert all(row["source_id"] == "CIC_W" for row in rows)
    assert all(row["current_semantic_kind"] == "AMBIGUOUS" for row in rows)
    assert all(row["current_review_decision"] == "UNREVIEWED" for row in rows)
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in rows)
    assert all(row["gpt_review_decision"] == "PENDING" for row in rows)
    assert all(row["merge_candidate_keys"] == "EMPTY" for row in rows)
    assert all(row["gpt_reason"] == "EMPTY" for row in rows)
    assert all(row["parent_source_key"] for row in rows)
    assert all(row["root_source_key"] for row in rows)
    batches = [load_leaf_batch(path) for path in LEAF_PATHS]
    assert [len(batch) for batch in batches] == list(BATCH_SIZES)
    assert [len(batch) for batch in batches] == [200, 200, 200, 200, 200, 181]
    keys = [{row["seed_proposal_key"] for row in batch} for batch in batches]
    for i, left in enumerate(keys):
        for right in keys[i + 1 :]:
            assert not left.intersection(right)
    assert len(set().union(*keys)) == 1181
    reviewed = set()
    for path in (GPT_MANIFEST_PATH, BATCH002_GPT_PATH, REVIEW003_GPT_PATH):
        for row in load_tsv(path):
            if row["source_id"] == "CIC_W":
                reviewed.add(row["source_key"])
    assert len(reviewed) == 541
    assert not {row["source_key"] for row in rows}.intersection(reviewed)
    assert universe_sha(rows, *LEAF_FIELDS) == LEAF_ROUTING_SHA
    for label, path in zip(BATCH_LABELS, LEAF_PATHS, strict=True):
        assert universe_sha(load_leaf_batch(path), *LEAF_FIELDS) == BATCH_SHAS[label]
    process_parents = [row for row in rows if row["parent_semantic_kind"] == "PROCESS"]
    assert process_parents
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in process_parents)
    assert "SAFE_SINGLE_KIND_FAMILY" not in {row["parent_leaf_family_policy"] for row in rows}
    assert "NO_CHILDREN" not in {row["parent_leaf_family_policy"] for row in rows}


def test_review004_does_not_propagate_or_classify():
    src = Path("tools/risk04/review004_leaf_routing.py").read_text(encoding="utf-8")
    decisions = Path("tools/risk04/review003_decisions.py").read_text(encoding="utf-8")
    gate = Path("tools/risk04/semantic_gate.py").read_text(encoding="utf-8")
    seed = Path("tools/risk04/seed_review.py").read_text(encoding="utf-8")
    frozen = Path("tools/risk04/review_decisions.py").read_text(encoding="utf-8")
    b002 = Path("tools/risk04/review002_decisions.py").read_text(encoding="utf-8")
    for blob in (src, decisions):
        assert "openai" not in blob.lower()
        assert "embedding" not in blob.lower()
        assert "rapidfuzz" not in blob.lower()
        assert "uuid4" not in blob
        assert "re.compile" not in blob
        assert "HOMOGENEOUS" not in blob
    assert 'gpt_semantic_kind": "PENDING"' in src
    assert "Not a depth/parent/name classifier" in decisions
    assert "uuid4" not in gate
    assert "uuid4" not in seed
    assert 'APPROVAL_STATE = "NOT_APPROVED"' in frozen
    assert "FROZEN_BATCH002_SHA" in b002


@pytest.mark.skipif(
    not (ARTIFACTS / "source_c/kalis_risk_profile.csv").exists(),
    reason="local RISK-01 artifacts required to rebuild REVIEW-004",
)
def test_review004_determinism_and_hierarchy():
    first_mid = build_review003_gpt_manifest(ARTIFACTS)
    second_mid = build_review003_gpt_manifest(ARTIFACTS)
    assert review003_manifest_sha(first_mid) == review003_manifest_sha(second_mid) == W_MID_MANIFEST_SHA
    first = build_leaf_routing(ARTIFACTS)
    second = build_leaf_routing(ARTIFACTS)
    assert first["sha"] == second["sha"] == LEAF_ROUTING_SHA
    assert first["batch_shas"] == second["batch_shas"]
    assert [row["seed_proposal_key"] for row in first["rows"]] == [
        row["seed_proposal_key"] for row in second["rows"]
    ]
    facts = first["facts"]
    assert facts["CIC_W_reviewed"] == 541
    assert facts["W_ROOT_reviewed"] == 62
    assert facts["W_MID_reviewed"] == 373
    assert facts["W_LEAF_reviewed"] == 106
    assert facts["W_LEAF_remaining"] == 1181
    assert facts["unreviewed_PROCESS"] == 0
    assert facts["unreviewed_AMBIGUOUS"] == 1181
    assert facts["GLOBAL_AUTO_CLASSIFIER"] == "NOT SAFE"
    assert facts["batch_sizes"] == [200, 200, 200, 200, 200, 181]
    assert first["source_plan"]["A"]["nodes"] == 1722
    assert first["source_plan"]["B"]["identity"] == "HOLD"
    assert first["source_plan"]["B"]["path_identities"] == 620
    assert first["source_plan"]["B"]["leaf_occurrence_sum"] == 626
    assert first["source_plan"]["C"]["unique_content"] == 30696
    assert first["source_plan"]["C"]["occurrence_sum"] == 47559
    assert universe_sha(load_leaf_universe(), *LEAF_FIELDS) == first["sha"]
