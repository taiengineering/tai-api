"""STEP7 — INDUSTRIAL canonical → Marketing 29 assembler tests.

WO-SAFE-IND-ASSEMBLER-SCHEMA-COMPAT-002:
  mock 은 CURRENT PRODUCTION PHYSICAL CONTRACT 로 고정한다(미래 schema mock 금지).
  factory_process 는 hazard_codes/worker_count/activity_types 를 제공하지 않고,
  equipment_assets 는 usage_types/relation_types 를 제공하지 않는다.
  따라서 active/operating row 가 있으면 process_list/equipment_list = UNRESOLVED.
"""
import copy
from services.safe_industrial_canonical_assembler import (
    assemble_industrial_marketing_contract, TARGET_FIELDS, CONTRACT_VERSION, SECTOR,
)

class _Res:
    def __init__(s, d): s.data = d
class _Q:
    def __init__(s, store, c): s.store = store; s.c = c; s._f = {}
    def select(s, *a, **k): return s
    def eq(s, col, val): s._f[col] = val; return s
    def limit(s, n): return s
    def insert(s, *a, **k): s.c["writes"] += 1; return s
    def update(s, *a, **k): s.c["writes"] += 1; return s
    def delete(s, *a, **k): s.c["writes"] += 1; return s
    def upsert(s, *a, **k): s.c["writes"] += 1; return s
    def execute(s):
        s.c.setdefault("reads", 0); s.c["reads"] += 1
        rows = [r for r in s.store if all(r.get(k) == v for k, v in s._f.items())]
        return _Res(copy.deepcopy(rows))
class _T:
    def __init__(s, name, store, c): s.name = name; s.store = store; s.c = c
    def select(s, *a, **k): return _Q(s.store, s.c)
    def insert(s, *a, **k): s.c["writes"] += 1; return _Q(s.store, s.c)
    def update(s, *a, **k): s.c["writes"] += 1; return _Q(s.store, s.c)
    def delete(s, *a, **k): s.c["writes"] += 1; return _Q(s.store, s.c)
class FakeSB:
    def __init__(s, **stores):
        s.stores = {"factories": [], "factory_process": [], "equipment_assets": [],
                    "factory_materials": [], "system_codes": []}
        s.stores.update(stores)
        s.counters = {"writes": 0, "reads": 0}
    def table(s, n): s.stores.setdefault(n, []); return _T(n, s.stores[n], s.counters)

def _sb(fac=None, **kw):
    facrow = [{"id": "F1", **(fac or {})}] if fac is not None else [{"id": "F1"}]
    return FakeSB(factories=facrow, **kw)

SC = [{"category": "factory_business_activity", "code": "REMODEL_OPERATION", "code_name": "리모델링 수행", "is_active": True},
      {"category": "factory_hazardous_environment", "code": "INDOOR_HIGH_HEAT", "code_name": "고열작업(실내)", "is_active": True}]
BC = [{"category": "factory_building_composition", "code": "MIX", "code_name": "복합", "is_active": True}]
RD = [{"category": "factory_regulatory_designation", "code": "SOIL", "code_name": "특정토양오염관리대상시설", "is_active": True}]


def test_A7_key_count_29():
    r = assemble_industrial_marketing_contract(_sb(), "F1")
    assert list(r["values"].keys()) == TARGET_FIELDS
    assert len(r["values"]) == 29
    assert r["contract_version"] == CONTRACT_VERSION and r["sector"] == SECTOR

def test_A7_extra_key_0():
    r = assemble_industrial_marketing_contract(_sb(), "F1")
    assert set(r["values"]) == set(TARGET_FIELDS)

def test_A7_worker_count_employee_only():
    r = assemble_industrial_marketing_contract(_sb({"employee_count": 10, "total_worker_count_calc": 99}), "F1")
    assert r["values"]["worker_count"] == 10

def test_A7_transforms():
    r = assemble_industrial_marketing_contract(_sb({
        "building_area": 123.4, "underground_floor_count": 2, "completion_year": 2020, "electrical_capacity_kw": 50}), "F1")
    v = r["values"]
    assert v["total_floor_area"] == 123.4 and v["basement_count"] == 2 and v["built_year"] == 2020 and v["electric_capacity"] == 50

def test_T7_column_exists_null_resolved_none():
    r = assemble_industrial_marketing_contract(_sb({"work_height_m": None}), "F1")
    assert r["values"]["work_height_m"] is None
    assert "work_height_m" not in r["unresolved_fields"]

def test_T6_column_absent_unresolved():
    r = assemble_industrial_marketing_contract(_sb({"employee_count": 5}), "F1")
    assert r["values"]["work_height_m"] is None
    assert "work_height_m" in r["unresolved_fields"]

