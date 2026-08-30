# WO-FE-CST-GAP-IMPL-001 PHASE B MERGE-GATE-01 — CONSTRUCTION 11 coverage fact, REAL production path.
# 실제 run_diagnosis()를 Fake Supabase로 호출하고, run_step1_func 로 생성된 DiagnoseStep1Body 를 캡처해
# 실제 build_facility(captured) 를 호출한다. CODE-C1 로직을 test 에 복제하지 않는다(production 함수 관측).
#   DiagnosisRunBody.input → run_diagnosis → canonical_applicability → DiagnoseStep1Body.input → build_facility → RTM facility
from schemas.diagnosis_integrated import DiagnosisRunBody
from clients.leg_runtime_client import build_facility
from services import diagnosis_integrated_svc as _svc

CST11 = ["has_tower_crane", "has_subcontractor", "has_excavation", "has_demolition",
         "has_asbestos", "has_chemical_substance", "has_gas", "has_high_pressure_gas",
         "has_water_tank", "is_energy_intensive", "is_multi_use"]


class _FakeResult:
    def __init__(self, data): self.data = data


class _FakeTable:
    def __init__(self, name): self._name = name
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def update(self, *a, **k): return self
    def insert(self, row):
        self._pending = row
        return self
    def execute(self):
        if self._name == "diagnosis_auth_log":
            return _FakeResult([{"id": "a1", "ci_hash": "ci", "name": "n", "phone": "p",
                                 "free_count": 0, "free_limit": 3, "status": "ACTIVE", "linked_user_id": None}])
        if self._name == "diagnosis_disclaimer_log":
            return _FakeResult([{"id": "disc1", "ci_hash": "ci", "agreed": True}])
        if self._name == "anonymous_diagnosis_results":
            row = getattr(self, "_pending", None)
            return _FakeResult([{**(row or {}), "id": "r1"}])
        return _FakeResult([])


class _FakeSupabase:
    def table(self, name): return _FakeTable(name)


def _run_and_capture(body):
    """실제 run_diagnosis 를 돌려 생성된 DiagnoseStep1Body 를 캡처 → 실제 build_facility 호출."""
    captured = {}

    def _run_step1(supabase, step1_body):
        captured["s1"] = step1_body
        return {"status": "success", "data": {"applicable_count": 0, "rules_table": []}}

    _svc.run_diagnosis(
        _FakeSupabase(), body,
        run_step1_func=_run_step1,
        auto_tier_func=lambda sector, floor_area, contract_amount_eok, user_tier: "CONSTRUCTION_X",
        build_partial_func=lambda full: {},
        now_func=lambda: "2026-01-01T00:00:00Z",
        paid_tier_prices={},
        free_tier_codes={"CONSTRUCTION_FREE", "INDUSTRY_FREE", "BUILDING_FREE"},  # payment_ref 없음 → sector별 FREE 확정
        engine_version="test",
        current_user=None,
    )
    return build_facility(captured["s1"])


def _cst_body(**kw):
    return DiagnosisRunBody(auth_token="t", sector="CONSTRUCTION", disclaimer_log_id="disc1", **kw)


def test_t1_11_raw_true_real_path():
    fac = _run_and_capture(_cst_body(input={c: True for c in CST11}))
    assert all(fac.get(c) is True for c in CST11)


def test_t2_11_raw_false_real_path():
    fac = _run_and_capture(_cst_body(input={c: False for c in CST11}))
    assert all(fac.get(c) is False for c in CST11)  # false != absent


def test_t3_has_gas_nested_only():
    assert _run_and_capture(_cst_body(input={"has_gas": True})).get("has_gas") is True


def test_t4_has_high_pressure_gas_nested_only():
    assert _run_and_capture(_cst_body(input={"has_high_pressure_gas": True})).get("has_high_pressure_gas") is True


def test_t5_is_multi_use_nested_only():
    assert _run_and_capture(_cst_body(input={"is_multi_use": True})).get("is_multi_use") is True


def test_t6_chemical_nested_only_exact_name():
    fac = _run_and_capture(_cst_body(input={"has_chemical_substance": True}))
    assert fac.get("has_chemical_substance") is True and "has_chemical" not in fac


def test_t7_top_level_false_precedence():
    # top-level explicit False + nested True → final False (explicit 우선)
    fac = _run_and_capture(_cst_body(has_gas=False, input={"has_gas": True}))
    assert fac.get("has_gas") is False


def test_t8_industrial_firewall():
    fac = _run_and_capture(DiagnosisRunBody(auth_token="t", sector="INDUSTRIAL", disclaimer_log_id="disc1",
                                            input={"has_gas": True, "has_chemical_substance": True}))
    # INDUSTRIAL paid nested 미경유 → has_gas/has_chemical_substance materialize 안 됨
    assert "has_gas" not in fac and "has_chemical_substance" not in fac


def test_t9_building_firewall():
    fac = _run_and_capture(DiagnosisRunBody(auth_token="t", sector="BUILDING", disclaimer_log_id="disc1",
                                            input={"has_gas": True}))
    assert "has_gas" not in fac


def test_t10_non_target_not_opened():
    fac = _run_and_capture(_cst_body(input={"has_welding": True, "has_forklift": True}))
    assert "has_welding" not in fac and "has_forklift" not in fac
