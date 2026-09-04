"""WO-BLD-FINALIZATION — SAFE BUILDING leg runtime 검증."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import services.safe_building_leg_runtime as bld_rt
from services.safe_building_leg_runtime import run_safe_building_leg
from schemas.legal_engine import SafeBuildingConsumerInput, SafeBuildingLegBody

class _Res:
    def __init__(s, d): s.data = d
class _Q:
    def __init__(s, rows): s._rows = rows
    def select(s,*a,**k): return s
    def eq(s,*a,**k): return s
    def limit(s,*a,**k): return s
    def execute(s): return _Res(s._rows)
class _FakeSB:
    def __init__(s, fac): s._fac = fac; s.writes = 0
    def table(s,n): return _Q([s._fac] if (n=="factories" and s._fac) else [])

def _patch(monkeypatch, cap):
    def fake(step1):
        cap["step1"]=step1
        return {"engine_family":"LEG","sector":"BUILDING","obligations":[]}
    monkeypatch.setattr(bld_rt, "run_leg_diagnosis", fake)

def test_owned_exact_read(monkeypatch):
    cap={}; _patch(monkeypatch,cap)
    out=run_safe_building_leg(_FakeSB({"floor_count":12,"has_boiler":True,"is_multi_use":False}),"F1",SafeBuildingConsumerInput())
    inp=cap["step1"].input
    assert inp["floor_count"]==12 and inp["has_boiler"] is True and inp["is_multi_use"] is False
    assert cap["step1"].sector=="BUILDING" and cap["step1"].factory_id=="F1"

def test_override_runtime(monkeypatch):
    cap={}; _patch(monkeypatch,cap)
    ci=SafeBuildingConsumerInput(building_use_type="오피스텔",building_height_m=250.0,has_high_pressure_gas=True,has_flat_plate_structure=True,is_collapse_risk_land=False)
    run_safe_building_leg(_FakeSB({"floor_count":5}),"F1",ci)
    inp=cap["step1"].input
    assert inp["building_use_type"]=="오피스텔" and inp["building_height_m"]==250.0
    assert inp["has_high_pressure_gas"] is True and inp["has_flat_plate_structure"] is True and inp["is_collapse_risk_land"] is False

def test_none_not_override(monkeypatch):
    cap={}; _patch(monkeypatch,cap)
    run_safe_building_leg(_FakeSB({"floor_count":5}),"F1",SafeBuildingConsumerInput(building_use_type=None))
    assert "building_use_type" not in cap["step1"].input

def test_owned_absent_unresolved(monkeypatch):
    cap={}; _patch(monkeypatch,cap)
    out=run_safe_building_leg(_FakeSB({"floor_count":5}),"F1",SafeBuildingConsumerInput())
    assert "has_boiler" in out["unresolved_fields"] and "is_multi_use" in out["unresolved_fields"]

def test_leg_once_no_write(monkeypatch):
    cap={"n":0}
    def fake(step1): cap["n"]+=1; cap["step1"]=step1; return {"engine_family":"LEG"}
    monkeypatch.setattr(bld_rt,"run_leg_diagnosis",fake)
    sb=_FakeSB({"floor_count":5}); run_safe_building_leg(sb,"F1",SafeBuildingConsumerInput())
    assert cap["n"]==1 and sb.writes==0

def test_floor_count_not_overridable():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SafeBuildingLegBody(factory_id="F1", input={"floor_count":5})
