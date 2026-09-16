"""WO-RISK-04-REVIEW-005D-DECISION-001 LEAF 004D GPT freeze. No new semantic decision."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review002_decisions import BATCH002_GPT_PATH
from tools.risk04.review003_decisions import REVIEW003_GPT_PATH
from tools.risk04.review004_leaf_routing import LEAF_FIELDS, LEAF_PATHS, load_leaf_batch
from tools.risk04.review005a_decisions import GPT_004A_PATH
from tools.risk04.review005b_decisions import GPT_004B_PATH
from tools.risk04.review005c_decisions import GPT_004C_PATH
from tools.risk04.review005d_pack import FROZEN_004D_SHA, INPUT_004D_PATH, PACK_004D_PATH, compact_pack_sha
from tools.risk04.review005d_decisions import (
    APPROVAL_STATE,
    FROZEN_COMPACT_SHA,
    GPT004D_FIELDS,
    GPT_004D_PATH,
    NAMED_KIND,
    RESULT_004D_PATH,
    build_004d_gpt_manifest,
    manifest_004d_sha,
)
from tools.risk04.review_decisions import GPT_MANIFEST_PATH, load_tsv
from tools.risk04.seed_review import universe_sha

MANIFEST_SHA = "a66f9ae03602422f6cef19ed58d80f43004f025fb61e5a05576c911d5942c370"
BATCH_SHAS = {
    "004A": "23e15185bc004c62432f8044596995a1106759d2f1febe399bd76c6b9265c894",
    "004B": "bfe98e52c4e6f812a09e44260b4f23bc7020bdbefa9a0c3eece281ab096b858c",
    "004C": "665a3c376c218315d4adceb32ff3d5a81da72af90eda76442d823fd6ac8e1f72",
    "004D": "f0cdea5c724fb5c7d66104a3fe72aa3aceaa550c9239fb5fe065eb58d3cfa047",
    "004E": "2a2a973666b7144045272adbcd8a3456218e83e5f5c4c876fc94480c8c20ab64",
    "004F": "c8ddb8b0e997005b3d6fe40f4b88ad1590e12012ba811f46c688773b2df3e100",
}
NAMED_DECISION = {
    "PROCESS": "KEEP_AS_DISTINCT",
    "TASK": "KEEP_AS_DISTINCT",
    "MATERIAL_COMPONENT": "REJECT",
    "FACILITY_EQUIPMENT": "REJECT",
    "CLASSIFICATION": "REJECT",
}


def test_frozen_004d_input_and_compact_unchanged():
    source = load_leaf_batch(INPUT_004D_PATH)
    assert universe_sha(source, *LEAF_FIELDS) == FROZEN_004D_SHA == BATCH_SHAS["004D"]
    compact = load_tsv(PACK_004D_PATH)
    assert compact_pack_sha(compact) == FROZEN_COMPACT_SHA
    labels = ("004A", "004B", "004C", "004D", "004E", "004F")
    for label, path in zip(labels, LEAF_PATHS, strict=True):
        assert universe_sha(load_leaf_batch(path), *LEAF_FIELDS) == BATCH_SHAS[label]


def test_004d_gpt_manifest_counts_and_no_merge_hold():
    rows = load_tsv(GPT_004D_PATH)
    rebuilt = build_004d_gpt_manifest()
    assert list(rows[0].keys()) == list(GPT004D_FIELDS)
    assert len(rows) == 200
    assert [row["review_no"] for row in rows] == [str(i) for i in range(1292, 1492)]
    assert len({row["review_no"] for row in rows}) == 200
    assert len({row["seed_proposal_key"] for row in rows}) == 200
    assert len({row["source_key"] for row in rows}) == 200
    kinds = Counter(row["semantic_kind_after"] for row in rows)
    decisions = Counter(row["semantic_review_decision"] for row in rows)
    assert kinds["PROCESS"] == 4
    assert kinds["TASK"] == 98
    assert kinds["MATERIAL_COMPONENT"] == 75
    assert kinds["FACILITY_EQUIPMENT"] == 20
    assert kinds["CLASSIFICATION"] == 3
    assert "METHOD" not in kinds
    assert "AMBIGUOUS" not in kinds
    assert decisions["KEEP_AS_DISTINCT"] == 102
    assert "MERGE_CANDIDATE" not in decisions
    assert "HOLD" not in decisions
    assert decisions["REJECT"] == 98
    assert all(row["approval_state"] == APPROVAL_STATE for row in rows)
    assert all(row["semantic_kind_before"] == "AMBIGUOUS" for row in rows)
    assert all(row["merge_candidate_keys"] == "EMPTY" for row in rows)
    by_no = {int(row["review_no"]): row for row in rows}
    for no, (name, kind) in NAMED_KIND.items():
        assert by_no[no]["name"] == name
        assert by_no[no]["name"].encode("utf-8") == name.encode("utf-8")
        assert by_no[no]["semantic_kind_after"] == kind
        assert by_no[no]["semantic_review_decision"] == NAMED_DECISION[kind]
    assert by_no[1426]["name"] == "창문 - - 대․중․소 분류대․중․소 분류"
    assert manifest_004d_sha(rows) == MANIFEST_SHA
    assert manifest_004d_sha(rebuilt) == manifest_004d_sha(build_004d_gpt_manifest()) == MANIFEST_SHA
    result = load_tsv(RESULT_004D_PATH)
    assert len(result) == 200
    assert [row["semantic_kind_after"] for row in result] == [row["semantic_kind_after"] for row in rows]
    assert [row["semantic_review_decision"] for row in result] == [row["semantic_review_decision"] for row in rows]


def test_cicw_reviewed_aggregate_1341():
    rows = []
    for path in (GPT_MANIFEST_PATH, BATCH002_GPT_PATH, REVIEW003_GPT_PATH):
        for row in load_tsv(path):
            if row["source_id"] != "CIC_W":
                continue
            kind = row.get("semantic_kind_after") or row["semantic_kind_override"]
            rows.append((row["source_key"], kind, row["semantic_review_decision"]))
    for path in (GPT_004A_PATH, GPT_004B_PATH, GPT_004C_PATH, GPT_004D_PATH):
        for row in load_tsv(path):
            rows.append((row["source_key"], row["semantic_kind_after"], row["semantic_review_decision"]))
    assert len({key for key, _, _ in rows}) == 1341
    kinds = Counter(kind for _, kind, _ in rows)
    decisions = Counter(decision for _, _, decision in rows)
    assert kinds["PROCESS"] == 438
    assert kinds["TASK"] == 394
    assert kinds["METHOD"] == 32
    assert kinds["MATERIAL_COMPONENT"] == 178
    assert kinds["FACILITY_EQUIPMENT"] == 186
    assert kinds["CLASSIFICATION"] == 88
    assert kinds["AMBIGUOUS"] == 25
    assert decisions["KEEP_AS_DISTINCT"] == 792
    assert decisions["MERGE_CANDIDATE"] == 40
    assert decisions["HOLD"] == 25
    assert decisions["REJECT"] == 484
    remaining = []
    for path in LEAF_PATHS[4:]:
        remaining.extend(load_leaf_batch(path))
    assert len(remaining) == 381
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in remaining)
    assert all(row["current_semantic_kind"] == "AMBIGUOUS" for row in remaining)
    assert all(row["current_review_decision"] == "UNREVIEWED" for row in remaining)


def test_005d_decisions_do_not_classify_or_propagate():
    src = Path("tools/risk04/review005d_decisions.py").read_text(encoding="utf-8")
    assert "openai" not in src.lower()
    assert "embedding" not in src.lower()
    assert "rapidfuzz" not in src.lower()
    assert "uuid4" not in src
    assert "re.compile" not in src
    assert "Completed GPT review of review_no 1292..1491 only." in src
    assert "This is an explicit decision freeze, not a classifier." in src
    compact = load_tsv(PACK_004D_PATH)
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in compact)
    assert all(row["gpt_review_decision"] == "PENDING" for row in compact)
    assert Path("tools/risk04/semantic_gate.py").read_text(encoding="utf-8").count("uuid4") == 0
    assert 'APPROVAL_STATE = "NOT_APPROVED"' in Path("tools/risk04/review_decisions.py").read_text(encoding="utf-8")
    pack_src = Path("tools/risk04/review005d_pack.py").read_text(encoding="utf-8")
    assert 'gpt_semantic_kind": "PENDING"' in pack_src
