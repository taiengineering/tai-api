# WO-FE-CST-EQUIPMENT-CAPTURE-WIRING-001: equipment_assets → 5 legal fact (TAI boundary), exact code equality.
# 010→has_emergency_gen/014→has_boiler/023→has_press/024→has_conveyor/038→has_pressure_vessel.
# 등록 설비만 true, 미등록 UNKNOWN(false 자동생성 금지), 정본 밖 code 는 fact 미생성. real run_diagnosis→build_facility 관측.
from schemas.diagnosis_integrated import DiagnosisRunBody
from clients.leg_runtime_client import build_facility
from services import diagnosis_integrated_svc as _svc

EQ = {"010": "has_emergency_gen", "014": "has_boiler", "023": "has_press",
      "024": "has_conveyor", "038": "has_pressure_vessel"}


class _R:
    def __init__(self, d): self.data = d
class _T:
    def __init__(self, n, eq): self._n = n; self._eq = eq
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def update(self, *a, **k): return self
    def insert(self, row): self._p = row; return self
    def execute(self):
        if self._n == "diagnosis_auth_log": return _R([{"id": "a1", "ci_hash": "ci", "name": "n", "phone": "p", "free_count": 0, "free_limit": 3, "status": "ACTIVE", "linked_user_id": None}])
        if self._n == "diagnosis_disclaimer_log": return _R([{"id": "disc1", "ci_hash": "ci", "agreed": True}])
        if self._n == "anonymous_diagnosis_results": return _R([{**(getattr(self, "_p", None) or {}), "id": "r1"}])
        if self._n == "equipment_assets": return _R([{"equipment_type_code": c} for c in self._eq])
        return _R([])
class _S:
    def __init__(self, eq): self._eq = eq
    def table(self, n): return _T(n, self._eq)


def _cap(codes, factory="f1"):
    cap = {}
    def r1(sb, s1): cap["s1"] = s1; return {"status": "success", "data": {"applicable_count": 0, "rules_table": []}}
    b = DiagnosisRunBody(auth_token="t", sector="CONSTRUCTION", disclaimer_log_id="disc1", factory_id=factory)
    _svc.run_diagnosis(_S(codes), b, run_step1_func=r1, auto_tier_func=lambda *a, **k: "CONSTRUCTION_X",
        build_partial_func=lambda f: {}, now_func=lambda: "2026-01-01T00:00:00Z", paid_tier_prices={},
        free_tier_codes={"CONSTRUCTION_FREE"}, engine_version="t", current_user=None)
    return build_facility(cap["s1"])


def test_equipment_contract_010(): assert _cap(["010"]).get("has_emergency_gen") is True
def test_equipment_contract_014(): assert _cap(["014"]).get("has_boiler") is True
def test_equipment_contract_023(): assert _cap(["023"]).get("has_press") is True
def test_equipment_contract_024(): assert _cap(["024"]).get("has_conveyor") is True
def test_equipment_contract_038(): assert _cap(["038"]).get("has_pressure_vessel") is True


def test_all_five_together():
    fac = _cap(["010", "014", "023", "024", "038"])
    assert all(fac.get(f) is True for f in EQ.values()), {f: fac.get(f) for f in EQ.values()}


def test_absence_does_not_generate_false():
    # 설비 미등록 → 해당 fact UNKNOWN(false 자동생성 안 함)
    fac = _cap([])
    for f in EQ.values():
        assert fac.get(f) is None, (f, fac.get(f))


def test_unknown_equipment_code_does_not_generate_fact():
    # 정본 5개 밖의 code → fact 생성 안 함
    fac = _cap(["999", "021"])
    for f in EQ.values():
        assert fac.get(f) is None


def test_no_factory_no_equipment_fact():
    # factory_id 없으면 equipment 조회 안 함
    cap = {}
    def r1(sb, s1): cap["s1"] = s1; return {"status": "success", "data": {"applicable_count": 0, "rules_table": []}}
    b = DiagnosisRunBody(auth_token="t", sector="CONSTRUCTION", disclaimer_log_id="disc1")
    _svc.run_diagnosis(_S(["010"]), b, run_step1_func=r1, auto_tier_func=lambda *a, **k: "CONSTRUCTION_X",
        build_partial_func=lambda f: {}, now_func=lambda: "2026-01-01T00:00:00Z", paid_tier_prices={},
        free_tier_codes={"CONSTRUCTION_FREE"}, engine_version="t", current_user=None)
    fac = build_facility(cap["s1"])
    assert fac.get("has_emergency_gen") is None
