"""Tests for facility_applicability_eval pure logic."""

from services.facility_applicability_eval import (
    aggregate_applicability_status,
    compare_numeric,
    evaluate_draft_for_facility,
)


def test_compare_numeric_gte_match():
    assert compare_numeric(">=", 50, 60) == "MATCH_CANDIDATE"
    assert compare_numeric(">=", 50, 49) == "NOT_MATCHED"


def test_compare_numeric_missing():
    assert compare_numeric(">=", None, 10) == "MISSING_DATA"
    assert compare_numeric(">=", 10, None) == "MISSING_DATA"


def test_aggregate_match_only():
    assert aggregate_applicability_status({"MATCH_CANDIDATE"}) == "MATCH_CANDIDATE"


def test_aggregate_conflict():
    assert aggregate_applicability_status({"MATCH_CANDIDATE", "NOT_MATCHED"}) == "AMBIGUOUS"


def test_evaluate_draft_employee_threshold():
    facility = {"id": "f1", "employee_count": 60}
    numerics = [
        {
            "part_id": "p1",
            "binding_field": "employee_count",
            "operator": ">=",
            "value": 50,
        }
    ]
    out = evaluate_draft_for_facility(facility, "d1", numerics, [])
    assert out is not None
    overall, part_id, checks = out
    assert overall == "MATCH_CANDIDATE"
    assert part_id == "p1"
    assert checks[0][6] == "MATCH_CANDIDATE"
