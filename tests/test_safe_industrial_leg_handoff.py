"""STEP8 — INDUSTRIAL canonical → LEG handoff tests."""
import pytest
import services.safe_industrial_leg_handoff as H
from clients.leg_runtime_client import _LEG_INPUT_FIELDS

def _contract(values=None, unresolved=None):
    return {"contract_version":"MKT_IND_PAID_CONTRACT_V1","sector":"INDUSTRIAL","factory_id":"F1",
            "values": values or {}, "unresolved_fields": unresolved or [], "provenance":{}}

FULL_VALUES = {
    "address":"서울","ksic_major":"2011","worker_count":0,"total_floor_area":123.4,"floor_count":3,
    "basement_count":1,"building_use_type":"공장","built_year":2010,"main_structure":"RC",
    "has_safety_manager":True,"electric_capacity":50,"has_boiler":False,"has_chemical_substance":True,
    "has_high_pressure_gas":None,"gas_capacity_kg":0,"elevator_count":2,"annual_energy_toe":10,
    "work_height_m":3.5,"has_truck_loading_unloading":False,"truck_loading_height_m":2.0,
    "has_manual_heavy_handling":True,"manual_handling_weight_kg":25,
    "material_profile":[{"material_category":"FL","handling_modes":["USE"]}],
    "business_activity_types":["리모델링 수행"],"building_qualifications":None,
    "regulated_facility_types":None,"hazardous_work_environments":["고열작업(실내)"],
    "process_list":[{"process_name":"용접","hazard_codes":["FIRE"],"worker_count":2,"is_primary":True,"activity_type":["WELD"]}],
    "equipment_list":[{"equipment_type":"PRESS","asset_name":"프레스","quantity":1,"capacity_value":10,"capacity_unit":"t","is_legal_target":True,"usage_type":["U"],"relation_type":["R"]}],
}

def test_H8_01_projection():
    fac=H.build_industrial_leg_facility(_contract(FULL_VALUES))
    assert isinstance(fac, dict) and "worker_count" in fac
def test_H8_02_exact_name_only():
    fac=H.build_industrial_leg_facility(_contract(FULL_VALUES))
    allowed=set(_LEG_INPUT_FIELDS)
    assert set(fac.keys()) <= allowed
    for k in ["address","floor_count","basement_count","built_year","main_structure","electric_capacity",
              "elevator_count","annual_energy_toe","material_profile","business_activity_types",
              "building_qualifications","regulated_facility_types","hazardous_work_environments",
              "process_list","equipment_list"]:
        assert k not in fac
def test_H8_03_none_excluded():
    fac=H.build_industrial_leg_facility(_contract(FULL_VALUES))
    assert "has_high_pressure_gas" not in fac
def test_H8_04_false_preserved():
    fac=H.build_industrial_leg_facility(_contract(FULL_VALUES))
    assert fac["has_boiler"] is False and fac["has_truck_loading_unloading"] is False
def test_H8_05_zero_preserved():
    fac=H.build_industrial_leg_facility(_contract(FULL_VALUES))
    assert fac["worker_count"]==0 and fac["gas_capacity_kg"]==0
def test_H8_06_07_value_unchanged():
    fac=H.build_industrial_leg_facility(_contract(FULL_VALUES))
    assert fac["worker_count"]==0 and fac["total_floor_area"]==123.4
    assert fac["work_height_m"]==3.5 and fac["manual_handling_weight_kg"]==25
def test_H8_chem_alias_reuse():
    fac=H.build_industrial_leg_facility(_contract(FULL_VALUES))
    assert fac.get("has_chemical") is True
    assert "has_chemical_substance" not in fac
def test_H8_08_09_10_no_structural_derive():
    fac=H.build_industrial_leg_facility(_contract(FULL_VALUES))
    for k in ["has_welding","has_press","has_casting","has_plating","has_conveyor","has_hazardous_material","has_gas"]:
        assert k not in fac
def test_H8_11_unresolved_not_gated():
    c=_contract({"worker_count":5}, unresolved=["main_structure","regulated_facility_types"])
    fac=H.build_industrial_leg_facility(c)
    assert fac=={"worker_count":5}
def test_H8_12_13_no_db(monkeypatch):
    src=open("services/safe_industrial_leg_handoff.py").read()
    assert "supabase" not in src and "get_supabase" not in src
def test_H8_14_15_16_evaluate_called_once_payload_passthrough(monkeypatch):
    calls=[]
    def fake_eval(facility, *, timeout=None):
        calls.append(facility)
        return {"status":"OK","obligations":[{"x":1}],"raw":"LEG"}
    monkeypatch.setattr(H.leg_runtime_client,"evaluate_rtm",fake_eval)
    resp=H.send_industrial_canonical_to_leg(_contract(FULL_VALUES))
    assert len(calls)==1
    fac=H.build_industrial_leg_facility(_contract(FULL_VALUES))
    assert calls[0]==fac
    assert resp=={"status":"OK","obligations":[{"x":1}],"raw":"LEG"}
def test_H8_17_no_result_processing(monkeypatch):
    monkeypatch.setattr(H.leg_runtime_client,"evaluate_rtm",lambda f,*,timeout=None:{"weird":"shape","no_status":True})
    resp=H.send_industrial_canonical_to_leg(_contract({"worker_count":1}))
    assert resp=={"weird":"shape","no_status":True}
