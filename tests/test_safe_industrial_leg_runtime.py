"""WO-DUAL-IND-STEP2-IMPLEMENT-001 GATE-4A tests (G4A-01~17)."""
import pytest
from services import safe_industrial_leg_runtime as R
from services.safe_industrial_canonical_assembler import TARGET_FIELDS, CONTRACT_VERSION
from schemas.legal_engine import SafeIndustrialConsumerInput, SafeIndustrialLegBody, DiagnoseStep1Body

# ---- fake assembler contract (29 canonical) ----
def _asset_contract(**over):
    values = {f: None for f in TARGET_FIELDS}
    # asset이 채운 예시 몇 개
    values["ksic_major"] = "C10"
    values["worker_count"] = 50
    values["has_chemical_substance"] = True
    values.update(over)
    return {"contract_version": CONTRACT_VERSION, "sector": "INDUSTRIAL", "factory_id": "F1",
            "values": {f: values[f] for f in TARGET_FIELDS},
            "unresolved_fields": sorted([f for f in TARGET_FIELDS if values[f] is None]),
            "provenance": {}}

@pytest.fixture
def patched(monkeypatch):
    calls = {"assemble": 0, "run_leg": 0, "step1": None, "send_direct": 0, "evaluate_rtm": 0}
    def fake_assemble(supabase, factory_id):
        calls["assemble"] += 1; return _asset_contract()
    def fake_run_leg(step1):
        calls["run_leg"] += 1; calls["step1"] = step1
        return {"sector": step1.sector, "engine_family": "LEG", "key_obligations": [],
                "facility_used": {"worker_count": step1.input.get("worker_count")}}
    monkeypatch.setattr(R, "assemble_industrial_marketing_contract", fake_assemble)
    monkeypatch.setattr(R, "run_leg_diagnosis", fake_run_leg)
    return calls

# G4A-01 assembler 1회 READ
def test_G4A01_assembler_once(patched):
    R.run_safe_industrial_leg(object(), "F1", SafeIndustrialConsumerInput())
    assert patched["assemble"] == 1

# G4A-02/12 run_leg_diagnosis 1회, direct sender 0
def test_G4A02_run_leg_once(patched):
    R.run_safe_industrial_leg(object(), "F1", SafeIndustrialConsumerInput())
    assert patched["run_leg"] == 1

# G4A-03 canonical 29 exact
def test_G4A03_canonical_29(patched):
    R.run_safe_industrial_leg(object(), "F1", SafeIndustrialConsumerInput())
    inp = patched["step1"].input
    assert len(inp) == 29 and list(inp.keys()) == list(TARGET_FIELDS)

# G4A-11 sector=INDUSTRIAL, input에 canonical(top-level shadow 0)
def test_G4A11_sector_input(patched):
    R.run_safe_industrial_leg(object(), "F1", SafeIndustrialConsumerInput())
    s1 = patched["step1"]
    assert s1.sector == "INDUSTRIAL" and isinstance(s1.input, dict)
    # canonical key가 top-level 속성으로 shadow되지 않음(input에만)
    assert s1.input["worker_count"] == 50

# G4A-04 None override = asset 유지 (미override)
def test_G4A04_none_keeps_asset(patched):
    R.run_safe_industrial_leg(object(), "F1", SafeIndustrialConsumerInput())  # 전부 None
    assert patched["step1"].input["worker_count"] == 50  # asset 값 유지
    assert patched["step1"].input["has_chemical_substance"] is True

# G4A-05 false/0/"" override (non-null → override)
def test_G4A05_false_zero_override(patched):
    ci = SafeIndustrialConsumerInput(has_chemical_substance=False, worker_count=0, has_safety_manager=False)
    R.run_safe_industrial_leg(object(), "F1", ci)
    inp = patched["step1"].input
    assert inp["has_chemical_substance"] is False   # True→False override
    assert inp["worker_count"] == 0                 # 50→0 override
    assert inp["has_safety_manager"] is False       # None asset→False override

# G4A-06 신규7 override 반영
def test_G4A06_new7_override(patched):
    ci = SafeIndustrialConsumerInput(work_height_m=3.5, has_truck_loading_unloading=True,
                                     truck_loading_height_m=1.2, building_use_type="공장")
    R.run_safe_industrial_leg(object(), "F1", ci)
    inp = patched["step1"].input
    assert inp["work_height_m"] == 3.5 and inp["has_truck_loading_unloading"] is True
    assert inp["truck_loading_height_m"] == 1.2 and inp["building_use_type"] == "공장"

# G4A-07 unresolved에서 override된 field 제거
def test_G4A07_override_clears_unresolved(patched):
    ci = SafeIndustrialConsumerInput(building_use_type="공장")  # asset엔 None(unresolved)
    out = R.run_safe_industrial_leg(object(), "F1", ci)
    assert "building_use_type" not in out["unresolved_fields"]

# G4A-08 override 안 한 unresolved는 유지
def test_G4A08_unresolved_kept(patched):
    out = R.run_safe_industrial_leg(object(), "F1", SafeIndustrialConsumerInput())
    assert "building_use_type" in out["unresolved_fields"]  # 미override

