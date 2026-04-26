from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta

from services import inspection_sets_helpers as h


def test_get_delta_quarter():
    assert h._get_delta("quarter", 2) == relativedelta(months=6)


def test_next_planned_from_is_not_past():
    base = date.today() - relativedelta(years=2)
    out = h._next_planned_from(base, "year", 1)
    assert out >= date.today()


def test_build_next_schedule_row_source_mapping():
    row, _ = h._build_next_schedule_row(
        {
            "id": "s1",
            "factory_id": "f1",
            "company_id": "c1",
            "cycle_unit": "month",
            "cycle_value": 1,
            "source": "LEGAL_ENGINE",
            "inspection_category": "INSPECT",
            "inspection_set_name": "이름",
        },
        date.today(),
    )
    assert row["source_type"] == "LEGAL"