def test_T8_false_zero_preserved_when_present():
    r = assemble_industrial_marketing_contract(
        _sb({"has_truck_loading_unloading": False, "truck_loading_height_m": 0, "has_boiler": False, "gas_capacity_kg": 0}), "F1")
    v = r["values"]
    assert v["has_truck_loading_unloading"] is False and "has_truck_loading_unloading" not in r["unresolved_fields"]
    assert v["truck_loading_height_m"] == 0 and "truck_loading_height_m" not in r["unresolved_fields"]
    assert v["has_boiler"] is False and v["gas_capacity_kg"] == 0

def test_A7_empty_array_preserved():
    r = assemble_industrial_marketing_contract(_sb({"business_activity_types": []}), "F1")
    assert r["values"]["business_activity_types"] == []

def test_A7_business_codes_to_labels():
    sb = _sb({"business_activity_types": ["REMODEL_OPERATION"]}, system_codes=SC)
    r = assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["business_activity_types"] == ["리모델링 수행"]

def test_A7_unknown_business_unresolved():
    sb = _sb({"business_activity_types": ["NOPE"]}, system_codes=SC)
    r = assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["business_activity_types"] is None and "business_activity_types" in r["unresolved_fields"]

def test_A7_hazard_codes_to_labels():
    sb = _sb({"hazardous_work_environments": ["INDOOR_HIGH_HEAT"]}, system_codes=SC)
    r = assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["hazardous_work_environments"] == ["고열작업(실내)"]

def test_T9_vocab_source_column_absent_unresolved():
    r = assemble_industrial_marketing_contract(_sb({"employee_count": 1}), "F1")
    assert r["values"]["business_activity_types"] is None and "business_activity_types" in r["unresolved_fields"]
    assert r["values"]["hazardous_work_environments"] is None and "hazardous_work_environments" in r["unresolved_fields"]

def test_T9_vocab_column_exists_null_resolved_none():
    r = assemble_industrial_marketing_contract(_sb({"business_activity_types": None, "hazardous_work_environments": None}), "F1")
    assert r["values"]["business_activity_types"] is None and "business_activity_types" not in r["unresolved_fields"]
    assert r["values"]["hazardous_work_environments"] is None and "hazardous_work_environments" not in r["unresolved_fields"]

def test_A7_building_use_unresolved_when_code_present():
    r = assemble_industrial_marketing_contract(_sb({"building_use_code": "X"}), "F1")
    assert r["values"]["building_use_type"] is None and "building_use_type" in r["unresolved_fields"]

def test_A7_main_structure_unresolved_when_code_present():
    r = assemble_industrial_marketing_contract(_sb({"building_structure_code": "RC"}), "F1")
    assert r["values"]["main_structure"] is None and "main_structure" in r["unresolved_fields"]

def test_A7_regulated_hazmat_no_auto():
    r = assemble_industrial_marketing_contract(_sb({"is_hazardous_material": True, "regulatory_designation_codes": None}), "F1")
    assert r["values"]["regulated_facility_types"] is None

def test_T11_material_active_rename_and_handling_preserve():
    sb = _sb(factory_materials=[{"factory_id": "F1", "is_active": True, "material_name": "톨루엔", "material_category_code": "FL", "handling_mode_codes": []}])
    r = assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["material_profile"] == [{"material_category": "FL", "handling_modes": []}]

def test_T11_material_handling_null_vs_empty():
    sb_null = _sb(factory_materials=[{"factory_id": "F1", "is_active": True, "material_category_code": "FL", "handling_mode_codes": None}])
    r_null = assemble_industrial_marketing_contract(sb_null, "F1")
    assert r_null["values"]["material_profile"] == [{"material_category": "FL", "handling_modes": None}]
    sb_empty = _sb(factory_materials=[{"factory_id": "F1", "is_active": True, "material_category_code": "FL", "handling_mode_codes": []}])
    r_empty = assemble_industrial_marketing_contract(sb_empty, "F1")
    assert r_empty["values"]["material_profile"] == [{"material_category": "FL", "handling_modes": []}]

def test_T11_material_category_missing_unresolved():
    sb = _sb(factory_materials=[{"factory_id": "F1", "is_active": True, "material_name": "x", "material_category_code": None}])
    r = assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["material_profile"] is None and "material_profile" in r["unresolved_fields"]

def test_T11_material_zero_null_known_none():
    r = assemble_industrial_marketing_contract(_sb(), "F1")
    assert r["values"]["material_profile"] is None and "material_profile" not in r["unresolved_fields"]

def test_T11_material_inactive_excluded():
    sb = _sb(factory_materials=[{"factory_id": "F1", "is_active": False, "material_category_code": "FL"}])
    r = assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["material_profile"] is None

