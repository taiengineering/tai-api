"""STEP4 — factory_process canonical extension (auth/ownership + 3 fields + sparse PATCH)."""
import copy, asyncio
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import routers.factory_process_v3 as pr
from routers.factory_process_v3 import ProcessCreateBody, ProcessUpdateBody, PROCESS_CANONICAL_NULL_CLEAR_FIELDS, _proc_apply_canonical

def _run(c): return asyncio.get_event_loop().run_until_complete(c)

class _Res:
    def __init__(s,d,count=None): s.data=d; s.count=count
class _Q:
    def __init__(s,store,c): s.store=store; s.c=c; s._f={}; s._upd=None; s._ins=None
    def select(s,*a,**k): return s
    def eq(s,col,val): s._f[col]=val; return s
    def in_(s,col,vals): s._f[col]=("in",set(vals)); return s
    def ilike(s,*a,**k): return s
    def order(s,*a,**k): return s
    def range(s,*a,**k): return s
    def limit(s,n): return s
    def update(s,d): s._upd=d; s.c["writes"]+=1; return s
    def insert(s,d): s._ins=d; s.c["writes"]+=1; return s
    def execute(s):
        s.c["reads"]+=1
        rows=[]
        for r in s.store:
            ok=True
            for k,v in s._f.items():
                if isinstance(v,tuple) and v[0]=="in":
                    if r.get(k) not in v[1]: ok=False
                elif r.get(k)!=v: ok=False
            if ok: rows.append(r)
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
    def in_(s,*a,**k): return _Q(s.store,s.c).in_(*a,**k)
class FakeSB:
    def __init__(s, proc=None):
        s.stores={"factory_process":proc if proc is not None else [],
                  "v_process_unified":[{"process_id":"P1","process_lv1":"a","process_lv2":"b","process_lv3":"c","process_lv4":"d","process_path":"a>b>c>d"}]}
        s.counters={"reads":0,"writes":0}
    def table(s,n): s.stores.setdefault(n,[]); return _T(n,s.stores[n],s.counters)

class _Cur(dict): pass
def _env(monkeypatch, own_ok=True, proc=None):
    sb=FakeSB(proc=proc)
    monkeypatch.setattr(pr,"get_supabase",lambda: sb)
    def own(s,fid,cur):
        if not own_ok: raise HTTPException(status_code=404, detail="foreign")
    monkeypatch.setattr(pr,"_ensure_factory_own",own)
    return sb

# ---- models: strict ----
def test_worker_count_strict():
    assert ProcessCreateBody(worker_count=0).worker_count==0
    assert ProcessCreateBody(worker_count=5).worker_count==5
    for bad in [-1, True, "3", 3.5]:
        with pytest.raises(ValidationError): ProcessCreateBody(worker_count=bad)
def test_arrays_strict():
    assert ProcessCreateBody(hazard_codes=[]).hazard_codes==[]
    assert ProcessCreateBody(hazard_codes=["H1"]).hazard_codes==["H1"]
    for bad in [[1],[True],[{"a":1}],[["x"]],[""],["  "]]:
        with pytest.raises(ValidationError): ProcessCreateBody(activity_types=bad)
def test_nullclear_set():
    assert PROCESS_CANONICAL_NULL_CLEAR_FIELDS=={"hazard_codes","worker_count","activity_types"}

# ---- _proc_apply_canonical (CREATE wiring) ----
def test_apply_canonical_provided_only():
    d={}; _proc_apply_canonical(d, ProcessCreateBody(source="MANUAL", process_name_manual="x", worker_count=0, hazard_codes=[]))
    assert d=={"worker_count":0,"hazard_codes":[]}  # activity_types omitted → 미포함; 0/[] 보존
def test_apply_canonical_omitted_absent():
    d={}; _proc_apply_canonical(d, ProcessCreateBody(source="MANUAL", process_name_manual="x"))
    assert d=={}

# ---- real route: GET/POST/PATCH/DELETE security + wiring ----
def test_get_includes_3_own(monkeypatch):
    sb=_env(monkeypatch, proc=[{"id":"R1","factory_id":"F1","process_id":"P1","source":"MANUAL","is_active":True,"process_name_manual":"m","hazard_codes":["H"],"worker_count":2,"activity_types":[]}])
    r=_run(pr.get_factory_processes("F1", _Cur(role_code="010")))
    it=r["data"]["items"][0]
    assert it["hazard_codes"]==["H"] and it["worker_count"]==2 and it["activity_types"]==[]
def test_get_foreign_404_no_query(monkeypatch):
    sb=_env(monkeypatch, own_ok=False)
    with pytest.raises(HTTPException) as e: _run(pr.get_factory_processes("F1", _Cur()))
    assert e.value.status_code==404 and sb.counters["reads"]==0
