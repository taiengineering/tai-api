"""STEP6 — factory_materials canonical asset CRUD."""
import copy, asyncio
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import routers.factory_materials as fm
from routers.factory_materials import (
    FactoryMaterialCreate, FactoryMaterialUpdate, MATERIAL_CANONICAL_NULL_CLEAR_FIELDS, router,
)

class _Res:
    def __init__(s,d): s.data=d
class _Q:
    def __init__(s,store,c): s.store=store; s.c=c; s._f={}; s._upd=None; s._ins=None
    def select(s,*a,**k): return s
    def eq(s,col,val): s._f[col]=val; return s
    def order(s,*a,**k): return s
    def limit(s,n): return s
    def update(s,d): s._upd=d; s.c["writes"]+=1; return s
    def insert(s,d): s._ins=d; s.c["writes"]+=1; return s
    def execute(s):
        s.c["reads"]+=1
        rows=[r for r in s.store if all(r.get(k)==v for k,v in s._f.items())]
        if s._upd is not None:
            for r in rows: r.update(s._upd)
            return _Res(copy.deepcopy(rows))
        if s._ins is not None:
            d=dict(s._ins); d.setdefault("id","NEW"); s.store.append(d)
            return _Res([copy.deepcopy(d)])
        return _Res(copy.deepcopy(rows))
class _T:
    def __init__(s,name,store,c): s.name=name; s.store=store; s.c=c
    def select(s,*a,**k): return _Q(s.store,s.c)
    def update(s,d): return _Q(s.store,s.c).update(d)
    def insert(s,d): return _Q(s.store,s.c).insert(d)
    def eq(s,*a,**k): return _Q(s.store,s.c).eq(*a,**k)
class FakeSB:
    def __init__(s, mats=None):
        s.stores={"factory_materials":mats if mats is not None else []}
        s.counters={"reads":0,"writes":0}
    def table(s,n): s.stores.setdefault(n,[]); return _T(n,s.stores[n],s.counters)

class _Cur(dict): pass
def _env(monkeypatch, own_ok=True, mats=None):
    sb=FakeSB(mats=mats)
    monkeypatch.setattr(fm,"get_supabase",lambda: sb)
    def own(s,fid,cur):
        if not own_ok: raise HTTPException(status_code=404, detail="foreign")
    monkeypatch.setattr(fm,"_ensure_factory_own",own)
    return sb

# ---- registry / prefix / contract ----
def test_registered_in_saas_core():
    import pathlib
    src=pathlib.Path("router_registry/saas_core.py").read_text()
    assert '"routers.factory_materials"' in src
def test_prefix():
    assert router.prefix=="/factory-materials"
def test_extra_forbid():
    for bad in ["id","is_active","created_at","updated_at","company_id"]:
        with pytest.raises(ValidationError): FactoryMaterialCreate(**{"factory_id":"F1","material_name":"x",bad:"y"})
    for bad in ["factory_id","id","is_active"]:
        with pytest.raises(ValidationError): FactoryMaterialUpdate(**{bad:"y"})
def test_nullclear_set():
    assert MATERIAL_CANONICAL_NULL_CLEAR_FIELDS=={"material_name","material_category_code","handling_mode_codes"}

# ---- strict ----
def test_strict_string():
    for bad in [123, True, ["x"], "", "  "]:
        with pytest.raises(ValidationError): FactoryMaterialCreate(factory_id="F1", material_name=bad)
def test_strict_array():
    assert FactoryMaterialCreate(factory_id="F1",material_name="x",handling_mode_codes=[]).handling_mode_codes==[]
    for bad in [[1],[True],[{"a":1}],[["x"]],[""],["  "]]:
        with pytest.raises(ValidationError): FactoryMaterialCreate(factory_id="F1",material_name="x",handling_mode_codes=bad)

# ---- create ----
def test_create_name_only(monkeypatch):
    sb=_env(monkeypatch, mats=[])
    r=fm.create_material(FactoryMaterialCreate(factory_id="F1",material_name="톨루엔"), _Cur())
    row=sb.stores["factory_materials"][0]
    assert row["material_name"]=="톨루엔" and row["is_active"] is True
def test_create_category_only(monkeypatch):
    sb=_env(monkeypatch, mats=[])
    fm.create_material(FactoryMaterialCreate(factory_id="F1",material_category_code="FLAMMABLE",handling_mode_codes=[]), _Cur())
    row=sb.stores["factory_materials"][0]
    assert row["material_category_code"]=="FLAMMABLE" and row["handling_mode_codes"]==[]
def test_create_identity_gate(monkeypatch):
    sb=_env(monkeypatch, mats=[])
    with pytest.raises(HTTPException) as e:
        fm.create_material(FactoryMaterialCreate(factory_id="F1"), _Cur())
    assert e.value.status_code==422 and sb.counters["writes"]==0
def test_create_foreign_404_no_write(monkeypatch):
    sb=_env(monkeypatch, own_ok=False, mats=[])
    with pytest.raises(HTTPException) as e:
        fm.create_material(FactoryMaterialCreate(factory_id="F1",material_name="x"), _Cur())
    assert e.value.status_code==404 and sb.counters["writes"]==0

# ---- list ----
def test_list_own(monkeypatch):
    sb=_env(monkeypatch, mats=[{"id":"M1","factory_id":"F1","material_name":"x","is_active":True}])
    r=fm.list_materials("F1", _Cur())
    assert r["data"]["total"]==1
