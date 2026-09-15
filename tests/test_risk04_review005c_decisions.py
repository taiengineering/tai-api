"""WO-RISK-04-REVIEW-005C-DECISION-001 LEAF 004C GPT freeze. No new semantic decision."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from tools.risk04.review002_decisions import BATCH002_GPT_PATH
from tools.risk04.review003_decisions import REVIEW003_GPT_PATH
from tools.risk04.review004_leaf_routing import LEAF_FIELDS, LEAF_PATHS, load_leaf_batch
from tools.risk04.review005a_decisions import GPT_004A_PATH
from tools.risk04.review005b_decisions import GPT_004B_PATH
from tools.risk04.review005c_pack import FROZEN_004C_SHA, INPUT_004C_PATH, PACK_004C_PATH, compact_pack_sha
from tools.risk04.review005c_decisions import (
    APPROVAL_STATE,
    FROZEN_COMPACT_SHA,
    GPT004C_FIELDS,
    GPT_004C_PATH,
    HOLD_NAMES,
    HOLD_NOS,
    NAMED_KIND,
    RESULT_004C_PATH,
    build_004c_gpt_manifest,
    manifest_004c_sha,
)
from tools.risk04.review_decisions import GPT_MANIFEST_PATH, load_tsv
from tools.risk04.seed_review import universe_sha

MANIFEST_SHA = "1abfcd2a186fd3479d29e6ee5f9ebb4cc3bd3e6c9044e64fbdc100aa19d3d66b"
BATCH_SHAS = {
    "004A": "23e15185bc004c62432f8044596995a1106759d2f1febe399bd76c6b9265c894",
    "004B": "bfe98e52c4e6f812a09e44260b4f23bc7020bdbefa9a0c3eece281ab096b858c",
    "004C": "665a3c376c218315d4adceb32ff3d5a81da72af90eda76442d823fd6ac8e1f72",
    "004D": "f0cdea5c724fb5c7d66104a3fe72aa3aceaa550c9239fb5fe065eb58d3cfa047",
    "004E": "2a2a973666b7144045272adbcd8a3456218e83e5f5c4c876fc94480c8c20ab64",
    "004F": "c8ddb8b0e997005b3d6fe40f4b88ad1590e12012ba811f46c688773b2df3e100",
}


def test_frozen_004c_input_and_compact_unchanged():
    source = load_leaf_batch(INPUT_004C_PATH)
    assert universe_sha(source, *LEAF_FIELDS) == FROZEN_004C_SHA == BATCH_SHAS["004C"]
    compact = load_tsv(PACK_004C_PATH)
    assert compact_pack_sha(compact) == FROZEN_COMPACT_SHA
    labels = ("004A", "004B", "004C", "004D", "004E", "004F")
    for label, path in zip(labels, LEAF_PATHS, strict=True):
        assert universe_sha(load_leaf_batch(path), *LEAF_FIELDS) == BATCH_SHAS[label]


def test_004c_gpt_manifest_counts_hold_and_no_merge():
    rows = load_tsv(GPT_004C_PATH)
    rebuilt = build_004c_gpt_manifest()
    assert list(rows[0].keys()) == list(GPT004C_FIELDS)
    assert len(rows) == 200
    assert [row["review_no"] for row in rows] == [str(i) for i in range(1092, 1292)]
    assert len({row["review_no"] for row in rows}) == 200
    assert len({row["seed_proposal_key"] for row in rows}) == 200
    assert len({row["source_key"] for row in rows}) == 200
    kinds = Counter(row["semantic_kind_after"] for row in rows)
    decisions = Counter(row["semantic_review_decision"] for row in rows)
    assert kinds["PROCESS"] == 24
    assert kinds["TASK"] == 86
    assert kinds["MATERIAL_COMPONENT"] == 41
    assert kinds["FACILITY_EQUIPMENT"] == 44
    assert kinds["AMBIGUOUS"] == 5
    assert "METHOD" not in kinds
    assert "CLASSIFICATION" not in kinds
    assert decisions["KEEP_AS_DISTINCT"] == 110
    assert "MERGE_CANDIDATE" not in decisions
    assert decisions["HOLD"] == 5
    assert decisions["REJECT"] == 85
    assert all(row["approval_state"] == APPROVAL_STATE for row in rows)
    assert all(row["semantic_kind_before"] == "AMBIGUOUS" for row in rows)
    assert all(row["merge_candidate_keys"] == "EMPTY" for row in rows)
    by_no = {int(row["review_no"]): row for row in rows}
    hold_only = {int(row["review_no"]) for row in rows if row["semantic_review_decision"] == "HOLD"}
    assert hold_only == set(HOLD_NOS)
    for no in HOLD_NOS:
        assert by_no[no]["semantic_kind_after"] == "AMBIGUOUS"
        assert by_no[no]["semantic_review_decision"] == "HOLD"
        assert by_no[no]["name"] == HOLD_NAMES[no]
        assert by_no[no]["name"].encode("utf-8") == HOLD_NAMES[no].encode("utf-8")
    for no, (name, kind) in NAMED_KIND.items():
        assert by_no[no]["name"] == name
        assert by_no[no]["semantic_kind_after"] == kind
    for no in range(1276, 1282):
        assert by_no[no]["semantic_kind_after"] == "MATERIAL_COMPONENT"
        assert by_no[no]["semantic_review_decision"] == "REJECT"
    assert manifest_004c_sha(rows) == MANIFEST_SHA
    assert manifest_004c_sha(rebuilt) == manifest_004c_sha(build_004c_gpt_manifest()) == MANIFEST_SHA
    result = load_tsv(RESULT_004C_PATH)
    assert len(result) == 200
    assert [row["semantic_kind_after"] for row in result] == [row["semantic_kind_after"] for row in rows]
    assert [row["semantic_review_decision"] for row in result] == [row["semantic_review_decision"] for row in rows]


def test_cicw_reviewed_aggregate_1141():
    rows = []
    for path in (GPT_MANIFEST_PATH, BATCH002_GPT_PATH, REVIEW003_GPT_PATH):
        for row in load_tsv(path):
            if row["source_id"] != "CIC_W":
                continue
            kind = row.get("semantic_kind_after") or row["semantic_kind_override"]
            rows.append((row["source_key"], kind, row["semantic_review_decision"]))
    for path in (GPT_004A_PATH, GPT_004B_PATH, GPT_004C_PATH):
        for row in load_tsv(path):
            rows.append((row["source_key"], row["semantic_kind_after"], row["semantic_review_decision"]))
    assert len({key for key, _, _ in rows}) == 1141
    kinds = Counter(kind for _, kind, _ in rows)
    decisions = Counter(decision for _, _, decision in rows)
    assert kinds["PROCESS"] == 434
    assert kinds["TASK"] == 296
    assert kinds["METHOD"] == 32
    assert kinds["MATERIAL_COMPONENT"] == 103
    assert kinds["FACILITY_EQUIPMENT"] == 166
    assert kinds["CLASSIFICATION"] == 85
    assert kinds["AMBIGUOUS"] == 25
    assert decisions["KEEP_AS_DISTINCT"] == 690
    assert decisions["MERGE_CANDIDATE"] == 40
    assert decisions["HOLD"] == 25
    assert decisions["REJECT"] == 386
    remaining = []
    for path in LEAF_PATHS[3:]:
        remaining.extend(load_leaf_batch(path))
    assert len(remaining) == 581
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in remaining)
    assert all(row["current_semantic_kind"] == "AMBIGUOUS" for row in remaining)
    assert all(row["current_review_decision"] == "UNREVIEWED" for row in remaining)


def test_005c_decisions_do_not_classify_or_propagate():
    src = Path("tools/risk04/review005c_decisions.py").read_text(encoding="utf-8")
    assert "openai" not in src.lower()
    assert "embedding" not in src.lower()
    assert "rapidfuzz" not in src.lower()
    assert "uuid4" not in src
    assert "re.compile" not in src
    assert "Completed GPT review of review_no 1092..1291 only." in src
    assert "This is not a parent/family/name/suffix classifier." in src
    assert "N=값 추정" not in src
    compact = load_tsv(PACK_004C_PATH)
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in compact)
    assert all(row["gpt_review_decision"] == "PENDING" for row in compact)
    assert Path("tools/risk04/semantic_gate.py").read_text(encoding="utf-8").count("uuid4") == 0
    assert 'APPROVAL_STATE = "NOT_APPROVED"' in Path("tools/risk04/review_decisions.py").read_text(encoding="utf-8")
    pack_src = Path("tools/risk04/review005c_pack.py").read_text(encoding="utf-8")
    assert 'gpt_semantic_kind": "PENDING"' in pack_src
