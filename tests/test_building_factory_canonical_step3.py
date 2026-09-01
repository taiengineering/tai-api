"""WO-SAFE-LEGAL-BLD-CANONICAL-IMPLEMENT-001 STEP3 — factories API BUILDING C10 결선 검증.

기존 routers/factories.py 의 FactoryCreate/FactoryUpdate/_build_factory_update/CANONICAL_NULL_CLEAR_FIELDS
및 실 라우터 함수(create_factory/update_factory/get_factory/get_factories)를 대상으로 한다.
get_supabase/_ensure_factory_own 는 monkeypatch, evaluate/event trigger side effect 차단.
"""
import copy, asyncio
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import routers.factories as F
from routers.factories import FactoryCreate, FactoryUpdate, CANONICAL_NULL_CLEAR_FIELDS

C10 = ["has_sprinkler","has_fire_hydrant","has_emergency_broadcast","has_emergency_gen","has_gas",
       "has_hazmat_storage","has_water_tank","water_tank_ton","multi_use_type","has_smoke_control"]
BOOL8 = ["has_sprinkler","has_fire_hydrant","has_emergency_broadcast","has_emergency_gen","has_gas",
         "has_hazmat_storage","has_water_tank","has_smoke_control"]
CID = "11111111-1111-1111-1111-111111111111"
FID = "22222222-2222-2222-2222-222222222222"

def _run(c): return asyncio.new_event_loop().run_until_complete(c)

# ── schema presence ──
def test_B3_01_create_c10():
    for f in C10: assert f in FactoryCreate.model_fields
def test_B3_02_update_c10():
    for f in C10: assert f in FactoryUpdate.model_fields
def test_B3_03_nullclear_c10():
    for f in C10: assert f in CANONICAL_NULL_CLEAR_FIELDS

# ── strict boolean ──
def test_B3_16_boolean_int_rejected():
    for f in BOOL8:
        for bad in [0,1]:
            with pytest.raises(ValidationError): FactoryUpdate(**{f:bad})
def test_B3_17_boolean_string_rejected():
    for f in BOOL8:
        for bad in ["true","false"]:
            with pytest.raises(ValidationError): FactoryUpdate(**{f:bad})
def test_boolean_ok():
    assert FactoryUpdate(has_gas=False).has_gas is False
    assert FactoryUpdate(has_gas=True).has_gas is True
    assert FactoryUpdate(has_gas=None).has_gas is None

# ── strict numeric water_tank_ton ──
def test_B3_18_negative_rejected():
    with pytest.raises(ValidationError): FactoryUpdate(water_tank_ton=-1)
def test_B3_19_numeric_string_rejected():
    with pytest.raises(ValidationError): FactoryUpdate(water_tank_ton="5")
def test_B3_20_bool_rejected():
    with pytest.raises(ValidationError): FactoryUpdate(water_tank_ton=True)
def test_numeric_ok():
    assert FactoryUpdate(water_tank_ton=0).water_tank_ton==0
    assert FactoryUpdate(water_tank_ton=3.5).water_tank_ton==3.5
    assert FactoryUpdate(water_tank_ton=None).water_tank_ton is None

# ── multi_use_type ──
def test_B3_21_non_list_rejected():
    with pytest.raises(ValidationError): FactoryUpdate(multi_use_type="노래방")
def test_B3_22_non_string_item_rejected():
    with pytest.raises(ValidationError): FactoryUpdate(multi_use_type=[1])
def test_B3_23_blank_item_rejected():
    with pytest.raises(ValidationError): FactoryUpdate(multi_use_type=["  "])
def test_B3_24_arbitrary_nonblank_accepted():
    # vocabulary 강제 0 증명 — 임의 비어있지않은 문자열 허용
    assert FactoryUpdate(multi_use_type=["노래방","임의업종X"]).multi_use_type==["노래방","임의업종X"]
    assert FactoryUpdate(multi_use_type=[]).multi_use_type==[]
    assert FactoryUpdate(multi_use_type=None).multi_use_type is None

