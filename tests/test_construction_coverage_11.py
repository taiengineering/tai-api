# WO-FE-CST-GAP-IMPL-001 E-B1 — CONSTRUCTION 11 fact via form_data (primary path), REAL run_diagnosis.
# FIX-B1(CODE-C1 제거)+FIX-B2(chemical step1 bridge)+FIX-B3(C2 keep) 후 form_data 경로로 11 fact 가
# canonical→build_facility→facility 로 materialize 되는지 실제 run_diagnosis→build_facility 로 관측.
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
    # 산업은 form_data.has_gas → 공통 canonical 배선(정상, 변경 없음)
    fac=_cap(_body("INDUSTRIAL",{"has_gas":True}))
    assert fac.get("has_gas") is True
    # 산업 chemical 은 top-level body.has_chemical_substance(else 분기) — FIX-B2(CONSTRUCTION 전용) 무관.
    # build_facility alias 로 facility.has_chemical 유지(C2 는 CONSTRUCTION-gated → 산업 facility.has_chemical 불변)
    b=DiagnosisRunBody(auth_token="t",sector="INDUSTRIAL",disclaimer_log_id="disc1",has_chemical_substance=True)
    fac2=_cap(b)
    assert fac2.get("has_chemical") is True and "has_chemical_substance" not in fac2

def test_building_firewall():
    fac=_cap(_body("BUILDING",{"has_gas":True}))
    assert fac.get("has_gas") is True  # 공통 canonical 배선(정상), CONSTRUCTION 전용 로직 미적용

def test_non_target_via_formdata():
    fac=_cap(_body("CONSTRUCTION",{"has_welding":True}))
    assert fac.get("has_welding") is True  # has_welding 도 _LEG vocab → 공통 배선(정상). 11 밖이지만 canonical 은 vocab 전체 허용
