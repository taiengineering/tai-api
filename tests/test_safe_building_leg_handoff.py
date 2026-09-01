"""WO-SAFE-LEGAL-BLD-CANONICAL-IMPLEMENT-001 STEP5 — BUILDING canonical 36 → LEG handoff 검증.

실제 clients.leg_runtime_client.build_facility(기존 BUILDING elevator sector gate 포함)를 사용하고
evaluate_rtm 만 monkeypatch 한다. 자체 fake build_facility 로 통과시키지 않는다.
"""
import inspect
import pytest

from clients import leg_runtime_client
import services.safe_building_leg_handoff as H

E5 = ["building_use_type","main_structure","is_multi_use","is_energy_intensive","building_grade"]


def _contract(values, unresolved=None):
    return {
        "contract_version": "MKT_BLD_PAID_CONTRACT_V1",
        "sector": "BUILDING",
        "factory_id": "fac-1",
        "values": dict(values),
        "unresolved_fields": list(unresolved or []),
        "provenance": {},
    }


class _Spy:
    def __init__(self, ret): self.calls=[]; self.ret=ret
    def __call__(self, facility, **kw): self.calls.append(facility); return self.ret

def _patch_eval(monkeypatch, ret=None):
    spy=_Spy(ret if ret is not None else {"status":"OK","obligations":[]})
    monkeypatch.setattr(leg_runtime_client, "evaluate_rtm", spy)
    return spy


# H-BLD-01/02
def test_HBLD_01_values_only():
    fac=H.build_building_leg_facility(_contract({"worker_count":10}))
    assert fac.get("worker_count")==10
def test_HBLD_02_sector_building():
    assert H.SECTOR=="BUILDING"
    assert H._CanonicalStep1Adapter({}).sector=="BUILDING"

# H-BLD-03 uses existing build_facility
def test_HBLD_03_uses_existing_build_facility():
    vals={"worker_count":10,"has_gas":True}
    fac=H.build_building_leg_facility(_contract(vals))
    expected=leg_runtime_client.build_facility(H._CanonicalStep1Adapter(vals))
    assert fac==expected
    assert "leg_runtime_client" in inspect.getsource(H)

# H-BLD-04/05/06/07 no new allowlist/alias/default/sector logic
def test_HBLD_04_07_no_new_tables():
    src=inspect.getsource(H)
    assert "_LEG_INPUT_FIELDS = " not in src
    assert "_LEG_CODE_TO_CONSUMER = " not in src
    assert "_FIELD_MAP = " not in src
    # STEP5 자체 elevator/sector 파생 로직 없음 (docstring/comment 언급 허용; tokenize 로 문자열·주석 제거 후 실행부만 검사)
    import io as _io, tokenize as _tok
    _code_toks=[]
    for _t in _tok.generate_tokens(_io.StringIO(src).readline):
        if _t.type in (_tok.STRING, _tok.COMMENT):
            continue
        _code_toks.append(_t.string)
    code_only=" ".join(_code_toks)
    assert "elevator_count" not in code_only
    assert "has_building_elevator" not in code_only

# H-BLD-08/09 전달
def test_HBLD_08_worker_count():
    fac=H.build_building_leg_facility(_contract({"worker_count":25}))
    assert fac["worker_count"]==25
def test_HBLD_09_total_floor_area():
    fac=H.build_building_leg_facility(_contract({"total_floor_area":1500}))
    assert fac["total_floor_area"]==1500

# H-BLD-10/11/12
def test_HBLD_10_has_gas_false():
    fac=H.build_building_leg_facility(_contract({"has_gas":False}))
    assert fac["has_gas"] is False
def test_HBLD_11_has_chemical_true():
    fac=H.build_building_leg_facility(_contract({"has_chemical":True}))
    assert fac["has_chemical"] is True
def test_HBLD_12_no_chemical_substance_key():
    # BUILDING 은 CONSTRUCTION chemical rename 미적용 → has_chemical 유지, has_chemical_substance 미생성
    fac=H.build_building_leg_facility(_contract({"has_chemical":True}))
    assert "has_chemical_substance" not in fac

# H-BLD-13/14/15 false/0 보존
def test_HBLD_13_work_height_zero():
    fac=H.build_building_leg_facility(_contract({"work_height_m":0}))
    assert fac["work_height_m"]==0
def test_HBLD_14_sprinkler_false():
    fac=H.build_building_leg_facility(_contract({"has_sprinkler":False}))
    assert fac["has_sprinkler"] is False
