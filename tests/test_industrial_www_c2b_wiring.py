"""WO-DUAL-IND-STEP2 GATE-2 C2b — WWW INDUSTRIAL canonical Step1 wired into LEG caller (run_diagnosis).
실제 caller(run_diagnosis) 경유 검증. C2a unit 재사용 아님 — factory→run_leg_diagnosis→build_facility 실 경로."""
import pytest
from services import diagnosis_integrated_svc as SVC
from services.diagnosis_helpers import _auto_tier
from services.canonical.industrial_www import build_industrial_www_step1
from clients import leg_runtime_client as legc
import services.leg_diagnosis_svc as legsvc

FREE = {"INDUSTRY_FREE", "BUILDING_FREE", "CONSTRUCTION_FREE"}
PRICES = {"INDUSTRY_V2": 79000, "BUILDING_V2": 99000, "CONSTRUCTION": 145000}

class _Res:
    def __init__(self, data): self.data = data
class _Q:
    def __init__(self, table): self._t = table; self._f = {}
    def select(self, *a, **k): return self
    def eq(self, c, v): self._f[c] = v; return self
    def limit(self, n): return self
    def update(self, *a, **k): return self
    def insert(self, payload): return self
    def execute(self):
        if self._t == "diagnosis_auth_log":
            return _Res([{"id": "AL1", "ci_hash": "H", "name": "n", "phone": "p",
                          "free_count": 0, "free_limit": 3, "status": "ACTIVE", "linked_user_id": None}])
        if self._t == "diagnosis_disclaimer_log":
            return _Res([{"id": "D1", "ci_hash": "H", "agreed": True}])
        if self._t == "anonymous_diagnosis_results":
            return _Res([{"id": "R1", "public_token": "tok"}])
        return _Res([])
class FakeSB:
    def table(self, name): return _Q(name)

class FakeBody:
    model_fields = {}
    def __init__(self, sector, form_data, auth_token="t"):
        self.sector = sector; self.form_data = form_data
        self.auth_token = auth_token; self.disclaimer_log_id = "D1"; self.payment_ref = None
    def __getattr__(self, name):
        return None

_ORIG_BF = legc.build_facility

def _drive(sector, form_data, factory, monkeypatch, auth_token="t", capture_facility=False):
    seen = {"factory": 0, "order": [], "step1": None, "facility": None}
    def spy_factory(body):
        seen["factory"] += 1; seen["order"].append("factory")
        return factory(body)
    def run_step1_func(supabase, step1_body):
        seen["step1"] = step1_body
        if capture_facility:
            seen["order"].append("run_leg_diagnosis")
            monkeypatch.setattr(legc, "LEG_RUNTIME_URL", "http://leg.test")
            def _eval(facility, *, timeout=None):
                seen["order"].append("evaluate_rtm"); seen["facility"] = facility
                return {"status": "OK", "obligations": [], "obligation_count": 0, "trace_id": "t"}
            monkeypatch.setattr(legc, "build_facility",
                                lambda s1b: (seen["order"].append("build_facility") or _ORIG_BF(s1b)))
            monkeypatch.setattr(legc, "evaluate_rtm", _eval)
            full = legsvc.run_leg_diagnosis(step1_body)
            return {"status": "success", "data": full}
        return {"status": "success", "data": {"sector": getattr(step1_body, "sector", None),
                "applicable_count": 0, "key_obligations": [], "applicable_laws": [], "law_badges": [],
                "rules": [], "risk_level": None, "summary": None}}
    out = SVC.run_diagnosis(
        supabase=FakeSB(), body=FakeBody(sector, form_data, auth_token=auth_token),
        run_step1_func=run_step1_func, auto_tier_func=_auto_tier, build_partial_func=lambda f: {"p": 1},
        now_func=lambda: "2026-01-01T00:00:00Z", paid_tier_prices=PRICES, free_tier_codes=FREE,
        engine_version="leg-runtime-v3", current_user=None, canonical_step1_factory_func=spy_factory)
    return out, seen

