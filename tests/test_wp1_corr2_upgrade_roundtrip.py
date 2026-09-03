"""WP1-CORRECTION-002 — RAW→CANONICAL firewall + 실제 upgrade round-trip (소스 grep 폐기)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import services.diagnosis_integrated_svc as svc
from clients.leg_runtime_client import build_facility


class _Q:
    def __init__(s, rows): s._rows = rows
    def select(s, *a, **k): return s
    def eq(s, *a, **k): return s
    def limit(s, *a, **k): return s
    def update(s, *a, **k): return s
    def insert(s, *a, **k): return s
    def execute(s):
        class _R: pass
        r = _R(); r.data = s._rows; return r
class _FakeSB:
    def __init__(s, rec): s._rec = rec
    def table(s, name):
        return _Q([s._rec]) if name == "anonymous_diagnosis_results" else _Q([])


def _run_upgrade(raw_structured_input, sector="BUILDING"):
    captured = {}
    def fake_run_step1(supabase, step1_body):
        captured["step1"] = step1_body
        return {"status": "success", "data": {"obligations": [], "diagnosis_id": "D-UP"}}
    _orig = (svc.resolve_auth_log, svc._assert_linkable, svc._save_diagnosis_purchase)
    svc.resolve_auth_log = lambda sb, tok: {"id": "A1", "ci_hash": "CI"}
    svc._assert_linkable = lambda auth_row, current: None
    svc._save_diagnosis_purchase = lambda *a, **k: None
    try:
        rec = {"id": "R1", "ci_hash": "CI", "tier_code": "PAID1", "paid_amount": 79000, "status": "PAID",
               "input_data": {"sector": sector, "tier_code": "PAID1", "floor_area": 400.0,
                              "contract_amount_eok": 1.0, "workers": 5,
                              "raw_structured_input": raw_structured_input}}
        sb = _FakeSB(rec)
        class _Body:
            auth_token = "tok"; public_token = "PT"; target_tier_code = "PAID3"; payment_ref = "PR"
        svc.upgrade_diagnosis(supabase=sb, body=_Body(), run_step1_func=fake_run_step1,
                              build_partial_func=lambda x: {},
                              paid_tier_prices={"PAID1": 79000, "PAID3": 249000},
                              current_user={"id": "U1", "ci_hash": "CI"},
                              now_func=lambda: "2026-09-03T00:00:00")
    finally:
        svc.resolve_auth_log, svc._assert_linkable, svc._save_diagnosis_purchase = _orig
    return build_facility(captured["step1"])


def test_CASE_A_form_data_roundtrip():
    fac = _run_upgrade({"form_data": {"building_use_type": "오피스텔", "floor_count": 30,
                                      "total_floor_area": 300.0, "elevator_count": 0}})
    assert fac.get("building_use_type") == "오피스텔"
    assert fac.get("floor_count") == 30
    assert fac.get("total_floor_area") == 300.0
    assert fac.get("has_building_elevator") is False

def test_CASE_B_raw_input_firewall():
    fac = _run_upgrade({"input": {"building_use_type": "사무실", "floor_count": 50,
                                  "total_floor_area": 9999.0, "elevator_count": 10}})
    assert fac.get("building_use_type") != "사무실"
    assert fac.get("floor_count") != 50
    assert fac.get("total_floor_area") != 9999.0
    assert "has_building_elevator" not in fac

def test_CASE_C_form_data_precedence():
    fac = _run_upgrade({"form_data": {"floor_count": 10}, "input": {"floor_count": 50}})
    assert fac.get("floor_count") == 10

def test_CASE_B2_empty_form_data_no_raw():
    fac = _run_upgrade({"form_data": {}, "input": {"floor_count": 77}})
    assert fac.get("floor_count") != 77