def test_HBLD_15_gas_capacity_zero():
    fac=H.build_building_leg_facility(_contract({"gas_capacity_kg":0}))
    assert fac["gas_capacity_kg"]==0

# H-BLD-16 None 미전달
def test_HBLD_16_none_omitted():
    fac=H.build_building_leg_facility(_contract({"worker_count":None,"has_gas":None}))
    assert "worker_count" not in fac and "has_gas" not in fac

# H-BLD-17~20 BUILDING elevator existing gate (real build_facility)
def test_HBLD_17_elevator_gt0():
    fac=H.build_building_leg_facility(_contract({"elevator_count":1}))
    assert fac.get("has_building_elevator") is True
def test_HBLD_18_elevator_zero():
    fac=H.build_building_leg_facility(_contract({"elevator_count":0}))
    assert "has_building_elevator" not in fac
def test_HBLD_19_elevator_none():
    fac=H.build_building_leg_facility(_contract({"elevator_count":None}))
    assert "has_building_elevator" not in fac
def test_HBLD_20_no_has_elevator_leak():
    # elevator_count 로 has_elevator(산업 리프트) 를 만들지 않음
    fac=H.build_building_leg_facility(_contract({"elevator_count":3}))
    assert "has_elevator" not in fac
    assert fac.get("has_building_elevator") is True

# H-BLD-21~26 E5 / non-LEG no-derivation
def test_HBLD_21_e5_none_absent():
    vals={f:None for f in E5}; vals["worker_count"]=5
    fac=H.build_building_leg_facility(_contract(vals))
    for f in E5: assert f not in fac
def test_HBLD_22_multi_use_no_derivation():
    fac=H.build_building_leg_facility(_contract({"multi_use_type":["노래방"]}))
    assert "is_multi_use" not in fac
def test_HBLD_23_energy_no_derivation():
    fac=H.build_building_leg_facility(_contract({"annual_energy_toe":99999}))
    assert "is_energy_intensive" not in fac
def test_HBLD_24_water_tank_no_derivation():
    fac=H.build_building_leg_facility(_contract({"water_tank_ton":50}))
    assert "has_water_tank" not in fac  # water_tank_ton 은 _LEG_INPUT_FIELDS 아님, has_water_tank 미제공
def test_HBLD_25_gas_capacity_no_has_gas():
    fac=H.build_building_leg_facility(_contract({"gas_capacity_m3":100}))
    assert "has_gas" not in fac
def test_HBLD_26_smoke_control_no_forced_key():
    # has_smoke_control 은 _LEG_INPUT_FIELDS 아님 → facility 미포함(억지 추가 0)
    fac=H.build_building_leg_facility(_contract({"has_smoke_control":True}))
    assert "has_smoke_control" not in fac

# H-BLD-27/28/29 call/response
def test_HBLD_27_evaluate_once(monkeypatch):
    spy=_patch_eval(monkeypatch)
    H.send_building_canonical_to_leg(_contract({"worker_count":5}))
    assert len(spy.calls)==1
def test_HBLD_28_payload_exact(monkeypatch):
    spy=_patch_eval(monkeypatch)
    c=_contract({"worker_count":5,"has_gas":False,"elevator_count":2})
    expected=H.build_building_leg_facility(c)
    H.send_building_canonical_to_leg(c)
    assert spy.calls[0]==expected
    assert expected.get("has_building_elevator") is True  # gate 반영 확인
def test_HBLD_29_raw_passthrough(monkeypatch):
    sentinel={"status":"OK","obligations":[{"id":"x"}],"trace_id":"t1"}
    spy=_patch_eval(monkeypatch, ret=sentinel)
    out=H.send_building_canonical_to_leg(_contract({"worker_count":5}))
    assert out is sentinel

# H-BLD-30/31/32 DB / policy
def test_HBLD_30_31_no_db():
    src=inspect.getsource(H)
    assert "supabase" not in src.lower()
    assert "get_supabase" not in src
    assert "assemble_building_marketing_contract" not in src
def test_HBLD_32_unresolved_no_gating(monkeypatch):
    spy=_patch_eval(monkeypatch)
    c=_contract({"worker_count":5}, unresolved=["building_use_type","main_structure","is_multi_use","is_energy_intensive","building_grade"])
    H.send_building_canonical_to_leg(c)
    assert len(spy.calls)==1