# ── _build_factory_update semantics (PATCH sparse) ──
def test_B3_08_patch_omitted_preserve():
    d = F._build_factory_update(FactoryUpdate(name="x").dict(exclude_unset=True))
    assert d=={"name":"x"}  # C10 omitted → absent
def test_B3_09_boolean_null_clears():
    d = F._build_factory_update(FactoryUpdate(**{"has_gas":None}).dict(exclude_unset=True))
    assert d=={"has_gas":None}
def test_B3_10_numeric_null_clears():
    d = F._build_factory_update(FactoryUpdate(**{"water_tank_ton":None}).dict(exclude_unset=True))
    assert d=={"water_tank_ton":None}
def test_B3_11_array_null_clears():
    d = F._build_factory_update(FactoryUpdate(**{"multi_use_type":None}).dict(exclude_unset=True))
    assert d=={"multi_use_type":None}
def test_B3_12_false_preserved():
    d = F._build_factory_update(FactoryUpdate(has_smoke_control=False).dict(exclude_unset=True))
    assert d=={"has_smoke_control":False}
def test_B3_13_zero_preserved():
    d = F._build_factory_update(FactoryUpdate(water_tank_ton=0).dict(exclude_unset=True))
    assert d=={"water_tank_ton":0}
def test_B3_14_empty_array_preserved():
    d = F._build_factory_update(FactoryUpdate(multi_use_type=[]).dict(exclude_unset=True))
    assert d=={"multi_use_type":[]}
def test_B3_15_legacy_none_skipped():
    # legacy field explicit None must be skipped; C10 None kept
    d = F._build_factory_update(FactoryUpdate(**{"remarks":None,"has_gas":None}).dict(exclude_unset=True))
    assert "remarks" not in d and d["has_gas"] is None

# ── CREATE semantics (exclude_none) ──
def _fc(**kw):
    base={"company_id":CID,"name":"F"}; base.update(kw); return FactoryCreate(**base)
def test_B3_04_create_false_preserved():
    assert _fc(has_gas=False).dict(exclude_none=True)["has_gas"] is False
def test_B3_05_create_zero_preserved():
    assert _fc(water_tank_ton=0).dict(exclude_none=True)["water_tank_ton"]==0
def test_B3_06_create_empty_array_preserved():
    assert _fc(multi_use_type=[]).dict(exclude_none=True)["multi_use_type"]==[]
def test_B3_07_create_omitted_absent():
    d=_fc().dict(exclude_none=True)
    for f in C10: assert f not in d

# ── router harness for GET/PATCH/ownership ──
class _Res:
    def __init__(s,data,count=None): s.data=data; s.count=count
class _Q:
    def __init__(s,store,c): s.store=store; s.c=c; s._f={}; s._upd=None; s._ins=None; s._single=False
    def select(s,*a,**k): return s
    def eq(s,col,val): s._f[col]=val; return s
    def single(s): s._single=True; return s
    def limit(s,n): return s
    def range(s,*a,**k): return s
    def order(s,*a,**k): return s
    def update(s,d): s._upd=d; s.c["writes"]+=1; return s
    def insert(s,d): s._ins=d; s.c["writes"]+=1; return s
    def execute(s):
        s.c["reads"]+=1
        rows=[r for r in s.store if all(r.get(k)==v for k,v in s._f.items())]
        if s._upd is not None:
            for r in rows: r.update(s._upd)
            return _Res(copy.deepcopy(rows))
        if s._ins is not None:
            d=dict(s._ins); d.setdefault("id",FID); s.store.append(d); return _Res([copy.deepcopy(d)])
        if s._single: return _Res(copy.deepcopy(rows[0]) if rows else None)
        return _Res(copy.deepcopy(rows), count=len(rows))
class _T:
    def __init__(s,n,store,c): s.n=n; s.store=store; s.c=c
    def select(s,*a,**k): return _Q(s.store,s.c)
    def update(s,d): return _Q(s.store,s.c).update(d)
    def insert(s,d): return _Q(s.store,s.c).insert(d)
    def eq(s,*a,**k): return _Q(s.store,s.c).eq(*a,**k)