def test_T1_no_fatal_missing_column_in_select():
    import re
    src = open("services/safe_industrial_canonical_assembler.py").read()
    selects = re.findall(r'\.select\("([^"]*(?:"\s*"[^"]*)*)"\)', src)
    joined = " ".join(selects)
    for col in ("hazard_codes", "worker_count", "activity_types", "usage_types", "relation_types"):
        assert col not in joined, ("fatal column still in a .select():", col)

def test_T2_process_active_rows_unresolved():
    sb = _sb(factory_process=[{"factory_id": "F1", "is_active": True, "process_lv1": "용접"}])
    r = assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["process_list"] is None
    assert "process_list" in r["unresolved_fields"]

def test_T3_process_zero_rows_known_none():
    r = assemble_industrial_marketing_contract(_sb(), "F1")
    assert r["values"]["process_list"] is None
    assert "process_list" not in r["unresolved_fields"]

def test_T2_process_inactive_excluded_known_none():
    sb = _sb(factory_process=[{"factory_id": "F1", "is_active": False, "process_lv1": "x"}])
    r = assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["process_list"] is None and "process_list" not in r["unresolved_fields"]

def test_T4_equipment_operating_rows_unresolved():
    sb = _sb(equipment_assets=[{"factory_id": "F1", "is_operating": True, "asset_name": "펌프"}])
    r = assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["equipment_list"] is None
    assert "equipment_list" in r["unresolved_fields"]

def test_T5_equipment_zero_rows_known_none():
    r = assemble_industrial_marketing_contract(_sb(), "F1")
    assert r["values"]["equipment_list"] is None
    assert "equipment_list" not in r["unresolved_fields"]

def test_T5_equipment_inactive_excluded_known_none():
    sb = _sb(equipment_assets=[{"factory_id": "F1", "is_operating": False, "asset_name": "x"}])
    r = assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["equipment_list"] is None and "equipment_list" not in r["unresolved_fields"]

def test_T10_building_qual_valid_code_still_unresolved():
    sb = _sb({"building_composition_codes": ["MIX"]}, system_codes=BC)
    r = assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["building_qualifications"] is None
    assert "building_qualifications" in r["unresolved_fields"]
    assert r["provenance"]["building_qualifications"]["mode"] == "UNRESOLVED"

def test_T10_regulated_valid_code_still_unresolved():
    sb = _sb({"regulatory_designation_codes": ["SOIL"]}, system_codes=RD)
    r = assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["regulated_facility_types"] is None
    assert "regulated_facility_types" in r["unresolved_fields"]

def test_T10_no_partial_direct_label_output():
    sb = _sb({"building_composition_codes": ["MIX"], "regulatory_designation_codes": ["SOIL"]}, system_codes=BC + RD)
    r = assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["building_qualifications"] is None and r["values"]["regulated_facility_types"] is None

def test_A7_provenance_modes():
    # has_boiler KEY 를 fixture 에 존재시켜야 DIRECT(=present) 검증이 유효(absent 는 §5 로 UNRESOLVED).
    r = assemble_industrial_marketing_contract(_sb({"employee_count": 5, "building_area": 1.0, "has_boiler": True}), "F1")
    assert r["provenance"]["worker_count"]["mode"] == "TRANSFORM"
    assert r["provenance"]["has_boiler"]["mode"] == "DIRECT"
    assert r["provenance"]["process_list"]["mode"] in ("COMPOSITE", "UNRESOLVED")

def test_A7_no_db_write():
    sb = _sb({"employee_count": 5}, factory_process=[{"factory_id": "F1", "is_active": True, "process_lv1": "a"}],
             equipment_assets=[{"factory_id": "F1", "is_operating": True, "asset_name": "x"}],
             factory_materials=[{"factory_id": "F1", "is_active": True, "material_category_code": "FL"}],
             system_codes=SC)
    assemble_industrial_marketing_contract(sb, "F1")
    assert sb.counters["writes"] == 0

def test_A7_no_diagnosis_input_fields_query():
    src = open("services/safe_industrial_canonical_assembler.py").read()
    assert '.table("diagnosis_input_fields")' not in src

def test_T12_exact_denominator_29():
    sb = _sb({"building_composition_codes": ["MIX"]}, system_codes=BC,
             factory_process=[{"factory_id": "F1", "is_active": True, "process_lv1": "a"}],
             equipment_assets=[{"factory_id": "F1", "is_operating": True, "asset_name": "x"}])
    r = assemble_industrial_marketing_contract(sb, "F1")
    assert len(r["values"]) == 29 and list(r["values"].keys()) == TARGET_FIELDS
    assert sb.counters["writes"] == 0
