"""WO-RISK-04-REVIEW-001 Batch 001 evidence pack. No semantic decision."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.risk04.review_batch import batch_sha
from tools.risk04.review_evidence import (
    FROZEN_BATCH_PATH,
    FROZEN_BATCH_SHA,
    OWNER_EMPTY,
    OWNER_PENDING,
    REVIEW_INPUT_PATH,
    WORKSHEET_FIELDS,
    assert_frozen_batch,
    build_review_input,
    load_frozen_batch,
    load_review_input,
    review_input_sha,
)

ARTIFACTS = Path("artifacts/risk01")
EVIDENCE = Path("tools/risk04/review_evidence.py")


def test_frozen_batch_sha_keys_order_unchanged():
    rows = load_frozen_batch()
    assert assert_frozen_batch(rows) == FROZEN_BATCH_SHA
    assert len(rows) == 100
    keys = [row["seed_proposal_key"] for row in rows]
    assert len(set(keys)) == 100
    assert batch_sha(rows) == FROZEN_BATCH_SHA
    assert sum(1 for row in rows if row["kind"] == "PROCESS") == 50
    assert sum(1 for row in rows if row["kind"] == "TASK") == 50
    assert sum(1 for row in rows if row["source_id"] == "CIC_W") == 50
    assert sum(1 for row in rows if row["source_id"] == "KALIS_RISK_PROFILE") == 50
    assert sum(1 for row in rows if row["source_id"] == "KOSHA_CONSTRUCTION_PROCESS") == 0
    # File bytes are the freeze; this test must not rewrite them.
    assert FROZEN_BATCH_PATH.read_bytes().count(b"\n") >= 100


def test_committed_review_input_matches_frozen_keys_and_owner_pending():
    frozen = load_frozen_batch()
    rows = load_review_input()
    assert [field for field in WORKSHEET_FIELDS] == list(rows[0].keys())
    assert len(rows) == 100
    assert [row["seed_proposal_key"] for row in rows] == [row["seed_proposal_key"] for row in frozen]
    assert [row["batch_no"] for row in rows] == [str(i) for i in range(1, 101)]
    assert len({row["seed_proposal_key"] for row in rows}) == 100
    assert all(row["owner_decision"] == OWNER_PENDING for row in rows)
    assert all(row["merge_candidate_keys"] == OWNER_EMPTY for row in rows)
    assert all(row["owner_reason"] == OWNER_EMPTY for row in rows)
    assert all(row["kind"] in {"PROCESS", "TASK"} for row in rows)
    for row in rows:
        if row["kind"] == "PROCESS":
            assert row["depth"] != ""
            assert row["child_count"] != ""
            assert row["is_leaf"] in {"YES", "NO"}
            if int(row["depth"]) > 1:
                assert row["parent_path"] != ""
        else:
            assert row["parent_path"] != ""
            assert row["risk_content_support"] != ""
            samples = [row["risk_sample_1"], row["risk_sample_2"], row["risk_sample_3"]]
            assert sum(1 for sample in samples if sample) <= 3
    forbidden = {"APPROVED", "ACTIVE", "KEEP_AS_DISTINCT", "MERGE_CANDIDATE", "REJECT"}
    assert not forbidden.intersection({row["owner_decision"] for row in rows})


def test_review_evidence_does_not_emit_semantic_decisions():
    src = EVIDENCE.read_text(encoding="utf-8")
    assert "uuid4" not in src
    assert "import uuid" not in src
    assert "datetime" not in src.lower()
    assert "openai" not in src.lower()
    assert "embedding" not in src.lower()
    assert "rapidfuzz" not in src.lower()
    assert OWNER_PENDING in src
    assert "owner_decision" in src


@pytest.mark.skipif(
    not (ARTIFACTS / "source_c/kalis_risk_profile.csv").exists(),
    reason="local RISK-01 artifacts required to rebuild review evidence",
)
def test_review_input_determinism_and_source_preservation():
    first = build_review_input(ARTIFACTS)
    second = build_review_input(ARTIFACTS)
    assert first["review_input_sha"] == second["review_input_sha"]
    assert first["frozen_sha"] == FROZEN_BATCH_SHA
    assert first["missing"] == 0
    assert first["extra"] == 0
    assert first["duplicate"] == 0
    assert first["facts"]["owner_pending"] == 100
    assert first["facts"]["keep_as_distinct"] == 0
    assert first["facts"]["seed_universe_total"] == 3103
    assert first["source_plan"]["A"]["nodes"] == 1722
    assert first["source_plan"]["B"]["rows"] == 626
    assert first["source_plan"]["B"]["path_identities"] == 620
    assert first["source_plan"]["B"]["identity"] == "HOLD"
    assert first["source_plan"]["B"]["leaf_occurrence_sum"] == 626
    assert first["source_plan"]["C"]["unique_content"] == 30696
    assert first["source_plan"]["C"]["occurrence_sum"] == 47559
    samples1 = [(row["risk_sample_1"], row["risk_sample_2"], row["risk_sample_3"]) for row in first["rows"]]
    samples2 = [(row["risk_sample_1"], row["risk_sample_2"], row["risk_sample_3"]) for row in second["rows"]]
    assert samples1 == samples2
    committed = load_review_input()
    assert review_input_sha(committed) == first["review_input_sha"]
    kalis = [row for row in first["rows"] if row["kind"] == "TASK"]
    assert all(row["risk_sample_1"] for row in kalis)