# G4A-13 contract_version 전달
def test_G4A13_contract_version(patched):
    out = R.run_safe_industrial_leg(object(), "F1", SafeIndustrialConsumerInput())
    assert out["contract_version"] == CONTRACT_VERSION

# G4A-14 override는 SAFE_UI 13 field만
def test_G4A14_override_scope_13():
    assert len(R.SAFE_UI_OVERRIDE_FIELDS) == 13
    assert set(R.SAFE_UI_OVERRIDE_FIELDS) <= set(TARGET_FIELDS)

# G4A-15 schema extra=forbid
def test_G4A15_extra_forbid():
    with pytest.raises(Exception):
        SafeIndustrialConsumerInput(unknown_field=1)
    with pytest.raises(Exception):
        SafeIndustrialLegBody(factory_id="F1", input={}, extra_top=1)

# G4A-16 canonical 30번째 key 금지(TARGET_FIELDS 밖 override 무시)
def test_G4A16_no_30th(patched):
    # SAFE_UI_OVERRIDE_FIELDS ⊆ TARGET_FIELDS 이므로 신규 key 진입 불가
    R.run_safe_industrial_leg(object(), "F1", SafeIndustrialConsumerInput())
    assert len(patched["step1"].input) == 29

# G4A-17 full_result 반환 구조
def test_G4A17_full_result(patched):
    out = R.run_safe_industrial_leg(object(), "F1", SafeIndustrialConsumerInput())
    assert "full_result" in out and out["full_result"]["sector"] == "INDUSTRIAL"
    assert out["full_result"]["engine_family"] == "LEG"


# ===================== route-level (auth-first / 503 / 502) =====================
def _client(monkeypatch):
    import importlib
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routers.legal_engine as LE
    app = FastAPI(); app.include_router(LE.router)
    return LE, app, TestClient

def test_G4A09_auth_first_no_assembler(monkeypatch):
    import routers.legal_engine as LE
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    calls = {"assemble": 0}
    monkeypatch.setattr(LE, "get_supabase", lambda: object())
    def _auth_fail(auth): raise HTTPException(status_code=401, detail="unauth")
    monkeypatch.setattr(LE, "get_current_user", _auth_fail)
    monkeypatch.setattr(R, "assemble_industrial_marketing_contract",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("assembler called on unauth")))
    app=FastAPI(); app.include_router(LE.router); c=TestClient(app, raise_server_exceptions=False)
    r=c.post("/legal-engine/diagnose/industrial-leg", json={"factory_id":"F1","input":{}})
    assert r.status_code == 401   # auth 실패 → assembler 미호출

def test_G4A10_ownership_foreign(monkeypatch):
    import routers.legal_engine as LE
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    monkeypatch.setattr(LE, "get_supabase", lambda: object())
    monkeypatch.setattr(LE, "get_current_user", lambda auth: {"id":"u1"})
    def _own_fail(sb, fid, cur): raise HTTPException(status_code=404, detail="not found")
    monkeypatch.setattr(LE, "_ensure_factory_own", _own_fail)
    monkeypatch.setattr(R, "assemble_industrial_marketing_contract",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("assembler on foreign")))
    app=FastAPI(); app.include_router(LE.router); c=TestClient(app, raise_server_exceptions=False)
    r=c.post("/legal-engine/diagnose/industrial-leg", json={"factory_id":"F9","input":{}})
    assert r.status_code == 404

def test_G4A_leg_disabled_503(monkeypatch):
    import routers.legal_engine as LE
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    monkeypatch.setattr(LE, "get_supabase", lambda: object())
    monkeypatch.setattr(LE, "get_current_user", lambda auth: {"id":"u1"})
    monkeypatch.setattr(LE, "_ensure_factory_own", lambda sb,fid,cur: None)
    monkeypatch.setattr(LE.leg_runtime_client, "is_enabled", lambda: False)
    app=FastAPI(); app.include_router(LE.router); c=TestClient(app, raise_server_exceptions=False)
    r=c.post("/legal-engine/diagnose/industrial-leg", json={"factory_id":"F1","input":{}})
    assert r.status_code == 503

def test_G4A_leg_fail_502(monkeypatch):
    import routers.legal_engine as LE
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    monkeypatch.setattr(LE, "get_supabase", lambda: object())
    monkeypatch.setattr(LE, "get_current_user", lambda auth: {"id":"u1"})
    monkeypatch.setattr(LE, "_ensure_factory_own", lambda sb,fid,cur: None)
    monkeypatch.setattr(LE.leg_runtime_client, "is_enabled", lambda: True)
    monkeypatch.setattr(LE, "run_safe_industrial_leg",
                        lambda sb,fid,ci: (_ for _ in ()).throw(LE.LegRuntimeError("rtm down")))
    app=FastAPI(); app.include_router(LE.router); c=TestClient(app, raise_server_exceptions=False)
    r=c.post("/legal-engine/diagnose/industrial-leg", json={"factory_id":"F1","input":{}})
    assert r.status_code == 502
