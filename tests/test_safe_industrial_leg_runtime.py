"""WO-DUAL-IND-STEP2-IMPLEMENT-001 GATE-4A tests (G4A-01~17).

WO-010 STEP-2C : run_safe_industrial_leg 이 canonical29 final-cut 을 제거하고
build_saas_leg_step1(→ build_unified_leg_input, _LEG_INPUT_FIELDS 103 필터) 로 배선됐다.
그에 따라 step1.input 의 계약이 바뀐다 :
  · 원 계약 : list(input.keys()) == TARGET_FIELDS(29), len==29 (None 슬롯도 포함)
  · 새 계약 : input.keys() ⊆ _LEG_INPUT_FIELDS(103), None/blank 배제, 값 있는 것만 통과
  · has_chemical_substance(canonical29 축) 는 _LEG_INPUT_FIELDS 밖 → unified 필터에서 제외.
    대신 승인된 alias(_LEG_CODE_TO_CONSUMER) 로 canonical key `has_chemical` 에 승격되어 입장.
build_facility 도달축(EXISTING facility parity) 은 불변. 자세한 파리티 검증은
tests/test_wo010_2c_saas_api_cutover.py 참조.
"""
import pytest
from clients.leg_runtime_client import _LEG_INPUT_FIELDS
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

# G4A-03 STEP-2C : step1.input.keys() ⊆ _LEG_INPUT_FIELDS(103), 값 있는 것만 통과.
#   canonical29 final-cut 제거 이후 계약. TARGET_FIELDS 상한 검증은 파일 하단 STEP-2C 파리티 test 로 이관.
def test_G4A03_canonical_29(patched):
    R.run_safe_industrial_leg(object(), "F1", SafeIndustrialConsumerInput())
    inp = patched["step1"].input
    assert set(inp.keys()) <= set(_LEG_INPUT_FIELDS), (
        "step1.input.keys() 는 _LEG_INPUT_FIELDS(103) 부분집합이어야 한다"
    )
    # 값 있는 canonical29 축은 통과(worker_count 50 / ksic_major "C10"). has_chemical_substance 는
    # _LEG_INPUT_FIELDS 밖 → 필터 배제. alias 승격으로 has_chemical=True 가 대신 입장.
    assert inp.get("worker_count") == 50
    assert inp.get("ksic_major") == "C10"
    assert inp.get("has_chemical") is True
    assert "has_chemical_substance" not in inp   # _LEG_INPUT_FIELDS 밖 → unified 필터 배제

# G4A-11 sector=INDUSTRIAL, input에 canonical(top-level shadow 0)
def test_G4A11_sector_input(patched):
    R.run_safe_industrial_leg(object(), "F1", SafeIndustrialConsumerInput())
    s1 = patched["step1"]
    assert s1.sector == "INDUSTRIAL" and isinstance(s1.input, dict)
    # canonical key가 top-level 속성으로 shadow되지 않음(input에만)
    assert s1.input["worker_count"] == 50

# G4A-04 None override = asset 유지 (미override) — STEP-2C 계약 : has_chemical_substance 는
#   alias 승격(has_chemical) 로 입장. asset 값 True 는 그대로 도달.
def test_G4A04_none_keeps_asset(patched):
    R.run_safe_industrial_leg(object(), "F1", SafeIndustrialConsumerInput())  # 전부 None
    assert patched["step1"].input["worker_count"] == 50  # asset 값 유지
    assert patched["step1"].input["has_chemical"] is True  # alias 승격

# G4A-05 false/0/"" override (non-null → override) — STEP-2C : has_chemical_substance False 는
#   alias 승격(has_chemical=False) 로 입장, false 보존.
def test_G4A05_false_zero_override(patched):
    ci = SafeIndustrialConsumerInput(has_chemical_substance=False, worker_count=0, has_safety_manager=False)
    R.run_safe_industrial_leg(object(), "F1", ci)
    inp = patched["step1"].input
    assert inp["has_chemical"] is False             # True→False override, alias 승격 후 false 보존
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

# G4A-16 STEP-2C : SAFE_UI_OVERRIDE_FIELDS 밖 field 진입 불가 규약 유지.
#   원 계약(len==29) 은 canonical29 final-cut 제거로 대체 — 대신 step1.input.keys() 는
#   여전히 _LEG_INPUT_FIELDS(103) 부분집합이고, SAFE_UI_OVERRIDE_FIELDS ⊆ TARGET_FIELDS 는 불변.
def test_G4A16_no_30th(patched):
    R.run_safe_industrial_leg(object(), "F1", SafeIndustrialConsumerInput())
    inp = patched["step1"].input
    assert set(inp.keys()) <= set(_LEG_INPUT_FIELDS), (
        "SAFE_UI_OVERRIDE_FIELDS 밖 신규 key 는 진입할 수 없다"
    )
    assert set(R.SAFE_UI_OVERRIDE_FIELDS) <= set(TARGET_FIELDS)

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
