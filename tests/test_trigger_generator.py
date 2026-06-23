"""Tests for trigger_generator + trigger_obligation_generator (CURSOR-TASK-001)."""

from unittest.mock import MagicMock

from services.trigger_generator import (
    generate_trigger_codes_from_row,
)
from services.trigger_obligation_generator import (
    generate_obligation_candidates,
    match_clauses_for_trigger,
)


def test_generate_trigger_codes_example_factory():
    row = {
        "employee_count": 80,
        "has_confined_space": True,
    }
    equipment = [{"equipment_type_code": "CRANE", "is_operating": True}]
    codes = generate_trigger_codes_from_row(row, equipment)
    assert codes == [
        "BUSINESS:REGISTERED",
        "THRESHOLD:EMPLOYEE_50_PLUS",
        "WORK:CONFINED_SPACE",
        "EQUIPMENT:CRANE",
        "EQUIPMENT_ACT:CRANE_USE",
    ]


def test_generate_trigger_codes_has_star_only_when_true():
    row = {
        "employee_count": 10,
        "has_confined_space": False,
        "has_blasting": True,
    }
    codes = generate_trigger_codes_from_row(row, [])
    assert "WORK:CONFINED_SPACE" not in codes
    assert "WORK:BLASTING" in codes
    assert "THRESHOLD:EMPLOYEE_50_PLUS" not in codes


def test_obligation_candidates_business_registered_null_condition():
    clauses = [
        {
            "id": "c1",
            "source_article_id": "a1",
            "condition_text": None,
            "action_text": "사업주는 안전조치를 해야 한다.",
            "content_type": "OBLIGATION",
            "executor_text": "사업주",
        },
        {
            "id": "c2",
            "source_article_id": "a2",
            "condition_text": "밀폐공간에서 작업하는 경우",
            "action_text": "사업주는 환기를 해야 한다.",
            "content_type": "OBLIGATION",
            "executor_text": "사업주",
        },
    ]
    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.eq.return_value.range.return_value.execute.return_value.data = clauses

    out = generate_obligation_candidates(["BUSINESS:REGISTERED"], sb)
    assert len(out) == 1
    assert out[0]["source_article_id"] == "a1"
    assert out[0]["confidence"] == "MEDIUM"


def test_obligation_candidates_confined_space_high_confidence():
    clauses = [
        {
            "id": "c1",
            "source_article_id": "a1",
            "condition_text": "밀폐공간에서 작업하는 경우",
            "action_text": "사업주는 산소농도를 측정해야 한다.",
            "content_type": "OBLIGATION",
            "executor_text": "사업주",
        }
    ]
    matched = match_clauses_for_trigger(clauses, "WORK:CONFINED_SPACE")
    assert len(matched) == 1


def test_obligation_candidates_dedupe_by_article():
    clauses = [
        {
            "id": "c1",
            "source_article_id": "a1",
            "condition_text": None,
            "action_text": "사업주는 해야 한다.",
            "content_type": "OBLIGATION",
            "executor_text": "사업주",
        },
        {
            "id": "c2",
            "source_article_id": "a1",
            "condition_text": "밀폐공간",
            "action_text": "사업주는 환기를 해야 한다.",
            "content_type": "OBLIGATION",
            "executor_text": "사업주",
        },
    ]
    sb = MagicMock()
    sb.table.return_value.select.return_value.in_.return_value.eq.return_value.range.return_value.execute.return_value.data = clauses

    out = generate_obligation_candidates(
        ["BUSINESS:REGISTERED", "WORK:CONFINED_SPACE"], sb
    )
    assert len(out) == 1
    assert out[0]["trigger_code"] == "WORK:CONFINED_SPACE"
    assert out[0]["confidence"] == "HIGH"
