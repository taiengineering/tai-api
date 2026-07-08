"""WO-ENG-001 — FIELD_MAP Axis Value Builder tests.

One assertion group per builder, covering normalize/derive/augment/gap paths.
pytest-discoverable; also runs standalone via `python tests/…py`.
No engine/FIELD_MAP modification; no live wiring.
"""

from __future__ import annotations

from services.axis_value_builder import (
    build_employee_count, build_area_size, build_power_capacity,
    build_storage_capacity, build_monetary_value, build_facility_type,
    build_process_type, build_equipment_type, build_voltage_level,
    build_concentration_level, build_distance_value, build_all, facility_view,
)


def test_employee_count_combined():
    r = build_employee_count({"direct_workers": 40, "subcon_workers": 15})
    assert r.value == 55 and r.method == "COMBINED"


def test_employee_count_fallback():
    r = build_employee_count({"worker_count": 30})
    assert r.value == 30 and r.method == "FALLBACK"


def test_area_size_fallback_chain():
    assert build_area_size({"floor_area": 1200}).value == 1200
    assert build_area_size(
        {"building_register": {"total_floor_area": 999}}).value == 999
    assert build_area_size({"total_floor_area": 4200}).method == "DIRECT"


def test_power_capacity():
    assert build_power_capacity({"electrical_capacity_kw": 500}).value == 500


def test_storage_capacity_units():
    assert build_storage_capacity({"gas_capacity_m3": 30}).value == 30
    assert build_storage_capacity(
        {"gas_capacity_kg": 100, "gas_density_kg_m3": 2.0}).value == 50.0
    # kg without density cannot convert -> gap
    assert build_storage_capacity({"gas_capacity_kg": 100}).method == "GAP"
    # engine note stays AMBIGUOUS for produced values
    assert build_storage_capacity({"gas_capacity_m3": 30}).engine_note == "AMBIGUOUS_QUALITY"


def test_monetary_scale():
    assert build_monetary_value({"construction_amount": 1_000_000}).value == 1_000_000
    assert build_monetary_value({"contract_amount_eok": 12}).value == 12 * 1e8
    assert build_monetary_value({"project_amount": 5}).value == 5 * 1e8


def test_facility_type_and_fire_target():
    assert build_facility_type({"building_use_type": "D-1"}).value == "D-1"
    assert build_facility_type({"use_code": "U9"}).method == "FALLBACK"
    r = build_facility_type({"building_use_type": "D-1"},
                            fire_target_map={"D-1": "FIRE_TARGET_A"})
    assert r.value == "FIRE_TARGET_A" and r.method == "LOOKUP"


def test_process_type_augment():
    assert build_process_type({"ksic_major": "C26"}).value == "C26"
    r = build_process_type(
        {"ksic_major": "C26", "process_list": [{"type": "welding"}]},
        process_map={"welding": "P-WELD"})
    assert "P-WELD" in r.value and r.method == "LOOKUP"


def test_equipment_type_list_and_flags():
    r = build_equipment_type({"equipment_list": [{"type": "transformer"}]})
    assert r.value == ["transformer"] and r.engine_note == "NO_FAC_COL"
    r2 = build_equipment_type({"has_boiler": True},
                              flag_map={"has_boiler": "boiler"})
    assert "boiler" in r2.value


def test_collection_gaps():
    assert build_voltage_level({}).method == "GAP"
    assert build_concentration_level({}).method == "GAP"
    assert build_distance_value({}).method == "GAP"
    # voltage supplied directly still builds
    assert build_voltage_level({"voltage_level": 22900}).value == 22900


def test_build_all_and_facility_view():
    ci = {"direct_workers": 40, "subcon_workers": 15, "total_floor_area": 4200,
          "electric_capacity": 900, "building_use_type": "D-1", "ksic_major": "C26",
          "gas_capacity_m3": 30, "project_amount": 12,
          "equipment_list": [{"type": "transformer"}]}
    allv = build_all(ci)
    assert set(allv) == {
        "employee_count", "area_size", "power_capacity", "storage_capacity",
        "monetary_value", "facility_type", "process_type", "equipment_type",
        "voltage_level", "concentration_level", "distance_value"}
    fv = facility_view(ci)
    # equipment_type has no fac_col -> excluded; voltage/conc/dist are gaps
    assert "employee_count" in fv and fv["construction_amount"] == 12 * 1e8
    assert "transformer_capacity_kva" not in fv  # voltage gap


def _main() -> None:
    ci = {"direct_workers": 40, "subcon_workers": 15, "total_floor_area": 4200,
          "electric_capacity": 900, "building_use_type": "D-1", "ksic_major": "C26",
          "gas_capacity_m3": 30, "project_amount": 12,
          "equipment_list": [{"type": "transformer"}]}
    print("%-20s %-10s %-14s %-14s %s" % ("axis", "method", "value", "engine", "sources"))
    print("-" * 88)
    for axis, av in build_all(ci).items():
        print("%-20s %-10s %-14s %-14s %s" % (
            axis, av.method, str(av.value)[:14], av.engine_note, ",".join(av.sources_used)))
    fns = [f for f in globals() if f.startswith("test_")]
    for f in fns:
        globals()[f]()
    print("-" * 88)
    print(f"{len(fns)}/{len(fns)} builder tests PASS")


if __name__ == "__main__":
    _main()
