"""WO-RISK-04-REVIEW-005A-DECISION-001 LEAF 004A GPT freeze. No new semantic decision."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review002_decisions import BATCH002_GPT_PATH
from tools.risk04.review003_decisions import REVIEW003_GPT_PATH
from tools.risk04.review004_leaf_routing import LEAF_FIELDS, LEAF_PATHS, load_leaf_batch
from tools.risk04.review005a_pack import FROZEN_004A_SHA, INPUT_004A_PATH, PACK_004A_PATH, compact_pack_sha
from tools.risk04.review005a_decisions import (
    APPROVAL_STATE,
    FROZEN_COMPACT_SHA,
    GPT004A_FIELDS,
    GPT_004A_PATH,
    MERGE_856,
    MERGE_864,
    MERGE_KEY_856,
    MERGE_KEY_864,
    RESULT_004A_PATH,
    build_004a_gpt_manifest,
    manifest_004a_sha,
)
from tools.risk04.review_decisions import GPT_MANIFEST_PATH, load_tsv
from tools.risk04.seed_review import universe_sha

MANIFEST_SHA = "045b8670697b091fe83f7b63e2902c0899426d8bbd10ce355aeaecb5b6bdbcde"
BATCH_SHAS = {
    "004A": "23e15185bc004c62432f8044596995a1106759d2f1febe399bd76c6b9265c894",
    "004B": "bfe98e52c4e6f812a09e44260b4f23bc7020bdbefa9a0c3eece281ab096b858c",
    "004C": "665a3c376c218315d4adceb32ff3d5a81da72af90eda76442d823fd6ac8e1f72",
    "004D": "f0cdea5c724fb5c7d66104a3fe72aa3aceaa550c9239fb5fe065eb58d3cfa047",
    "004E": "2a2a973666b7144045272adbcd8a3456218e83e5f5c4c876fc94480c8c20ab64",
    "004F": "c8ddb8b0e997005b3d6fe40f4b88ad1590e12012ba811f46c688773b2df3e100",
}


def test_frozen_004a_input_and_compact_unchanged():
    source = load_leaf_batch(INPUT_004A_PATH)
    assert universe_sha(source, *LEAF_FIELDS) == FROZEN_004A_SHA == BATCH_SHAS["004A"]
    compact = load_tsv(PACK_004A_PATH)
    assert compact_pack_sha(compact) == FROZEN_COMPACT_SHA
    labels = ("004A", "004B", "004C", "004D", "004E", "004F")
    for label, path in zip(labels, LEAF_PATHS, strict=True):
        assert universe_sha(load_leaf_batch(path), *LEAF_FIELDS) == BATCH_SHAS[label]


def test_004a_gpt_manifest_counts_and_merge_pair():
    rows = load_tsv(GPT_004A_PATH)
    rebuilt = build_004a_gpt_manifest()
    assert list(rows[0].keys()) == list(GPT004A_FIELDS)
    assert len(rows) == 200
    assert [row["review_no"] for row in rows] == [str(i) for i in range(692, 892)]
    kinds = Counter(row["semantic_kind_after"] for row in rows)
    decisions = Counter(row["semantic_review_decision"] for row in rows)
    assert kinds["PROCESS"] == 7
    assert kinds["TASK"] == 69
    assert kinds["METHOD"] == 2
    assert kinds["MATERIAL_COMPONENT"] == 5
    assert kinds["FACILITY_EQUIPMENT"] == 70
    assert kinds["CLASSIFICATION"] == 47
    assert kinds["AMBIGUOUS"] == 0
    assert decisions["KEEP_AS_DISTINCT"] == 74
    assert decisions["MERGE_CANDIDATE"] == 2
    assert decisions["HOLD"] == 0
    assert decisions["REJECT"] == 124
    assert all(row["approval_state"] == APPROVAL_STATE for row in rows)
    assert all(row["semantic_kind_before"] == "AMBIGUOUS" for row in rows)
    by_no = {int(row["review_no"]): row for row in rows}
    left = by_no[MERGE_856]
    right = by_no[MERGE_864]
    assert left["semantic_kind_after"] == "TASK"
    assert right["semantic_kind_after"] == "TASK"
    assert left["semantic_review_decision"] == "MERGE_CANDIDATE"
    assert right["semantic_review_decision"] == "MERGE_CANDIDATE"
    assert left["merge_candidate_keys"] == MERGE_KEY_856 == right["seed_proposal_key"]
    assert right["merge_candidate_keys"] == MERGE_KEY_864 == left["seed_proposal_key"]
    assert all(
        row["merge_candidate_keys"] == "EMPTY"
        for row in rows
        if int(row["review_no"]) not in {MERGE_856, MERGE_864}
    )
    assert manifest_004a_sha(rows) == MANIFEST_SHA
    assert manifest_004a_sha(rebuilt) == manifest_004a_sha(build_004a_gpt_manifest()) == MANIFEST_SHA
    result = load_tsv(RESULT_004A_PATH)
    assert len(result) == 200
    assert [row["semantic_kind_after"] for row in result] == [row["semantic_kind_after"] for row in rows]


def test_cicw_reviewed_aggregate_741():
    rows = []
    for path in (GPT_MANIFEST_PATH, BATCH002_GPT_PATH, REVIEW003_GPT_PATH):
        for row in load_tsv(path):
            if row["source_id"] != "CIC_W":
                continue
            kind = row.get("semantic_kind_after") or row["semantic_kind_override"]
            rows.append((row["source_key"], kind, row["semantic_review_decision"]))
    for row in load_tsv(GPT_004A_PATH):
        rows.append((row["source_key"], row["semantic_kind_after"], row["semantic_review_decision"]))
    assert len({key for key, _, _ in rows}) == 741
    kinds = Counter(kind for _, kind, _ in rows)
    decisions = Counter(decision for _, _, decision in rows)
    assert kinds["PROCESS"] == 390
    assert kinds["TASK"] == 94
    assert kinds["METHOD"] == 6
    assert kinds["MATERIAL_COMPONENT"] == 42
    assert kinds["FACILITY_EQUIPMENT"] == 117
    assert kinds["CLASSIFICATION"] == 75
    assert kinds["AMBIGUOUS"] == 17
    assert decisions["KEEP_AS_DISTINCT"] == 453
    assert decisions["MERGE_CANDIDATE"] == 31
    assert decisions["HOLD"] == 17
    assert decisions["REJECT"] == 240
    remaining = []
    for path in LEAF_PATHS[1:]:
        remaining.extend(load_leaf_batch(path))
    assert len(remaining) == 981
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in remaining)
    assert all(row["current_semantic_kind"] == "AMBIGUOUS" for row in remaining)


def test_005a_decisions_do_not_classify_or_propagate():
    src = Path("tools/risk04/review005a_decisions.py").read_text(encoding="utf-8")
    assert "openai" not in src.lower()
    assert "embedding" not in src.lower()
    assert "rapidfuzz" not in src.lower()
    assert "uuid4" not in src
    assert "re.compile" not in src
    assert "Not a parent/family/suffix classifier" in src
    assert Path("tools/risk04/semantic_gate.py").read_text(encoding="utf-8").count("uuid4") == 0
    assert 'APPROVAL_STATE = "NOT_APPROVED"' in Path("tools/risk04/review_decisions.py").read_text(encoding="utf-8")
    compact = load_tsv(PACK_004A_PATH)
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in compact)
    assert all(row["gpt_review_decision"] == "PENDING" for row in compact)