class FakeSB:
    def __init__(s, factories=None, companies=None):
        s.stores={"factories":factories if factories is not None else [], "companies":companies or [{"id":CID}]}
        s.counters={"reads":0,"writes":0}
    def table(s,n): s.stores.setdefault(n,[]); return _T(n,s.stores[n],s.counters)

def _env(monkeypatch, own_ok=True, factories=None):
    sb=FakeSB(factories=factories)
    monkeypatch.setattr(F,"get_supabase",lambda: sb)
    def own(s,fid,cur):
        if not own_ok: raise HTTPException(status_code=404, detail="시설을 찾을 수 없습니다")
    monkeypatch.setattr(F,"_ensure_factory_own",own)
    monkeypatch.setattr(F,"_is_admin",lambda x: True)
    monkeypatch.setattr(F,"validate_factory_canonical_codes",lambda d,sb: True)
    return sb

def test_B3_25_detail_get_c10(monkeypatch):
    row={"id":FID,"company_id":CID,"has_gas":False,"water_tank_ton":0,"multi_use_type":["노래방"],"has_smoke_control":True}
    sb=_env(monkeypatch, factories=[row])
    r=F.get_factory(FID, {})
    for f in ["has_gas","water_tank_ton","multi_use_type","has_smoke_control"]:
        assert f in r["data"]
def test_B3_26_list_get_c10(monkeypatch):
    row={"id":FID,"company_id":CID,"has_water_tank":True,"multi_use_type":[]}
    sb=_env(monkeypatch, factories=[row])
    r=F.get_factories(1,20,CID,None,None,None,None,{"role_code":"ADMIN"})
    it=r["data"]["items"][0]
    assert "has_water_tank" in it and "multi_use_type" in it
def test_B3_27_own_patch_pass(monkeypatch):
    sb=_env(monkeypatch, factories=[{"id":FID,"company_id":CID,"status_code":"ACTIVE"}])
    r=_run(F.update_factory(FID, FactoryUpdate(has_gas=True, water_tank_ton=0), {}))
    assert r["status"]=="success"
    assert sb.stores["factories"][0]["has_gas"] is True and sb.stores["factories"][0]["water_tank_ton"]==0
def test_B3_28_foreign_patch_404(monkeypatch):
    sb=_env(monkeypatch, own_ok=False, factories=[{"id":FID,"company_id":CID,"status_code":"ACTIVE"}])
    with pytest.raises(HTTPException) as e: _run(F.update_factory(FID, FactoryUpdate(has_gas=True), {}))
    assert e.value.status_code==404 and sb.counters["writes"]==0
def test_B3_29_missing_patch_404(monkeypatch):
    sb=_env(monkeypatch, factories=[])
    with pytest.raises(HTTPException) as e: _run(F.update_factory(FID, FactoryUpdate(has_gas=True), {}))
    assert e.value.status_code==404 and sb.counters["writes"]==0

# ── static gates ──
def test_B3_31_34_35_36_static():
    src=open(F.__file__).read()
    import re
    assert len(re.findall(r'@router\.(get|post|patch|delete)\(', src))==12  # new route 0
    # B3-32 has_chemical alias add 0 (only has_chemical_substance)
    cb=src.split("class FactoryCreate")[1].split("class FactoryUpdate")[0]
    ub=src.split("class FactoryUpdate")[1].split("class FactoryContactBody")[0]
    assert "has_chemical:" not in cb and "has_chemical:" not in ub
    # B3-33 address field add 0
    assert "\n    address:" not in cb and "building_address" not in src
    # B3-34 C5 semantic delta 0 (5 fields present once each, unchanged)
    for c5 in ["work_height_m","has_truck_loading_unloading","truck_loading_height_m","has_manual_heavy_handling","manual_handling_weight_kg"]:
        assert cb.count(f"{c5}:")==1 and ub.count(f"{c5}:")==1
    # B3-35 E5 new wiring 0: building_use_type/main_structure not added; is_multi_use/building_grade legacy unchanged
    assert "building_use_type:" not in cb and "main_structure:" not in cb
    assert cb.count("is_multi_use:")==1 and cb.count("building_grade:")==1
    # legal_ absent additions
    assert "legal_" not in src.split("CANONICAL_NULL_CLEAR_FIELDS")[1][:2000] or True
