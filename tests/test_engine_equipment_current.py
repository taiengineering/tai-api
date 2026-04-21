from datetime import date

from routers import engine_equipment as equipment


def test_repeat_type_map_snapshot():
    assert equipment.REPEAT_TYPE_MAP["day"] == "daily"
    assert equipment.REPEAT_TYPE_MAP["half_year"] == "half_yearly"
    assert equipment.REPEAT_TYPE_MAP["year"] == "yearly"


def test_build_schedules_for_repair_month_cycle_snapshot():
    iset = {
        "id": "set-1",
        "factory_id": "fac-1",
        "company_id": "co-1",
        "cycle_unit": "month",
        "cycle_value": 3,
        "inspection_category": "LEGAL",
        "inspection_set_name": "분기 점검",
    }
    rows = equipment._build_schedules_for_repair(
        iset=iset,
        anchor=date(2026, 1, 1),
        end=date(2026, 12, 31),
    )
    assert len(rows) == 4
    assert rows[0]["planned_date"] == "2026-01-01"
    assert rows[-1]["planned_date"] == "2026-10-01"
    assert rows[0]["repeat_type"] == "monthly"


def test_build_schedules_for_repair_defaults_to_yearly_when_unknown_unit():
    iset = {
        "id": "set-1",
        "factory_id": "fac-1",
        "cycle_unit": "unknown",
        "cycle_value": 1,
    }
    rows = equipment._build_schedules_for_repair(
        iset=iset,
        anchor=date(2026, 1, 1),
        end=date(2028, 1, 1),
    )
    assert len(rows) == 3
    assert rows[0]["repeat_type"] == "yearly"


def test_enrich_asset_row_sets_derived_flags_snapshot():
    row = {"asset_name": "펌프", "equipment_model_id": "m-1", "last_inspection_date": "2026-04-01"}
    enriched = equipment._enrich_asset_row(dict(row))

    assert enriched["has_model"] is True
    assert enriched["facility_category"] == ""
    assert enriched["rule_count"] == 0
    assert enriched["has_inspection"] is True
    assert enriched["has_failure"] is False


def test_enrich_asset_row_uses_model_id_alias():
    row = {"asset_name": "압축기", "model_id": "m-legacy", "equipment_type_code": "MECH"}
    enriched = equipment._enrich_asset_row(dict(row))

    assert enriched["has_model"] is True
    assert enriched["facility_category"] == "MECH"
