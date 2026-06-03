"""Phase 9 — Obligation Quality Evaluator tests (pure, no DB).

These assert the evaluator's OWN deterministic output against fixtures. Run:
    python -m pytest tests/test_obligation_quality_evaluator.py -q
"""
import json
from pathlib import Path

from services.obligation_quality_evaluator import (
    evaluate_quality,
    evaluate_batch,
    is_schedulable,
    READY,
    TRACE_REQUIRED,
    CORRECTION_REQUIRED,
)

_CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "obligation_quality_cases.json").read_text(encoding="utf-8")
)


def test_fixture_count():
    assert len(_CASES) >= 30


def test_each_case_status_and_reason():
    for c in _CASES:
        res = evaluate_quality(c["obligation"], c["check_report"], duplicate=c.get("duplicate", False))
        assert res["quality_status"] in (READY, TRACE_REQUIRED, CORRECTION_REQUIRED)
        assert res["quality_status"] == c["expect_status"], f"{c['name']}: {res} != {c['expect_status']}"
        if "expect_reason" in c:
            assert res["quality_reason"] == c["expect_reason"], f"{c['name']}: {res} != {c['expect_reason']}"


def test_all_three_categories_present():
    statuses = {c["expect_status"] for c in _CASES}
    assert {READY, TRACE_REQUIRED, CORRECTION_REQUIRED} <= statuses


def test_required_reason_categories_present():
    reasons = {c.get("expect_reason") for c in _CASES}
    # 중복 / 근거누락 / 조치누락 카테고리 포함
    assert "DUPLICATE_OBLIGATION" in reasons
    assert "EVIDENCE_INSUFFICIENT" in reasons
    assert "ACTION_INSUFFICIENT" in reasons


def test_batch_duplicate_detection():
    obs = [
        {"obligation_id": "DUP", "law_name": "산안법", "article_no": "1"},
        {"obligation_id": "DUP", "law_name": "산안법", "article_no": "1"},
        {"obligation_id": "UNIQ", "law_name": "산안법", "article_no": "2"},
    ]
    report = {
        "report_id": "r",
        "status_summary": {
            "claim": {"CLAIM_PRESENT": 1},
            "evidence": {"EVIDENCE_ATTACHED": 1},
            "chain": {"EVIDENCE_CHAIN_COMPLETE": 1},
        },
        "observation_records": [{}],
    }
    out = evaluate_batch(obs, {"DUP": report, "UNIQ": report})
    dup = [o for o in out if o["obligation_id"] == "DUP"]
    assert len(dup) == 2
    assert all(
        o["quality_status"] == CORRECTION_REQUIRED and o["quality_reason"] == "DUPLICATE_OBLIGATION"
        for o in dup
    )
    uniq = [o for o in out if o["obligation_id"] == "UNIQ"][0]
    assert uniq["quality_status"] == READY
    assert uniq["check_report_id"] == "r"


def test_is_schedulable_only_ready():
    assert is_schedulable(READY) is True
    assert is_schedulable(TRACE_REQUIRED) is False
    assert is_schedulable(CORRECTION_REQUIRED) is False
    assert is_schedulable(None) is False
    assert is_schedulable("anything") is False
