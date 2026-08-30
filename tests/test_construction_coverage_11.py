# WO-FE-CST-GAP-IMPL-001 E-C — CONSTRUCTION 11 fact via official form_data envelope, REAL run_diagnosis.
# E-C1: paid base input 보존. CORRECTION-01: 0≠None + invalid 422. CORRECTION-02: structural mapping sector-gate.
from schemas.diagnosis_integrated import DiagnosisRunBody
from clients.leg_runtime_client import build_facility
from services import diagnosis_integrated_svc as _svc

CST11 = ["has_tower_crane", "has_subcontractor", "has_excavation", "has_demolition",
         "has_asbestos", "has_chemical_substance", "has_gas", "has_high_pressure_gas",
         "has_water_tank", "is_energy_intensive", "is_multi_use"]


class _R:
    def __init__(self, data): self.data = data
class _T:
    def __init__(self, n): self._n = n
    def select(self,*a,**k): return self
    def eq(self,*a,**k): return self
    def limit(self,*a,**k): return self
    def update(self,*a,**k): return self
    def insert(self,row): self._p=row; return self
    def execute(self):
        if self._n=="diagnosis_auth_log": return _R([{"id":"a1","ci_hash":"ci","name":"n","phone":"p","free_count":0,"free_limit":3,"status":"ACTIVE","linked_user_id":None}])
        if self._n=="diagnosis_disclaimer_log": return _R([{"id":"disc1","ci_hash":"ci","agreed":True}])
        if self._n=="anonymous_diagnosis_results": return _R([{**(getattr(self,"_p",None) or {}),"id":"r1"}])
        return _R([])
class _S:
    def table(self,n): return _T(n)

def _cap(body):
    cap={}
    def r1(sb,s1): cap["s1"]=s1; return {"status":"success","data":{"applicable_count":0,"rules_table":[]}}
    _svc.run_diagnosis(_S(),body,run_step1_func=r1,
        auto_tier_func=lambda *a,**k:"CONSTRUCTION_X",build_partial_func=lambda f:{},now_func=lambda:"2026-01-01T00:00:00Z",
        paid_tier_prices={},free_tier_codes={"CONSTRUCTION_FREE","INDUSTRY_FREE","BUILDING_FREE"},engine_version="t",current_user=None)
    return build_facility(cap["s1"])

def _body(sector,fd):
    return DiagnosisRunBody(auth_token="t",sector=sector,disclaimer_log_id="disc1",form_data=fd)

def test_11_true_via_formdata():
    fac=_cap(_body("CONSTRUCTION",{c:True for c in CST11}))
    assert all(fac.get(c) is True for c in CST11), {c:fac.get(c) for c in CST11}

def test_11_false_via_formdata():
    fac=_cap(_body("CONSTRUCTION",{c:False for c in CST11}))
    assert all(fac.get(c) is False for c in CST11)

def test_chemical_exact_name():
    fac=_cap(_body("CONSTRUCTION",{"has_chemical_substance":True}))
    assert fac.get("has_chemical_substance") is True and "has_chemical" not in fac

def test_industrial_firewall():
    fac=_cap(_body("INDUSTRIAL",{"has_gas":True}))
    assert fac.get("has_gas") is True
    b=DiagnosisRunBody(auth_token="t",sector="INDUSTRIAL",disclaimer_log_id="disc1",has_chemical_substance=True)
    fac2=_cap(b)
    assert fac2.get("has_chemical") is True and "has_chemical_substance" not in fac2

def test_building_firewall():
    fac=_cap(_body("BUILDING",{"has_gas":True}))
    assert fac.get("has_gas") is True

def test_non_target_via_formdata():
    fac=_cap(_body("CONSTRUCTION",{"has_welding":True}))
    assert fac.get("has_welding") is True


# ── E-C1: paid base input preservation after Nexas quarantine ──
def _cap_all(body):
    """run_diagnosis 로 생성된 step1_body + 저장 row + auto_tier 전달값 캡처."""
    cap = {}
    def r1(sb, s1):
        cap["s1"] = s1
        return {"status": "success", "data": {"applicable_count": 0, "rules_table": []}}
    class _T2(_T):
        def insert(self, row):
            if self._n == "anonymous_diagnosis_results":
                cap["row"] = row
            return super().insert(row)
    class _S2:
        def table(self, n): return _T2(n)
    tier_seen = {}
    def _auto_tier(sector, floor_area, contract_amount_eok, user_tier):
        tier_seen["contract_amount_eok"] = contract_amount_eok
        return "CONSTRUCTION_X"
    _svc.run_diagnosis(_S2(), body, run_step1_func=r1,
        auto_tier_func=_auto_tier, build_partial_func=lambda f: {}, now_func=lambda: "2026-01-01T00:00:00Z",
        paid_tier_prices={}, free_tier_codes={"CONSTRUCTION_FREE", "INDUSTRY_FREE", "BUILDING_FREE"},
        engine_version="t", current_user=None)
    return cap["s1"], cap.get("row", {}), tier_seen