def test_list_foreign_404_no_query(monkeypatch):
    sb=_env(monkeypatch, own_ok=False)
    with pytest.raises(HTTPException) as e: fm.list_materials("F1", _Cur())
    assert e.value.status_code==404 and sb.counters["reads"]==0

# ---- get single ----
def test_get_missing_404(monkeypatch):
    sb=_env(monkeypatch, mats=[])
    with pytest.raises(HTTPException) as e: fm.get_material("MX", _Cur())
    assert e.value.status_code==404
def test_get_inactive_404(monkeypatch):
    sb=_env(monkeypatch, mats=[{"id":"M1","factory_id":"F1","is_active":False,"material_name":"x"}])
    with pytest.raises(HTTPException) as e: fm.get_material("M1", _Cur())
    assert e.value.status_code==404
def test_get_foreign_404(monkeypatch):
    sb=_env(monkeypatch, own_ok=False, mats=[{"id":"M1","factory_id":"F1","is_active":True,"material_name":"x"}])
    with pytest.raises(HTTPException) as e: fm.get_material("M1", _Cur())
    assert e.value.status_code==404

# ---- patch ----
def test_patch_omitted_preserve(monkeypatch):
    sb=_env(monkeypatch, mats=[{"id":"M1","factory_id":"F1","is_active":True,"material_name":"톨루엔","material_category_code":"FL","handling_mode_codes":["USE"]}])
    fm.update_material("M1", FactoryMaterialUpdate(handling_mode_codes=["STORE"]), _Cur())
    row=sb.stores["factory_materials"][0]
    assert row["handling_mode_codes"]==["STORE"] and row["material_name"]=="톨루엔"
def test_patch_name_null_clear_ok(monkeypatch):
    sb=_env(monkeypatch, mats=[{"id":"M1","factory_id":"F1","is_active":True,"material_name":"톨루엔","material_category_code":"FL"}])
    fm.update_material("M1", FactoryMaterialUpdate(**{"material_name":None}), _Cur())
    assert sb.stores["factory_materials"][0]["material_name"] is None
def test_patch_handling_null_clear(monkeypatch):
    sb=_env(monkeypatch, mats=[{"id":"M1","factory_id":"F1","is_active":True,"material_name":"x","handling_mode_codes":["USE"]}])
    fm.update_material("M1", FactoryMaterialUpdate(**{"handling_mode_codes":None}), _Cur())
    assert sb.stores["factory_materials"][0]["handling_mode_codes"] is None
def test_patch_handling_empty_preserve(monkeypatch):
    sb=_env(monkeypatch, mats=[{"id":"M1","factory_id":"F1","is_active":True,"material_name":"x"}])
    fm.update_material("M1", FactoryMaterialUpdate(handling_mode_codes=[]), _Cur())
    assert sb.stores["factory_materials"][0]["handling_mode_codes"]==[]
def test_patch_postmerge_identity_422(monkeypatch):
    sb=_env(monkeypatch, mats=[{"id":"M1","factory_id":"F1","is_active":True,"material_name":"톨루엔","material_category_code":None}])
    with pytest.raises(HTTPException) as e:
        fm.update_material("M1", FactoryMaterialUpdate(**{"material_name":None}), _Cur())
    assert e.value.status_code==422
    assert sb.counters["writes"]==0
def test_patch_postmerge_identity_ok_when_category_present(monkeypatch):
    sb=_env(monkeypatch, mats=[{"id":"M1","factory_id":"F1","is_active":True,"material_name":"톨루엔","material_category_code":"FL"}])
    fm.update_material("M1", FactoryMaterialUpdate(**{"material_name":None}), _Cur())
    assert sb.stores["factory_materials"][0]["material_name"] is None
def test_patch_foreign_404_no_write(monkeypatch):
    sb=_env(monkeypatch, own_ok=False, mats=[{"id":"M1","factory_id":"F1","is_active":True,"material_name":"x"}])
    with pytest.raises(HTTPException) as e:
        fm.update_material("M1", FactoryMaterialUpdate(material_name="y"), _Cur())
    assert e.value.status_code==404 and sb.counters["writes"]==0

# ---- delete ----
def test_delete_soft(monkeypatch):
    sb=_env(monkeypatch, mats=[{"id":"M1","factory_id":"F1","is_active":True,"material_name":"x"}])
    fm.delete_material("M1", _Cur())
    assert sb.stores["factory_materials"][0]["is_active"] is False
def test_delete_foreign_404_no_write(monkeypatch):
    sb=_env(monkeypatch, own_ok=False, mats=[{"id":"M1","factory_id":"F1","is_active":True,"material_name":"x"}])
    with pytest.raises(HTTPException) as e: fm.delete_material("M1", _Cur())
    assert e.value.status_code==404 and sb.counters["writes"]==0

# ---- forbidden refs ----
def _code_only(src):
    import re
    # strip module docstring (first triple-quoted block) + # comments
    src = re.sub(r'"""(?:.|\n)*?"""', "", src, count=1)
    return "\n".join(ln.split("#",1)[0] for ln in src.splitlines())
def test_no_marketing_legal_refs():
    code=_code_only(open("routers/factory_materials.py").read())
    # actual table queries / storage / routes / relations must be absent in code (docstring 언급 허용)
    assert '"material_profile"' not in code and '.table("diagnosis_input_fields")' not in code
    assert '.table("kosha_safety_materials")' not in code and '.table("runtime_facility_hazard")' not in code
    assert "legal_material" not in code and "legal-diagnosis" not in code and "legal-material" not in code
    assert '"factory_process_id"' not in code and "factory_process_id=" not in code
    assert "create_client" not in code
