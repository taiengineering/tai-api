"""WO-RISK-04-REVIEW-005E-DECISION-001 LEAF 004E GPT freeze. No new semantic decision."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review002_decisions import BATCH002_GPT_PATH
from tools.risk04.review003_decisions import REVIEW003_GPT_PATH
from tools.risk04.review004_leaf_routing import LEAF_FIELDS, LEAF_PATHS, load_leaf_batch
from tools.risk04.review005a_decisions import GPT_004A_PATH
from tools.risk04.review005b_decisions import GPT_004B_PATH
from tools.risk04.review005c_decisions import GPT_004C_PATH
from tools.risk04.review005d_decisions import GPT_004D_PATH
from tools.risk04.review005e_pack import FROZEN_004E_SHA, INPUT_004E_PATH, PACK_004E_PATH, compact_pack_sha
from tools.risk04.review005e_decisions import (
    APPROVAL_STATE,
    FROZEN_COMPACT_SHA,
    GPT004E_FIELDS,
    GPT_004E_PATH,
    MERGE_CANDIDATE,
    NAMED_KIND,
    RESULT_004E_PATH,
    build_004e_gpt_manifest,
    manifest_004e_sha,
)
from tools.risk04.review_decisions import GPT_MANIFEST_PATH, load_tsv
from tools.risk04.seed_review import universe_sha

MANIFEST_SHA = "2f32cf671e463aafa025ecdcb5f281387e3fce46af4cf7e3e5085b094e639316"
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
}


def test_frozen_004e_input_and_compact_unchanged():
    source = load_leaf_batch(INPUT_004E_PATH)
    assert universe_sha(source, *LEAF_FIELDS) == FROZEN_004E_SHA == BATCH_SHAS["004E"]
    compact = load_tsv(PACK_004E_PATH)
    assert compact_pack_sha(compact) == FROZEN_COMPACT_SHA
    labels = ("004A", "004B", "004C", "004D", "004E", "004F")
    for label, path in zip(labels, LEAF_PATHS, strict=True):
        assert universe_sha(load_leaf_batch(path), *LEAF_FIELDS) == BATCH_SHAS[label]


def test_004e_gpt_manifest_counts_and_merge_pairs():
    rows = load_tsv(GPT_004E_PATH)
    rebuilt = build_004e_gpt_manifest()
    assert list(rows[0].keys()) == list(GPT004E_FIELDS)
    assert len(rows) == 200
    assert [row["review_no"] for row in rows] == [str(i) for i in range(1492, 1692)]
    assert len({row["review_no"] for row in rows}) == 200
    assert len({row["seed_proposal_key"] for row in rows}) == 200
    assert len({row["source_key"] for row in rows}) == 200
    kinds = Counter(row["semantic_kind_after"] for row in rows)
    decisions = Counter(row["semantic_review_decision"] for row in rows)
    assert kinds["PROCESS"] == 14
    assert kinds["TASK"] == 122
    assert kinds["MATERIAL_COMPONENT"] == 44
    assert kinds["FACILITY_EQUIPMENT"] == 20
    assert "METHOD" not in kinds
    assert "CLASSIFICATION" not in kinds
    assert "AMBIGUOUS" not in kinds
    assert decisions["KEEP_AS_DISTINCT"] == 132
    assert decisions["MERGE_CANDIDATE"] == 4
    assert "HOLD" not in decisions
    assert decisions["REJECT"] == 64
    assert all(row["approval_state"] == APPROVAL_STATE for row in rows)
    assert all(row["semantic_kind_before"] == "AMBIGUOUS" for row in rows)
    by_no = {int(row["review_no"]): row for row in rows}
    for left, right in ((1501, 1548), (1652, 1654)):
        assert by_no[left]["semantic_kind_after"] == "TASK"
        assert by_no[right]["semantic_kind_after"] == "TASK"
        assert by_no[left]["semantic_review_decision"] == "MERGE_CANDIDATE"
        assert by_no[right]["semantic_review_decision"] == "MERGE_CANDIDATE"
        assert by_no[left]["merge_candidate_keys"] == by_no[right]["seed_proposal_key"]
        assert by_no[right]["merge_candidate_keys"] == by_no[left]["seed_proposal_key"]
    empty = [row for row in rows if int(row["review_no"]) not in MERGE_CANDIDATE]
    assert len(empty) == 196
    assert all(row["merge_candidate_keys"] == "EMPTY" for row in empty)
    for no, (name, kind) in NAMED_KIND.items():
        assert by_no[no]["name"] == name
        assert by_no[no]["name"].encode("utf-8") == name.encode("utf-8")
        assert by_no[no]["semantic_kind_after"] == kind
        expected = "MERGE_CANDIDATE" if no in MERGE_CANDIDATE else NAMED_DECISION[kind]
        assert by_no[no]["semantic_review_decision"] == expected
    assert manifest_004e_sha(rows) == MANIFEST_SHA
    assert manifest_004e_sha(rebuilt) == manifest_004e_sha(build_004e_gpt_manifest()) == MANIFEST_SHA
    result = load_tsv(RESULT_004E_PATH)
    assert len(result) == 200
    assert [row["semantic_kind_after"] for row in result] == [row["semantic_kind_after"] for row in rows]
    assert [row["semantic_review_decision"] for row in result] == [row["semantic_review_decision"] for row in rows]


def test_cicw_reviewed_aggregate_1541():
    rows = []
    for path in (GPT_MANIFEST_PATH, BATCH002_GPT_PATH, REVIEW003_GPT_PATH):
        for row in load_tsv(path):
            if row["source_id"] != "CIC_W":
                continue
            kind = row.get("semantic_kind_after") or row["semantic_kind_override"]
            rows.append((row["source_key"], kind, row["semantic_review_decision"]))
    for path in (GPT_004A_PATH, GPT_004B_PATH, GPT_004C_PATH, GPT_004D_PATH, GPT_004E_PATH):
        for row in load_tsv(path):
            rows.append((row["source_key"], row["semantic_kind_after"], row["semantic_review_decision"]))
    assert len({key for key, _, _ in rows}) == 1541
    kinds = Counter(kind for _, kind, _ in rows)
    decisions = Counter(decision for _, _, decision in rows)
    assert kinds["PROCESS"] == 452
    assert kinds["TASK"] == 516
    assert kinds["METHOD"] == 32
    assert kinds["MATERIAL_COMPONENT"] == 222
    assert kinds["FACILITY_EQUIPMENT"] == 206
    assert kinds["CLASSIFICATION"] == 88
    assert kinds["AMBIGUOUS"] == 25
    assert decisions["KEEP_AS_DISTINCT"] == 924
    assert decisions["MERGE_CANDIDATE"] == 44
    assert decisions["HOLD"] == 25
    assert decisions["REJECT"] == 548
    remaining = load_leaf_batch(LEAF_PATHS[5])
    assert len(remaining) == 181
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in remaining)
    assert all(row["current_semantic_kind"] == "AMBIGUOUS" for row in remaining)
    assert all(row["current_review_decision"] == "UNREVIEWED" for row in remaining)


def test_005e_decisions_do_not_classify_or_propagate():
    src = Path("tools/risk04/review005e_decisions.py").read_text(encoding="utf-8")
    assert "openai" not in src.lower()
    assert "embedding" not in src.lower()
    assert "rapidfuzz" not in src.lower()
    assert "uuid4" not in src
    assert "re.compile" not in src
    assert "Completed GPT review of review_no 1492..1691 only." in src
    assert "This is an explicit decision freeze, not a classifier." in src
    compact = load_tsv(PACK_004E_PATH)
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in compact)
    assert all(row["gpt_review_decision"] == "PENDING" for row in compact)
    assert Path("tools/risk04/semantic_gate.py").read_text(encoding="utf-8").count("uuid4") == 0
    assert 'APPROVAL_STATE = "NOT_APPROVED"' in Path("tools/risk04/review_decisions.py").read_text(encoding="utf-8")
    pack_src = Path("tools/risk04/review005e_pack.py").read_text(encoding="utf-8")
    assert 'gpt_semantic_kind": "PENDING"' in pack_src
