"""STEP7 — INDUSTRIAL canonical → Marketing 29 assembler tests."""
import copy
import pytest
from services.safe_industrial_canonical_assembler import (
    assemble_industrial_marketing_contract, TARGET_FIELDS, CONTRACT_VERSION, SECTOR,
)

class _Res:
    def __init__(s,d): s.data=d
class _Q:
    def __init__(s,store,c): s.store=store; s.c=c; s._f={}
    def select(s,*a,**k): return s
    def eq(s,col,val): s._f[col]=val; return s
    def limit(s,n): return s
    def insert(s,*a,**k): s.c["writes"]+=1; return s
    def update(s,*a,**k): s.c["writes"]+=1; return s
    def delete(s,*a,**k): s.c["writes"]+=1; return s
    def upsert(s,*a,**k): s.c["writes"]+=1; return s
    def execute(s):
        s.c.setdefault("reads",0); s.c["reads"]+=1
        rows=[r for r in s.store if all(r.get(k)==v for k,v in s._f.items())]
        return _Res(copy.deepcopy(rows))
class _T:
    def __init__(s,name,store,c): s.name=name; s.store=store; s.c=c
    def select(s,*a,**k): return _Q(s.store,s.c)
    def insert(s,*a,**k): s.c["writes"]+=1; return _Q(s.store,s.c)
    def update(s,*a,**k): s.c["writes"]+=1; return _Q(s.store,s.c)
    def delete(s,*a,**k): s.c["writes"]+=1; return _Q(s.store,s.c)
class FakeSB:
    def __init__(s, **stores):
        s.stores={"factories":[], "factory_process":[], "equipment_assets":[], "factory_materials":[], "system_codes":[]}
        s.stores.update(stores)
        s.counters={"writes":0,"reads":0}
    def table(s,n): s.stores.setdefault(n,[]); return _T(n,s.stores[n],s.counters)

def _sb(fac=None, **kw):
    facrow=[{"id":"F1", **(fac or {})}] if fac is not None else [{"id":"F1"}]
    return FakeSB(factories=facrow, **kw)

# ---- denominator ----
def test_A7_key_count_29():
    r=assemble_industrial_marketing_contract(_sb(), "F1")
    assert list(r["values"].keys())==TARGET_FIELDS
    assert len(r["values"])==29
    assert r["contract_version"]==CONTRACT_VERSION and r["sector"]==SECTOR
def test_A7_extra_key_0():
    r=assemble_industrial_marketing_contract(_sb(), "F1")
    assert set(r["values"])==set(TARGET_FIELDS)

# ---- direct mapping ----
def test_A7_worker_count_employee_only():
    r=assemble_industrial_marketing_contract(_sb({"employee_count":10,"total_worker_count_calc":99}), "F1")
    assert r["values"]["worker_count"]==10  # calc ignored
def test_A7_transforms():
    r=assemble_industrial_marketing_contract(_sb({
        "building_area":123.4,"underground_floor_count":2,"completion_year":2020,"electrical_capacity_kw":50}), "F1")
    v=r["values"]
    assert v["total_floor_area"]==123.4 and v["basement_count"]==2 and v["built_year"]==2020 and v["electric_capacity"]==50
def test_A7_false_zero_null_preserved():
    r=assemble_industrial_marketing_contract(_sb({"has_boiler":False,"work_height_m":0,"gas_capacity_kg":None}), "F1")
    v=r["values"]
    assert v["has_boiler"] is False and v["work_height_m"]==0 and v["gas_capacity_kg"] is None
def test_A7_empty_array_preserved():
    r=assemble_industrial_marketing_contract(_sb({"business_activity_types":[]}), "F1")
    assert r["values"]["business_activity_types"]==[]

# ---- vocabulary ----
SC=[{"category":"factory_business_activity","code":"REMODEL_OPERATION","code_name":"리모델링 수행","is_active":True},
    {"category":"factory_hazardous_environment","code":"INDOOR_HIGH_HEAT","code_name":"고열작업(실내)","is_active":True}]
def test_A7_business_codes_to_labels():
    sb=_sb({"business_activity_types":["REMODEL_OPERATION"]}, system_codes=SC)
    r=assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["business_activity_types"]==["리모델링 수행"]
