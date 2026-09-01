"""STEP5 — equipment_assets canonical extension (usage_types/relation_types + sparse PATCH + ownership)."""
import copy, asyncio
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import routers.equipment_assets as eq
from routers.equipment_assets import EquipmentAssetCreate, EquipmentAssetUpdate, EQUIPMENT_CANONICAL_NULL_CLEAR_FIELDS

def _run(c): return asyncio.get_event_loop().run_until_complete(c)

class _Res:
    def __init__(s,d,count=None): s.data=d; s.count=count
class _Q:
    def __init__(s,store,c): s.store=store; s.c=c; s._f={}; s._upd=None; s._ins=None; s._lim=None
    def select(s,*a,**k): return s
    def eq(s,col,val): s._f[col]=val; return s
    def in_(s,col,vals): s._f[col]=("in",set(vals)); return s
    def order(s,*a,**k): return s
    def range(s,*a,**k): return s
    def limit(s,n): s._lim=n; return s
    def update(s,d): s._upd=d; s.c["writes"]+=1; return s
    def insert(s,d): s._ins=d; s.c["writes"]+=1; return s
    def execute(s):
        s.c["reads"]+=1
        rows=[r for r in s.store if all((r.get(k) in v[1]) if isinstance(v,tuple) else r.get(k)==v for k,v in s._f.items())]
        if s._upd is not None:
            for r in rows: r.update(s._upd)
            return _Res(copy.deepcopy(rows))
        if s._ins is not None:
            ins=s._ins if isinstance(s._ins,list) else [s._ins]
            for d in ins:
                d=dict(d); d.setdefault("id","NEW"); s.store.append(d)
            return _Res(copy.deepcopy(ins))
        return _Res(copy.deepcopy(rows), count=len(rows))
class _T:
    def __init__(s,name,store,c): s.name=name; s.store=store; s.c=c
    def select(s,*a,**k): return _Q(s.store,s.c)
    def update(s,d): return _Q(s.store,s.c).update(d)
    def insert(s,d): return _Q(s.store,s.c).insert(d)
    def eq(s,*a,**k): return _Q(s.store,s.c).eq(*a,**k)
class FakeSB:
    def __init__(s, assets=None, facs=None):
        s.stores={"equipment_assets":assets if assets is not None else [],
                  "factories":facs if facs is not None else [{"id":"F1","company_id":"C1"}]}
        s.counters={"reads":0,"writes":0}
    def table(s,n): s.stores.setdefault(n,[]); return _T(n,s.stores[n],s.counters)

class _Cur(dict): pass
def _env(monkeypatch, own_ok=True, assets=None):
    sb=FakeSB(assets=assets)
    monkeypatch.setattr(eq,"get_supabase",lambda: sb)
    def fown(s,fid,cur):
        if not own_ok: raise HTTPException(status_code=404, detail="foreign")
    monkeypatch.setattr(eq,"_ensure_factory_own",fown)
    return sb

# models
def test_arrays_strict():
    assert EquipmentAssetCreate(factory_id="F1",asset_name="a",usage_types=[]).usage_types==[]
    assert EquipmentAssetCreate(factory_id="F1",asset_name="a",usage_types=["U"]).usage_types==["U"]
    for bad in [[1],[True],[{"a":1}],[["x"]],[""],["  "]]:
        with pytest.raises(ValidationError): EquipmentAssetUpdate(relation_types=bad)
def test_nullclear_set():
    assert EQUIPMENT_CANONICAL_NULL_CLEAR_FIELDS=={"usage_types","relation_types"}

# GET list select includes them (static)
def test_get_list_select_has_fields():
    src=open("routers/equipment_assets.py").read()
    assert "created_at, usage_types, relation_types" in src

# CREATE wiring
def test_create_wires_and_empty_preserved(monkeypatch):
    sb=_env(monkeypatch, assets=[])
    _run(eq.create_asset(EquipmentAssetCreate(factory_id="F1",asset_name="펌프",usage_types=["STORAGE"],relation_types=[]), _Cur(role_code="010")))
    row=sb.stores["equipment_assets"][0]
    assert row["usage_types"]==["STORAGE"] and row["relation_types"]==[]
def test_create_omitted_absent(monkeypatch):
    sb=_env(monkeypatch, assets=[])
    _run(eq.create_asset(EquipmentAssetCreate(factory_id="F1",asset_name="펌프"), _Cur(role_code="010")))
    row=sb.stores["equipment_assets"][0]
    assert "usage_types" not in row and "relation_types" not in row  # omitted None → dropped

# PATCH sparse
def test_patch_null_clear(monkeypatch):
    sb=_env(monkeypatch, assets=[{"id":"A1","factory_id":"F1","usage_types":["U"],"relation_types":["R"]}])
    eq.update_asset("A1", EquipmentAssetUpdate(**{"usage_types":None}), _Cur(role_code="010"))
    assert sb.stores["equipment_assets"][0]["usage_types"] is None
def test_patch_empty_preserved(monkeypatch):
    sb=_env(monkeypatch, assets=[{"id":"A1","factory_id":"F1"}])
    eq.update_asset("A1", EquipmentAssetUpdate(relation_types=[]), _Cur(role_code="010"))
    assert sb.stores["equipment_assets"][0]["relation_types"]==[]
def test_patch_omitted_preserved(monkeypatch):
    sb=_env(monkeypatch, assets=[{"id":"A1","factory_id":"F1","usage_types":["U"]}])
    eq.update_asset("A1", EquipmentAssetUpdate(relation_types=["R"]), _Cur(role_code="010"))
    row=sb.stores["equipment_assets"][0]
    assert row["relation_types"]==["R"] and row["usage_types"]==["U"]

# ownership (via _ensure_asset_own → _ensure_factory_own)
def test_patch_foreign_404_no_write(monkeypatch):
    sb=_env(monkeypatch, own_ok=False, assets=[{"id":"A1","factory_id":"F1"}])
    with pytest.raises(HTTPException) as e:
        eq.update_asset("A1", EquipmentAssetUpdate(usage_types=["U"]), _Cur())
    assert e.value.status_code==404 and sb.counters["writes"]==0
def test_patch_missing_404(monkeypatch):
    sb=_env(monkeypatch, assets=[])
    with pytest.raises(HTTPException) as e:
        eq.update_asset("AX", EquipmentAssetUpdate(usage_types=["U"]), _Cur())
    assert e.value.status_code==404 and sb.counters["writes"]==0
def test_get_single_foreign_404(monkeypatch):
    sb=_env(monkeypatch, own_ok=False, assets=[{"id":"A1","factory_id":"F1"}])
    with pytest.raises(HTTPException) as e:
        eq.get_asset("A1", _Cur())
    assert e.value.status_code==404

# static: legal absent, factory_process_id no new writer
def test_no_legal_and_fpid():
    src=open("routers/equipment_assets.py").read()
    assert "legal_usage" not in src and "legal_relation" not in src
    assert "legal-diagnosis" not in src and "legal-equipment" not in src
    # factory_process_id: no write (no update/insert assignment). only reads(select/get).
    assert '"factory_process_id":' not in src   # not written in any insert/update dict