FD14 = {"ksic_major": "C25", "worker_count": 7, "total_floor_area": 5000, "building_use_type": "공장",
        "has_safety_manager": True, "has_boiler": False, "has_chemical_substance": True,
        "has_high_pressure_gas": True, "gas_capacity_kg": 120, "work_height_m": 3.5,
        "has_truck_loading_unloading": True, "truck_loading_height_m": 2.0,
        "has_manual_heavy_handling": True, "manual_handling_weight_kg": 25,
        "address": "서울", "floor_count": 3, "process_list": [{"process_name": "x"}]}

def test_C2b_01_industrial_factory_called_once(monkeypatch):
    _, seen = _drive("INDUSTRY", {"worker_count": 5}, build_industrial_www_step1, monkeypatch)
    assert seen["factory"] == 1
    assert seen["step1"].sector == "INDUSTRIAL"

def test_C2b_02_pipeline_order(monkeypatch):
    _, seen = _drive("INDUSTRY", FD14, build_industrial_www_step1, monkeypatch, capture_facility=True)
    assert seen["order"] == ["factory", "run_leg_diagnosis", "build_facility", "evaluate_rtm"]

def test_C2b_03_W1_total_floor_area_5000(monkeypatch):
    _, seen = _drive("INDUSTRY", {"total_floor_area": 5000}, build_industrial_www_step1, monkeypatch, capture_facility=True)
    assert seen["facility"]["total_floor_area"] == 5000 and seen["facility"]["total_floor_area"] != 400

def test_C2b_04_W2_has_chemical(monkeypatch):
    _, seen = _drive("INDUSTRY", {"has_chemical_substance": True}, build_industrial_www_step1, monkeypatch, capture_facility=True)
    assert seen["facility"].get("has_chemical") is True
    assert "has_chemical_substance" not in seen["facility"]

def test_C2b_05_leg_expected_14_14(monkeypatch):
    _, seen = _drive("INDUSTRY", FD14, build_industrial_www_step1, monkeypatch, capture_facility=True)
    exp = {"ksic_major": "C25", "worker_count": 7, "total_floor_area": 5000, "building_use_type": "공장",
           "has_safety_manager": True, "has_boiler": False, "has_chemical": True,
           "has_high_pressure_gas": True, "gas_capacity_kg": 120, "work_height_m": 3.5,
           "has_truck_loading_unloading": True, "truck_loading_height_m": 2.0,
           "has_manual_heavy_handling": True, "manual_handling_weight_kg": 25}
    assert len(exp) == 14
    for k, v in exp.items():
        assert seen["facility"][k] == v, f"{k}: {v!r} != {seen['facility'].get(k)!r}"
    for k in ("has_chemical_substance", "address", "floor_count", "process_list"):
        assert k not in seen["facility"]

def test_C2b_06_compiler_none_uses_legacy():
    seen = {}
    def run_step1_func(supabase, step1_body):
        seen["step1"] = step1_body
        return {"status": "success", "data": {}}
    SVC.run_diagnosis(supabase=FakeSB(), body=FakeBody("INDUSTRY", {"total_floor_area": 5000}),
                      run_step1_func=run_step1_func, auto_tier_func=_auto_tier, build_partial_func=lambda f: {},
                      now_func=lambda: "t", paid_tier_prices=PRICES, free_tier_codes=FREE,
                      engine_version="v", current_user=None, canonical_step1_factory_func=None)
    assert seen["step1"].sector == "MANUFACTURING"

@pytest.mark.parametrize("sector", ["BUILDING", "CONSTRUCTION"])
def test_C2b_07_non_industrial_factory_not_called(monkeypatch, sector):
    _, seen = _drive(sector, {"total_floor_area": 5000}, build_industrial_www_step1, monkeypatch)
    assert seen["factory"] == 0

def test_C2b_08_auth_failure_factory_not_called(monkeypatch):
    called = {"n": 0}
    def spy_factory(body):
        called["n"] += 1
        return build_industrial_www_step1(body)
    with pytest.raises(Exception):
        SVC.run_diagnosis(supabase=FakeSB(), body=FakeBody("INDUSTRY", {"worker_count": 5}, auth_token=""),
                          run_step1_func=lambda s, b: {"status": "success", "data": {}},
                          auto_tier_func=_auto_tier, build_partial_func=lambda f: {},
                          now_func=lambda: "t", paid_tier_prices=PRICES, free_tier_codes=FREE,
                          engine_version="v", current_user=None, canonical_step1_factory_func=spy_factory)
    assert called["n"] == 0