def test_A7_unknown_business_unresolved():
    sb=_sb({"business_activity_types":["NOPE"]}, system_codes=SC)
    r=assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["business_activity_types"] is None and "business_activity_types" in r["unresolved_fields"]
def test_A7_hazard_codes_to_labels():
    sb=_sb({"hazardous_work_environments":["INDOOR_HIGH_HEAT"]}, system_codes=SC)
    r=assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["hazardous_work_environments"]==["고열작업(실내)"]

# ---- no legal invention ----
def test_A7_building_use_unresolved_when_code_present():
    r=assemble_industrial_marketing_contract(_sb({"building_use_code":"X"}), "F1")
    assert r["values"]["building_use_type"] is None and "building_use_type" in r["unresolved_fields"]
def test_A7_main_structure_unresolved_when_code_present():
    r=assemble_industrial_marketing_contract(_sb({"building_structure_code":"RC"}), "F1")
    assert r["values"]["main_structure"] is None and "main_structure" in r["unresolved_fields"]
def test_A7_regulated_hazmat_no_auto():
    r=assemble_industrial_marketing_contract(_sb({"is_hazardous_material":True,"regulatory_designation_codes":None}), "F1")
    assert r["values"]["regulated_facility_types"] is None
def test_A7_building_qual_no_legal_guess():
    r=assemble_industrial_marketing_contract(_sb({"building_composition_codes":None}), "F1")
    assert r["values"]["building_qualifications"] is None

# ---- material ----
def test_A7_material_active_rename_and_handling_preserve():
    sb=_sb(factory_materials=[{"factory_id":"F1","is_active":True,"material_name":"톨루엔","material_category_code":"FL","handling_mode_codes":[]}])
    r=assemble_industrial_marketing_contract(sb, "F1")
    mp=r["values"]["material_profile"]
    assert mp==[{"material_category":"FL","handling_modes":[]}]  # material_name leak 0
def test_A7_material_category_missing_unresolved():
    sb=_sb(factory_materials=[{"factory_id":"F1","is_active":True,"material_name":"x","material_category_code":None}])
    r=assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["material_profile"] is None and "material_profile" in r["unresolved_fields"]
def test_A7_material_zero_null():
    r=assemble_industrial_marketing_contract(_sb(), "F1")
    assert r["values"]["material_profile"] is None
def test_A7_material_inactive_excluded():
    sb=_sb(factory_materials=[{"factory_id":"F1","is_active":False,"material_category_code":"FL"}])
    r=assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["material_profile"] is None

# ---- process ----
def test_A7_process_row_shape_and_name_priority():
    sb=_sb(factory_process=[{"factory_id":"F1","is_active":True,"process_name_manual":"용접","process_lv4":"L4",
        "hazard_codes":["H"],"worker_count":0,"is_primary":True,"activity_types":["WELD"]}])
    r=assemble_industrial_marketing_contract(sb, "F1")
    pl=r["values"]["process_list"]
    assert pl==[{"process_name":"용접","hazard_codes":["H"],"worker_count":0,"is_primary":True,"activity_type":["WELD"]}]
def test_A7_process_name_fallback():
    sb=_sb(factory_process=[{"factory_id":"F1","is_active":True,"process_lv2":"L2"}])
    r=assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["process_list"][0]["process_name"]=="L2"
def test_A7_process_unnamed_unresolved():
    sb=_sb(factory_process=[{"factory_id":"F1","is_active":True}])
    r=assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["process_list"] is None and "process_list" in r["unresolved_fields"]
def test_A7_process_zero_null():
    r=assemble_industrial_marketing_contract(_sb(), "F1")
    assert r["values"]["process_list"] is None

# ---- equipment ----
def test_A7_equipment_8key_and_preserve():
    sb=_sb(equipment_assets=[{"factory_id":"F1","is_operating":True,"equipment_type_code":"P","asset_name":"펌프",
        "quantity":0,"capacity_value":0,"capacity_unit":"kW","is_legal_target":False,"usage_types":["U"],
        "relation_types":["R"],"factory_process_id":"FP1"}])
    r=assemble_industrial_marketing_contract(sb, "F1")
    el=r["values"]["equipment_list"][0]
    assert set(el.keys())=={"equipment_type","asset_name","quantity","capacity_value","capacity_unit","is_legal_target","usage_type","relation_type"}
    assert el["quantity"]==0 and el["capacity_value"]==0 and el["is_legal_target"] is False
    assert el["usage_type"]==["U"] and el["relation_type"]==["R"]
    assert "factory_process_id" not in el   # transport leak 0
