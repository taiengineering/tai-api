"""WO-RISK-04-REVIEW-005B LEAF 004B compact GPT pack. No semantic decision."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review002_decisions import BATCH002_GPT_PATH
from tools.risk04.review003_decisions import REVIEW003_GPT_PATH
from tools.risk04.review004_leaf_routing import LEAF_FIELDS, LEAF_PATHS, load_leaf_batch
from tools.risk04.review005a_decisions import GPT_004A_PATH
from tools.risk04.review005a_pack import COMPACT_FIELDS, compact_pack_sha
from tools.risk04.review005b_pack import (
    FROZEN_004B_SHA,
    GROUPS_004B_PATH,
    INPUT_004B_PATH,
    PACK_004B_PATH,
    assert_frozen_004b,
    build_compact_pack_004b,
    parent_groups,
    render_parent_groups_004b,
)
from tools.risk04.review_decisions import GPT_MANIFEST_PATH, load_tsv
from tools.risk04.seed_review import universe_sha

COMPACT_SHA = "d253c143a54c034858115cfbc87e45559c64217dbf76a80a6205c2a0e217f360"
BATCH_SHAS = {
    "004A": "23e15185bc004c62432f8044596995a1106759d2f1febe399bd76c6b9265c894",
    "004B": "bfe98e52c4e6f812a09e44260b4f23bc7020bdbefa9a0c3eece281ab096b858c",
    "004C": "665a3c376c218315d4adceb32ff3d5a81da72af90eda76442d823fd6ac8e1f72",
    "004D": "f0cdea5c724fb5c7d66104a3fe72aa3aceaa550c9239fb5fe065eb58d3cfa047",
    "004E": "2a2a973666b7144045272adbcd8a3456218e83e5f5c4c876fc94480c8c20ab64",
    "004F": "c8ddb8b0e997005b3d6fe40f4b88ad1590e12012ba811f46c688773b2df3e100",
}


def test_frozen_004b_input_unchanged():
    rows = assert_frozen_004b()
    assert universe_sha(rows, *LEAF_FIELDS) == FROZEN_004B_SHA
    assert INPUT_004B_PATH.exists()
    labels = ("004A", "004B", "004C", "004D", "004E", "004F")
    for label, path in zip(labels, LEAF_PATHS, strict=True):
        assert universe_sha(load_leaf_batch(path), *LEAF_FIELDS) == BATCH_SHAS[label]
    assert [int(row["review_no"]) for row in rows][0] == 892
    assert [int(row["review_no"]) for row in rows][-1] == 1091


def test_compact_pack_identity_and_pending():
    source = load_leaf_batch(INPUT_004B_PATH)
    rows = load_tsv(PACK_004B_PATH)
    assert list(rows[0].keys()) == list(COMPACT_FIELDS)
    assert len(rows) == 200
    assert [row["review_no"] for row in rows] == [str(i) for i in range(892, 1092)]
    assert len({row["review_no"] for row in rows}) == 200
    assert len({row["seed_proposal_key"] for row in rows}) == 200
    assert len({row["source_key"] for row in rows}) == 200
    assert {row["seed_proposal_key"] for row in rows} == {row["seed_proposal_key"] for row in source}
    assert {row["source_key"] for row in rows} == {row["source_key"] for row in source}
    assert [row["review_no"] for row in rows] == [row["review_no"] for row in source]
    assert [row["seed_proposal_key"] for row in rows] == [row["seed_proposal_key"] for row in source]
    assert [row["source_key"] for row in rows] == [row["source_key"] for row in source]
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in rows)
    assert all(row["gpt_review_decision"] == "PENDING" for row in rows)
    assert all(row["merge_candidate_keys"] == "EMPTY" for row in rows)
    assert all(row["gpt_reason"] == "EMPTY" for row in rows)
    assert compact_pack_sha(rows) == COMPACT_SHA
    first = build_compact_pack_004b(source)
    second = build_compact_pack_004b(source)
    assert compact_pack_sha(first) == compact_pack_sha(second) == COMPACT_SHA
    g1 = render_parent_groups_004b(parent_groups(first))
    g2 = render_parent_groups_004b(parent_groups(second))
    assert g1 == g2
    assert GROUPS_004B_PATH.read_text(encoding="utf-8") == g1


def test_reviewed_counts_unchanged_and_no_004b_decisions():
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
    a004 = load_tsv(GPT_004A_PATH)
    a_kinds = Counter(row["semantic_kind_after"] for row in a004)
    a_decs = Counter(row["semantic_review_decision"] for row in a004)
    assert a_kinds["PROCESS"] == 7
    assert a_kinds["TASK"] == 69
    assert a_kinds["METHOD"] == 2
    assert a_kinds["MATERIAL_COMPONENT"] == 5
    assert a_kinds["FACILITY_EQUIPMENT"] == 70
    assert a_kinds["CLASSIFICATION"] == 47
    assert a_decs["KEEP_AS_DISTINCT"] == 74
    assert a_decs["MERGE_CANDIDATE"] == 2
    assert a_decs["REJECT"] == 124
    reviewed = {key for key, _, _ in rows}
    pack_keys = {row["source_key"] for row in load_tsv(PACK_004B_PATH)}
    assert not pack_keys.intersection(reviewed)
    remaining = set()
    for path in LEAF_PATHS[1:]:
        remaining.update(row["source_key"] for row in load_leaf_batch(path))
    assert len(remaining) == 981
    assert pack_keys <= remaining
    assert decisions["KEEP_AS_DISTINCT"] == 453
    assert kinds["AMBIGUOUS"] == 17


def test_review005b_does_not_decide_or_propagate():
    src = Path("tools/risk04/review005b_pack.py").read_text(encoding="utf-8")
    assert "openai" not in src.lower()
    assert "embedding" not in src.lower()
    assert "rapidfuzz" not in src.lower()
    assert "uuid4" not in src
    assert "re.compile" not in src
    assert 'gpt_semantic_kind": "PENDING"' in src
    groups = GROUPS_004B_PATH.read_text(encoding="utf-8")
    assert "이 family는 PROCESS다" not in groups
    assert "이 family는 TASK다" not in groups
    assert "자동분류 가능" not in groups
    assert "canonical 후보" not in groups
    assert "merge 가능" not in groups
    assert "동일 개념" not in groups
    assert "class: records" in groups
    pack = load_tsv(PACK_004B_PATH)
    process_parents = [row for row in pack if row["parent_semantic_kind"] == "PROCESS"]
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in process_parents)
    task_parents = [row for row in pack if row["parent_semantic_kind"] == "TASK"]
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in task_parents)
    assert Path("tools/risk04/semantic_gate.py").read_text(encoding="utf-8").count("uuid4") == 0
    assert 'APPROVAL_STATE = "NOT_APPROVED"' in Path("tools/risk04/review_decisions.py").read_text(encoding="utf-8")
