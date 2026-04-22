from datetime import date

from services import equipment_helpers as h


def test_now_iso_has_timezone_suffix_snapshot():
    now = h._now_iso()
    assert "T" in now
    assert now.endswith("+00:00")


def test_build_schedules_for_repair_weekly_count_snapshot():
    rows = h._build_schedules_for_repair(
        {
            "id": "set-1",
            "factory_id": "fac-1",
            "cycle_unit": "week",
            "cycle_value": 2,
            "inspection_category": "LEGAL",
            "inspection_set_name": "격주 점검",
        },
        anchor=date(2026, 1, 1),
        end=date(2026, 2, 15),
    )
    assert len(rows) == 4
    assert rows[0]["repeat_type"] == "weekly"
    assert rows[0]["repeat_interval"] == 2


def test_enrich_asset_row_without_model_snapshot():
    row = {"asset_name": "배관", "equipment_type_code": "UTILITY", "last_inspection_date": None}
    out = h._enrich_asset_row(dict(row))
    assert out["has_model"] is False
    assert out["facility_category"] == "UTILITY"
    assert out["has_inspection"] is False
    assert out["has_failure"] is False


def test_category_map_contains_expected_labels():
    assert h.CATEGORY_MAP["MECH"] == "기계설비"
    assert h.CATEGORY_MAP["FIRE"] == "소방설비"
