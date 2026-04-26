"""
STEP 0 — inspection_sets 현재 동작 스냅샷.
"""
from __future__ import annotations

from datetime import date

import pytest
from dateutil.relativedelta import relativedelta
from pydantic import ValidationError

from routers import inspection_sets as isets
from schemas.inspection_sets import ManualInspectionSetBody


def test_get_delta_month_3():
    assert isets._get_delta("month", 3) == relativedelta(months=3)


def test_next_planned_from_past_base_returns_future_or_today():
    base = date.today() - relativedelta(months=14)
    planned = isets._next_planned_from(base, "month", 3)
    assert planned >= date.today()


def test_meets_4_conditions_all_true():
    row = {
        "schedule_anchor_date": date.today().isoformat(),
        "cycle_unit": "month",
        "assignee_user_id": "u1",
        "description": "점검 의무",
        "legal_rule_code": None,
        "legal_rule_id": None,
    }
    assert isets._meets_4_conditions(row) is True


def test_meets_4_conditions_missing_assignee_false():
    row = {
        "schedule_anchor_date": date.today().isoformat(),
        "cycle_unit": "month",
        "assignee_user_id": None,
        "description": "점검 의무",
        "legal_rule_code": "L-1",
        "legal_rule_id": None,
    }
    assert isets._meets_4_conditions(row) is False


def test_build_law_engine_row_contains_required_fields():
    row = {
        "id": "set-1",
        "factory_id": "fac-1",
        "company_id": "co-1",
        "schedule_anchor_date": date.today().isoformat(),
        "cycle_unit": "month",
        "cycle_value": 1,
        "assignee_user_id": "u1",
        "description": "의무 설명",
        "inspection_category": "INSPECT",
        "law_name": "산안법",
        "law_article": "제1조",
        "legal_rule_code": "R001",
        "legal_rule_id": "RID001",
    }
    out = isets._build_law_engine_row(row)
    assert out["factory_id"] == "fac-1"
    assert out["inspection_set_id"] == "set-1"
    assert out["assigned_user_id"] == "u1"
    assert out["source_type"] == "LAW_ENGINE"
    assert out["status_code"] == "PENDING"
    assert out["rule_code"] == "R001"


def test_manual_inspection_set_body_required_fields():
    body = ManualInspectionSetBody(factory_id="f1", inspection_set_name="정기 점검")
    assert body.factory_id == "f1"
    assert body.cycle_unit == "month"
    with pytest.raises(ValidationError):
        ManualInspectionSetBody(factory_id="f1")
