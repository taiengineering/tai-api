"""STEP3B-IMPL — canonical vocabulary validation (system_codes) + write exposure + null-clear 9."""
import copy
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import routers.factories as fac_router
from routers.factories import FactoryCreate, FactoryUpdate, CANONICAL_NULL_CLEAR_FIELDS, _build_factory_update
from services.factory_canonical_vocab_svc import (
    FIELD_TO_CATEGORY, load_active_codes, validate_factory_canonical_codes,
)

CODES = {
    "factory_business_activity": {"REMODEL_OPERATION","EMISSION_FACILITY_OPERATION"},
    "factory_hazardous_environment": {"INDOOR_HIGH_HEAT","FIRE_EXPLOSION_HAZARD_AREA"},
    "factory_building_composition": {"ROWHOUSE_MULTIFAMILY_COEXISTENCE","BASEMENT_COMMUNITY_FACILITY_USE"},
    "factory_regulatory_designation": {"SOIL_CONTAMINATION_MANAGEMENT_DESIGNATION"},
}

class _Res:
    def __init__(s,d): s.data=d
class _Q:
    def __init__(s,store,counters): s.store=store; s.c=counters; s._f={}; s._in=None
    def select(s,*a,**k): return s
    def in_(s,col,vals): s._in=(col,set(vals)); return s
    def eq(s,col,val): s._f[col]=val; return s
    def limit(s,n): return s
    def single(s): return s
    def execute(s):
        s.c["reads"]+=1
        rows=s.store
        if s._in:
            col,vals=s._in; rows=[r for r in rows if r.get(col) in vals]
        rows=[r for r in rows if all(r.get(k)==v for k,v in s._f.items())]
        return _Res(copy.deepcopy(rows))
class _T:
    def __init__(s,name,store,counters): s.name=name; s.store=store; s.c=counters
    def select(s,*a,**k): return _Q(s.store,s.c)
    def insert(s,d): s.c["writes"]+=1; s._d=d; return s
    def update(s,d): s.c["writes"]+=1; s._d=d; return s
    def eq(s,*a,**k): return s
    def execute(s): return _Res([getattr(s,"_d",{})])
class FakeSB:
    def __init__(s):
        sc=[{"category":c,"code":code,"is_active":True} for c,codes in CODES.items() for code in codes]
        s.stores={"system_codes":sc,"companies":[{"id":"C1"}],"factories":[{"id":"F1","status_code":"ACTIVE"}]}
        s.counters={"reads":0,"writes":0}
    def table(s,n): s.stores.setdefault(n,[]); return _T(n,s.stores[n],s.counters)

# ---- vocab service ----
def test_field_map(): assert set(FIELD_TO_CATEGORY)=={"business_activity_types","hazardous_work_environments","building_composition_codes","regulatory_designation_codes"}
def test_load():
    c=load_active_codes(FakeSB()); assert "REMODEL_OPERATION" in c["factory_business_activity"]
def test_valid_ok():
    validate_factory_canonical_codes({"business_activity_types":["REMODEL_OPERATION"]}, FakeSB())
def test_invalid_422():
    with pytest.raises(HTTPException) as e:
        validate_factory_canonical_codes({"business_activity_types":["NOPE"]}, FakeSB())
    assert e.value.status_code==422
def test_null_skips_read():
    sb=FakeSB(); validate_factory_canonical_codes({"business_activity_types":None}, sb); assert sb.counters["reads"]==0
def test_empty_passes():
    sb=FakeSB(); validate_factory_canonical_codes({"business_activity_types":[]}, sb)
def test_no_target_no_read():
    sb=FakeSB(); validate_factory_canonical_codes({"name":"x"}, sb); assert sb.counters["reads"]==0
def test_marketing_not_queried():
    sb=FakeSB(); validate_factory_canonical_codes({"hazardous_work_environments":["INDOOR_HIGH_HEAT"]}, sb)
    assert "diagnosis_input_fields" not in sb.stores or sb.stores.get("diagnosis_input_fields")==[]

# ---- model write exposure + null-clear 9 ----
def test_write_fields_exposed():
    for f in ["building_composition_codes","regulatory_designation_codes"]:
        assert f in FactoryCreate.model_fields and f in FactoryUpdate.model_fields
def test_nullclear_9():
    assert CANONICAL_NULL_CLEAR_FIELDS=={
        "work_height_m","has_truck_loading_unloading","truck_loading_height_m",
        "has_manual_heavy_handling","manual_handling_weight_kg",
        "business_activity_types","hazardous_work_environments",
        "building_composition_codes","regulatory_designation_codes"}
def test_patch_explicit_null_clears_new():
    for f in ["building_composition_codes","regulatory_designation_codes"]:
        upd=_build_factory_update(FactoryUpdate(**{f:None}).dict(exclude_unset=True))
        assert upd=={f:None}
def test_patch_omitted_preserves_new():
    upd=_build_factory_update(FactoryUpdate(building_composition_codes=["ROWHOUSE_MULTIFAMILY_COEXISTENCE"]).dict(exclude_unset=True))
    assert upd=={"building_composition_codes":["ROWHOUSE_MULTIFAMILY_COEXISTENCE"]}
def test_new_fields_strict_shape():
    with pytest.raises(ValidationError): FactoryUpdate(building_composition_codes=[1])
    with pytest.raises(ValidationError): FactoryUpdate(regulatory_designation_codes=[""])
    assert FactoryUpdate(regulatory_designation_codes=[]).regulatory_designation_codes==[]

# ---- real route execution: security + validation order ----
class _Cur(dict): pass
def _patch_env(monkeypatch, own_ok=True, exists=True):
    sb=FakeSB()
    if not exists: sb.stores["factories"]=[]
    monkeypatch.setattr(fac_router,"get_supabase",lambda: sb)
    def own(s,fid,cur):
        if not own_ok: raise HTTPException(status_code=404, detail="foreign")
    monkeypatch.setattr(fac_router,"_ensure_factory_own",own)
    return sb

import asyncio
def _run(coro): return asyncio.get_event_loop().run_until_complete(coro)

def test_V3B_patch_valid(monkeypatch):
    sb=_patch_env(monkeypatch)
    r=_run(fac_router.update_factory("F1", FactoryUpdate(business_activity_types=["REMODEL_OPERATION"]), _Cur(role_code="010")))
    assert r["status"]=="success"
def test_V3B_patch_invalid_422(monkeypatch):
    _patch_env(monkeypatch)
    with pytest.raises(HTTPException) as e:
        _run(fac_router.update_factory("F1", FactoryUpdate(business_activity_types=["NOPE"]), _Cur(role_code="010")))
    assert e.value.status_code==422
def test_V3B_foreign_404_no_vocab_no_write(monkeypatch):
    sb=_patch_env(monkeypatch, own_ok=False)
    with pytest.raises(HTTPException) as e:
        _run(fac_router.update_factory("F1", FactoryUpdate(business_activity_types=["NOPE"]), _Cur(role_code="010")))
    assert e.value.status_code==404
    assert sb.counters["reads"]==0 and sb.counters["writes"]==0
def test_V3B_missing_404(monkeypatch):
    sb=_patch_env(monkeypatch, exists=False)
    with pytest.raises(HTTPException) as e:
        _run(fac_router.update_factory("F404", FactoryUpdate(work_height_m=1.0), _Cur(role_code="010")))
    assert e.value.status_code==404
    assert sb.counters["writes"]==0
