"""Phase 10 — coverage + population batch tests (pure, no DB).

    python -m pytest tests/test_obligation_quality_coverage.py -q
"""
from services.obligation_quality_coverage import compute_coverage
from services.obligation_quality_batch import (
    empty_check_report,
    collect_obligations_from_diagnosis,
    collect_obligations_from_work_schedules,
    evaluate_population,
)
from services.obligation_quality_evaluator import READY, TRACE_REQUIRED, CORRECTION_REQUIRED


def test_compute_coverage_basic():
    rows = [
        {"obligation_id": "a", "quality_status": READY, "quality_reason": "OK"},
        {"obligation_id": "b", "quality_status": TRACE_REQUIRED, "quality_reason": "EVIDENCE_INSUFFICIENT"},
        {"obligation_id": "c", "quality_status": TRACE_REQUIRED, "quality_reason": "EVIDENCE_INSUFFICIENT"},
        {"obligation_id": "d", "quality_status": CORRECTION_REQUIRED, "quality_reason": "LAW_LINK_ERROR"},
    ]
    cov = compute_coverage(rows)
    assert cov["total"] == 4
    assert cov["distribution"] == {READY: 1, TRACE_REQUIRED: 2, CORRECTION_REQUIRED: 1}
    assert cov["fully_classified"] is True
    assert cov["top_reasons"][0] == {"reason": "EVIDENCE_INSUFFICIENT", "count": 2}


def test_compute_coverage_empty():
    cov = compute_coverage([])
    assert cov["total"] == 0
    assert cov["fully_classified"] is False


def test_collect_from_work_schedules():
    rows = [
        {"rule_code": "R1", "law_name": "산안법", "law_article": "17"},
        {"rule_code": "R1", "law_name": "산안법", "law_article": "17"},
        {"rule_code": "R2", "law_name": "산안법", "law_article": "18"},
        {"rule_code": "R2", "law_name": "다른법", "law_article": "1"},
        {"rule_code": "", "law_name": "x"},
        {"law_name": "no code"},
    ]
    obs, conflicts = collect_obligations_from_work_schedules(rows)
    ids = {o["obligation_id"] for o in obs}
    assert ids == {"R1", "R2"}
    assert "R2" in conflicts
    assert "R1" not in conflicts


def test_collect_dedup_and_conflict_diagnosis():
    rows = [
        {"result_data": {"inspection_required": [
            {"rule_id": "R1", "law_name": "산안법", "law_article": "17"},
            {"rule_code": "R2", "law_name": "산안법", "law_article": "18"},
        ]}},
        {"result_data": {"rules": [
            {"rule_id": "R3", "law_name": "산안법", "article_no": "99"},
        ]}},
        {"result_data": {"inspection_required": [
            {"rule_id": "R3", "law_name": "다른법", "law_article": "1"},
        ]}},
    ]
    obligations, conflicts = collect_obligations_from_diagnosis(rows)
    ids = {o["obligation_id"] for o in obligations}
    assert ids == {"R1", "R2", "R3"}
    assert "R3" in conflicts


def test_evaluate_population_empty_report_is_trace():
    obs = [{"obligation_id": "R1", "law_name": "산안법", "law_article": "17"}]
    out = evaluate_population(obs)
    assert out[0]["quality_status"] == TRACE_REQUIRED
    assert out[0]["quality_reason"] == "EVIDENCE_INSUFFICIENT"


def test_evaluate_population_law_missing_is_correction():
    obs = [{"obligation_id": "R2", "law_name": "", "law_article": ""}]
    out = evaluate_population(obs)
    assert out[0]["quality_status"] == CORRECTION_REQUIRED
    assert out[0]["quality_reason"] == "LAW_LINK_ERROR"


def test_evaluate_population_conflict_is_correction():
    obs = [{"obligation_id": "R3", "law_name": "산안법", "law_article": "99"}]
    out = evaluate_population(obs, conflicts={"R3"})
    assert out[0]["quality_status"] == CORRECTION_REQUIRED
    assert out[0]["quality_reason"] == "DUPLICATE_OBLIGATION"


def test_evaluate_population_real_report_can_be_ready():
    obs = [{"obligation_id": "R4", "law_name": "산안법", "law_article": "17"}]
    report = {
        "report_id": "rptR4",
        "status_summary": {
            "claim": {"CLAIM_PRESENT": 1},
            "evidence": {"EVIDENCE_ATTACHED": 1},
            "chain": {"EVIDENCE_CHAIN_COMPLETE": 1},
        },
        "observation_records": [{}],
    }
    out = evaluate_population(obs, reports_by_id={"R4": report})
    assert out[0]["quality_status"] == READY
    assert out[0]["check_report_id"] == "rptR4"


def test_empty_check_report_wellformed():
    rep = empty_check_report("X")
    assert "status_summary" in rep and "observation_records" in rep
    assert rep["observation_records"] == []