def test_A7_equipment_zero_null():
    r=assemble_industrial_marketing_contract(_sb(), "F1")
    assert r["values"]["equipment_list"] is None

# ---- provenance / mutation ----
def test_A7_provenance_modes():
    r=assemble_industrial_marketing_contract(_sb({"employee_count":5,"building_area":1.0}), "F1")
    assert r["provenance"]["worker_count"]["mode"]=="TRANSFORM"
    assert r["provenance"]["has_boiler"]["mode"]=="DIRECT"
    assert r["provenance"]["process_list"]["mode"]=="COMPOSITE"
def test_A7_no_db_write():
    sb=_sb({"employee_count":5}, factory_process=[{"factory_id":"F1","is_active":True,"process_lv1":"a"}],
           equipment_assets=[{"factory_id":"F1","is_operating":True,"asset_name":"x"}],
           factory_materials=[{"factory_id":"F1","is_active":True,"material_category_code":"FL"}],
           system_codes=SC)
    assemble_industrial_marketing_contract(sb, "F1")
    assert sb.counters["writes"]==0
def test_A7_no_diagnosis_input_fields_query():
    src=open("services/safe_industrial_canonical_assembler.py").read()
    assert '.table("diagnosis_input_fields")' not in src


# ── STEP7-PATCH-1: building_qualifications / regulated_facility_types 항상 UNRESOLVED ──
BC=[{"category":"factory_building_composition","code":"MIX","code_name":"도시형생활주택·타주택 복합","is_active":True}]
RD=[{"category":"factory_regulatory_designation","code":"SOIL","code_name":"특정토양오염관리대상시설","is_active":True}]
def test_A7P1_building_qual_valid_code_still_unresolved():
    sb=_sb({"building_composition_codes":["MIX"]}, system_codes=BC)
    r=assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["building_qualifications"] is None
    assert "building_qualifications" in r["unresolved_fields"]
    assert r["provenance"]["building_qualifications"]["mode"]=="UNRESOLVED"
def test_A7P1_building_qual_empty_unresolved():
    sb=_sb({"building_composition_codes":[]})
    r=assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["building_qualifications"] is None and "building_qualifications" in r["unresolved_fields"]
def test_A7P1_building_qual_null_unresolved():
    r=assemble_industrial_marketing_contract(_sb({"building_composition_codes":None}), "F1")
    assert r["values"]["building_qualifications"] is None and "building_qualifications" in r["unresolved_fields"]
def test_A7P1_regulated_valid_code_still_unresolved():
    sb=_sb({"regulatory_designation_codes":["SOIL"]}, system_codes=RD)
    r=assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["regulated_facility_types"] is None
    assert "regulated_facility_types" in r["unresolved_fields"]
    assert r["provenance"]["regulated_facility_types"]["mode"]=="UNRESOLVED"
def test_A7P1_regulated_empty_unresolved():
    sb=_sb({"regulatory_designation_codes":[]})
    r=assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["regulated_facility_types"] is None and "regulated_facility_types" in r["unresolved_fields"]
def test_A7P1_no_partial_direct_label_output():
    sb=_sb({"building_composition_codes":["MIX"],"regulatory_designation_codes":["SOIL"]}, system_codes=BC+RD)
    r=assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["building_qualifications"] is None and r["values"]["regulated_facility_types"] is None
def test_A7P1_business_hazard_regression_unchanged():
    sb=_sb({"business_activity_types":["REMODEL_OPERATION"],"hazardous_work_environments":["INDOOR_HIGH_HEAT"]}, system_codes=SC)
    r=assemble_industrial_marketing_contract(sb, "F1")
    assert r["values"]["business_activity_types"]==["리모델링 수행"]
    assert r["values"]["hazardous_work_environments"]==["고열작업(실내)"]
def test_A7P1_denominator_and_no_write():
    sb=_sb({"building_composition_codes":["MIX"]}, system_codes=BC)
    r=assemble_industrial_marketing_contract(sb, "F1")
    assert len(r["values"])==29 and list(r["values"].keys())==TARGET_FIELDS
    assert sb.counters["writes"]==0