def test_ec1_paid_base_input_preserved_form_data_only():
    fd = {
        "project_amount": 50, "worker_count": 100, "construction_type": "토목",
        "project_address": "서울시 강남구", "process_list": [{"process_name": "굴착"}],
        **{c: True for c in CST11},
    }
    s1, row, tier_seen = _cap_all(_body("CONSTRUCTION", fd))
    assert s1.worker_count == 100, s1.worker_count
    assert s1.construction_type == "토목", s1.construction_type
    assert float(s1.contract_amount_eok) == 50.0, s1.contract_amount_eok
    assert (s1.input or {}).get("region") == "서울시 강남구", (s1.input or {}).get("region")
    assert tier_seen["contract_amount_eok"] == 50.0, tier_seen
    rsi = (row.get("input_data") or {}).get("raw_structured_input") or {}
    assert rsi.get("process_list") == [{"process_name": "굴착"}], rsi
    fac = build_facility(s1)
    assert all(fac.get(c) is True for c in CST11), {c: fac.get(c) for c in CST11}


def test_ec1_top_level_precedence_over_form_data():
    b = DiagnosisRunBody(auth_token="t", sector="CONSTRUCTION", disclaimer_log_id="disc1",
                         worker_count=7, contract_amount_eok=3.0,
                         form_data={"worker_count": 100, "project_amount": 50})
    s1, _, tier_seen = _cap_all(b)
    assert s1.worker_count == 7
    assert float(s1.contract_amount_eok) == 3.0
    assert tier_seen["contract_amount_eok"] == 3.0


# ── E-C1 CORRECTION-01: zero preservation + invalid numeric fail-closed ──
import pytest
from fastapi import HTTPException


def test_ec1c1_zero_preserved():
    fd = {"project_amount": 0, "worker_count": 0, "construction_type": "토목"}
    s1, row, tier_seen = _cap_all(_body("CONSTRUCTION", fd))
    assert tier_seen["contract_amount_eok"] == 0.0, tier_seen
    assert float(s1.contract_amount_eok) == 0.0, s1.contract_amount_eok
    assert s1.worker_count == 0, s1.worker_count
    idata = row.get("input_data") or {}
    assert float(idata.get("contract_amount_eok")) == 0.0, idata
    assert idata.get("workers") == 0, idata


def test_ec1c1_invalid_project_amount_422():
    with pytest.raises(HTTPException) as ei:
        _cap_all(_body("CONSTRUCTION", {"project_amount": "INVALID"}))
    assert ei.value.status_code == 422


def test_ec1c1_invalid_worker_count_422():
    with pytest.raises(HTTPException) as ei:
        _cap_all(_body("CONSTRUCTION", {"worker_count": "INVALID"}))
    assert ei.value.status_code == 422


# ── E-C1 CORRECTION-02: CONSTRUCTION structural mapping firewall (sector-gated) ──
def test_ec1c2_building_project_amount_not_mapped():
    _, _, tier_seen = _cap_all(_body("BUILDING", {"project_amount": 50}))
    assert tier_seen["contract_amount_eok"] == 0.0, tier_seen  # BUILDING 은 project_amount 미매핑

def test_ec1c2_industrial_project_amount_not_mapped():
    _, _, tier_seen = _cap_all(_body("INDUSTRIAL", {"project_amount": 50}))
    assert tier_seen["contract_amount_eok"] == 0.0, tier_seen

def test_ec1c2_building_project_address_not_region():
    s1, _, _ = _cap_all(_body("BUILDING", {"project_address": "서울시"}))
    assert (s1.input or {}).get("region") in (None, ""), (s1.input or {}).get("region")

def test_ec1c2_industrial_project_address_not_region():
    s1, _, _ = _cap_all(_body("INDUSTRIAL", {"project_address": "서울시"}))
    assert (s1.input or {}).get("region") in (None, ""), (s1.input or {}).get("region")

def test_ec1c2_building_unrelated_invalid_project_amount_no_422():
    # BUILDING 의 form_data.project_amount 는 CONSTRUCTION 전용 validator 대상 아님 → 422 아님
    s1, _, tier_seen = _cap_all(_body("BUILDING", {"project_amount": "INVALID"}))
    assert tier_seen["contract_amount_eok"] == 0.0

def test_ec1c2_industrial_unrelated_invalid_project_amount_no_422():
    s1, _, tier_seen = _cap_all(_body("INDUSTRIAL", {"project_amount": "INVALID"}))
    assert tier_seen["contract_amount_eok"] == 0.0

def test_ec1c2_construction_project_amount_still_mapped():
    _, _, tier_seen = _cap_all(_body("CONSTRUCTION", {"project_amount": 50}))
    assert tier_seen["contract_amount_eok"] == 50.0