def test_post_manual_wires_3(monkeypatch):
    sb=_env(monkeypatch, proc=[])
    r=_run(pr.add_factory_process("F1", ProcessCreateBody(source="MANUAL", process_name_manual="용접", worker_count=3, hazard_codes=["FIRE"], activity_types=["WELD"]), _Cur()))
    row=sb.stores["factory_process"][0]
    assert row["worker_count"]==3 and row["hazard_codes"]==["FIRE"] and row["activity_types"]==["WELD"]
def test_post_foreign_404_no_write_no_trace(monkeypatch):
    sb=_env(monkeypatch, own_ok=False, proc=[])
    with pytest.raises(HTTPException) as e:
        _run(pr.add_factory_process("F1", ProcessCreateBody(source="MANUAL", process_name_manual="x"), _Cur()))
    assert e.value.status_code==404 and sb.counters["writes"]==0
def test_patch_sparse_null_clear(monkeypatch):
    sb=_env(monkeypatch, proc=[{"id":"R1","factory_id":"F1","is_active":True,"hazard_codes":["H"],"worker_count":2}])
    r=_run(pr.update_factory_process("F1","R1", ProcessUpdateBody(**{"worker_count":None}), _Cur()))
    assert sb.stores["factory_process"][0]["worker_count"] is None
def test_patch_zero_empty_preserved(monkeypatch):
    sb=_env(monkeypatch, proc=[{"id":"R1","factory_id":"F1","is_active":True}])
    _run(pr.update_factory_process("F1","R1", ProcessUpdateBody(worker_count=0, hazard_codes=[]), _Cur()))
    row=sb.stores["factory_process"][0]
    assert row["worker_count"]==0 and row["hazard_codes"]==[]
def test_patch_omitted_preserve(monkeypatch):
    sb=_env(monkeypatch, proc=[{"id":"R1","factory_id":"F1","is_active":True,"hazard_codes":["H"]}])
    _run(pr.update_factory_process("F1","R1", ProcessUpdateBody(worker_count=5), _Cur()))
    row=sb.stores["factory_process"][0]
    assert row["worker_count"]==5 and row["hazard_codes"]==["H"]  # omitted 보존
def test_patch_missing_404(monkeypatch):
    sb=_env(monkeypatch, proc=[])
    with pytest.raises(HTTPException) as e:
        _run(pr.update_factory_process("F1","RX", ProcessUpdateBody(worker_count=1), _Cur()))
    assert e.value.status_code==404 and sb.counters["writes"]==0
def test_patch_inactive_404(monkeypatch):
    sb=_env(monkeypatch, proc=[{"id":"R1","factory_id":"F1","is_active":False}])
    with pytest.raises(HTTPException) as e:
        _run(pr.update_factory_process("F1","R1", ProcessUpdateBody(worker_count=1), _Cur()))
    assert e.value.status_code==404
def test_patch_cross_factory_404(monkeypatch):
    sb=_env(monkeypatch, proc=[{"id":"R1","factory_id":"F2","is_active":True}])
    with pytest.raises(HTTPException) as e:
        _run(pr.update_factory_process("F1","R1", ProcessUpdateBody(worker_count=1), _Cur()))
    assert e.value.status_code==404
def test_delete_foreign_404_no_write(monkeypatch):
    sb=_env(monkeypatch, own_ok=False, proc=[{"id":"R1","factory_id":"F1","is_active":True}])
    with pytest.raises(HTTPException) as e:
        _run(pr.delete_factory_process("F1","R1", _Cur()))
    assert e.value.status_code==404 and sb.counters["writes"]==0
def test_bulk_foreign_404(monkeypatch):
    sb=_env(monkeypatch, own_ok=False)
    with pytest.raises(HTTPException) as e:
        _run(pr.bulk_add_factory_processes("F1", {"process_ids":["P1"]}, _Cur()))
    assert e.value.status_code==404
def test_recommend_foreign_404(monkeypatch):
    sb=_env(monkeypatch, own_ok=False)
    with pytest.raises(HTTPException) as e:
        _run(pr.recommend_equipment("F1", None, _Cur()))
    assert e.value.status_code==404

# ---- static: legal absent, factory_process_id untouched, routes ----
def test_no_legal_and_routes():
    src=open("routers/factory_process_v3.py").read()
    assert "legal_hazard" not in src and "legal_worker" not in src and "legal_activity" not in src
    assert "legal-diagnosis" not in src and "legal-process" not in src
    # factory_process_id must not be used as a code column ref (docstring 언급은 허용)
    assert 'factory_process_id"' not in src and "factory_process_id'" not in src
    paths={r.path for r in pr.router.routes}
    assert "/factory-process/{factory_id}/processes" in paths
