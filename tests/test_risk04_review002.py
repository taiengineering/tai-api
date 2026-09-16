"""WO-RISK-04-REVIEW-002 CIC_W Batch 002 evidence. No semantic decision."""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pytest

from tools.risk04.review_batch import batch_sha
from tools.risk02.contract import SOURCE_KALIS
from tools.risk02.identity import path_source_key
from tools.risk04.seed_review import build_seed_proposals
from tools.risk04.review_decisions import GPT_MANIFEST_PATH, load_tsv
from tools.risk04.review_evidence import (
    FROZEN_BATCH_SHA,
    REVIEW_INPUT_PATH,
    load_frozen_batch,
    review_input_sha,
)
from tools.risk04.review002 import (
    BATCH002_PATH,
    WORKSHEET_FIELDS,
    build_review002,
    load_batch002,
    worksheet_sha,
)

ARTIFACTS = Path("artifacts/risk01")
REVIEW_INPUT_SHA = "c28fa67368ff3af3d05f7b771cebca455c6cf5cd94884bbff44dd1bd5087df1b"


def test_frozen_batch001_and_review_input_unchanged():
    frozen = load_frozen_batch()
    assert batch_sha(frozen) == FROZEN_BATCH_SHA
    review_rows = list(csv.DictReader(REVIEW_INPUT_PATH.open(encoding="utf-8"), delimiter="\t"))
    assert review_input_sha(review_rows) == REVIEW_INPUT_SHA


def test_chg1_manifest_counts_unchanged():
    rows = load_tsv(GPT_MANIFEST_PATH)
    counts = Counter(row["semantic_review_decision"] for row in rows)
    assert counts["KEEP_AS_DISTINCT"] == 49
    assert counts["MERGE_CANDIDATE"] == 22
    assert counts["HOLD"] == 17
    assert counts["REJECT"] == 12
    assert all(row["approval_state"] == "NOT_APPROVED" for row in rows)


def test_committed_batch002_shape_and_gpt_pending():
    rows = load_batch002()
    assert list(rows[0].keys()) == list(WORKSHEET_FIELDS)
    assert len(rows) == 200
    assert [row["batch_no"] for row in rows] == [str(i) for i in range(201, 401)]
    assert len({row["seed_proposal_key"] for row in rows}) == 200
    assert all(row["source_id"] == "CIC_W" for row in rows)
    assert all(row["current_semantic_kind"] == "AMBIGUOUS" for row in rows)
    assert all(row["current_review_decision"] == "UNREVIEWED" for row in rows)
    assert all(row["gpt_semantic_kind"] == "PENDING" for row in rows)
    assert all(row["gpt_review_decision"] == "PENDING" for row in rows)
    assert all(row["merge_candidate_keys"] == "EMPTY" for row in rows)
    assert all(row["gpt_reason"] == "EMPTY" for row in rows)
    assert all(row["source_node_type"] in {"W_ROOT", "W_MID", "W_LEAF"} for row in rows)
    assert all(row["root_source_key"] for row in rows)
    assert all(row["depth"] in {"1", "2", "3"} for row in rows)
    for row in rows:
        if row["source_node_type"] != "W_ROOT":
            assert row["parent_source_key"]
            assert row["parent_path"]
    frozen_keys = {row["seed_proposal_key"] for row in load_frozen_batch()}
    assert not frozen_keys.intersection({row["seed_proposal_key"] for row in rows})
    types = Counter(row["source_node_type"] for row in rows)
    assert types["W_ROOT"] == 61
    assert types["W_MID"] == 70
    assert types["W_LEAF"] == 69
    leaves = [row for row in rows if row["source_node_type"] == "W_LEAF"]
    root_share = max(Counter(row["root_source_key"] for row in leaves).values()) / len(leaves)
    parent_share = max(Counter(row["parent_source_key"] for row in leaves).values()) / len(leaves)
    assert root_share <= 0.25
    assert parent_share <= 0.10
    assert BATCH002_PATH.exists()


def test_kalis_multi_parent_auto_hold_still_zero():
    nodes = [
        {
            "source_id": SOURCE_KALIS,
            "source_key": path_source_key("토목", "가설공사", "설치작업"),
            "node_type": "TASK",
            "name_raw": "설치작업",
            "name_normalized": "설치작업",
            "path_normalized": "토목 > 가설공사 > 설치작업",
            "path_raw": "토목 > 가설공사 > 설치작업",
        },
        {
            "source_id": SOURCE_KALIS,
            "source_key": path_source_key("건축", "가설공사", "설치작업"),
            "node_type": "TASK",
            "name_raw": "설치작업",
            "name_normalized": "설치작업",
            "path_normalized": "건축 > 가설공사 > 설치작업",
            "path_raw": "건축 > 가설공사 > 설치작업",
        },
    ]
    proposals = build_seed_proposals(nodes)
    assert all(row["metadata"]["same_name_multi_parent"] is True for row in proposals)
    assert all(row["review_status"] != "HOLD" for row in proposals)


def test_review002_does_not_emit_decisions_or_llm():
    src = Path("tools/risk04/review002.py").read_text(encoding="utf-8")
    assert "openai" not in src.lower()
    assert "embedding" not in src.lower()
    assert "rapidfuzz" not in src.lower()
    assert "uuid4" not in src
    assert "datetime" not in src.lower()


@pytest.mark.skipif(
    not (ARTIFACTS / "source_c/kalis_risk_profile.csv").exists(),
    reason="local RISK-01 artifacts required to rebuild Batch 002",
)
def test_review002_pool_determinism_and_source_preservation():
    first = build_review002(ARTIFACTS)
    second = build_review002(ARTIFACTS)
    assert first["sha"] == second["sha"]
    assert first["facts"]["CIC_W_total"] == 1722
    assert first["facts"]["CIC_W_reviewed"] == 50
    assert first["facts"]["CIC_W_unreviewed"] == 1672
    assert first["facts"]["CIC_W_unreviewed_PROCESS"] == 0
    assert first["facts"]["BATCH002"] == 200
    assert first["facts"]["Batch001_overlap"] == 0
    assert [row["seed_proposal_key"] for row in first["rows"]] == [
        row["seed_proposal_key"] for row in second["rows"]
    ]
    assert worksheet_sha(load_batch002()) == first["sha"]
    assert first["source_plan"]["B"]["identity"] == "HOLD"
    assert first["source_plan"]["B"]["path_identities"] == 620
    assert first["source_plan"]["B"]["leaf_occurrence_sum"] == 626
    assert first["source_plan"]["C"]["unique_content"] == 30696
    assert first["source_plan"]["C"]["occurrence_sum"] == 47559
