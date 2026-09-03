"""WP1-CORRECTION-003 — run_diagnosis(실제 insert row capture) → upgrade_diagnosis 전체 round-trip.

CORRECTION-002 의 upgrade-only(직접 raw_structured_input 조립) 폐기.
run_diagnosis 실호출 → supabase insert 저장 row 캡처 → 그 row 그대로 upgrade_diagnosis
→ 최종 build_facility. RAW 값은 exact absence(키 부재)로 검증. source-grep 없음.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import services.diagnosis_integrated_svc as svc
from clients.leg_runtime_client import build_facility
from schemas.diagnosis_integrated import DiagnosisRunBody


class _Q:
    def __init__(s, store, table, sink):
        s.store = store; s.table = table; s.sink = sink; s._ins = None
    def select(s, *a, **k): return s
    def eq(s, *a, **k): return s
    def limit(s, *a, **k): return s
    def update(s, *a, **k): return s
    def insert(s, payload, *a, **k):
        s._ins = payload
        if s.table == "anonymous_diagnosis_results":
            s.sink["saved_row"] = payload
        return s
    def execute(s):
        class _R: pass
        r = _R()
        if s._ins is not None:
            row = dict(s._ins); row.setdefault("id", "NEWID")
            r.data = [row]
        else:
            r.data = s.store.get(s.table, [])
        return r
class _FakeSB:
    def __init__(s, store, sink): s.store = store; s.sink = sink
    def table(s, name): return _Q(s.store, name, s.sink)


def _run_full_roundtrip(form_data=None, raw_input=None):
    sink = {}; cap = {}
    def fake_run_step1(supabase, step1_body):
        cap["step1"] = step1_body
        return {"status": "success", "data": {"obligations": [], "diagnosis_id": "D"}}
    _orig = (svc.resolve_auth_log, svc._assert_linkable, svc._save_diagnosis_purchase,
             svc._bind_linked_user_id, svc._ensure_disclaimer_for_paid_entry)
    svc.resolve_auth_log = lambda sb, tok: {"id": "A1", "ci_hash": "CI", "free_count": 0, "free_limit": 3, "linked_user_id": None}
    svc._assert_linkable = lambda a, c: None
    svc._save_diagnosis_purchase = lambda *a, **k: None
    svc._bind_linked_user_id = lambda *a, **k: None
    svc._ensure_disclaimer_for_paid_entry = lambda sb, ar: "DISC1"
    try:
        store = {}; sb = _FakeSB(store, sink)
        # disclaimer_log_id 미지정 + payment_ref → _ensure_disclaimer_for_paid_entry(mock) 경로.
        body = DiagnosisRunBody(sector="BUILDING", auth_token="tok", payment_ref="PR",
                               input=(raw_input or {}), form_data=form_data)
        svc.run_diagnosis(supabase=sb, body=body, run_step1_func=fake_run_step1,
                          auto_tier_func=lambda *a, **k: "PAID2", build_partial_func=lambda x: {},
                          now_func=lambda: "2026-09-03T00:00:00",
                          paid_tier_prices={"PAID2": 149000, "PAID3": 249000},
                          free_tier_codes=set(), engine_version="v1",
                          current_user={"id": "U1", "ci_hash": "CI", "identity_verified": True, "identity_ci": "CI"})
        saved = sink.get("saved_row")
        assert saved is not None, "run_diagnosis insert row 미캡처"
        rec_input_data = saved["input_data"]
        store["anonymous_diagnosis_results"] = [{"id": "R1", "ci_hash": "CI", "tier_code": "PAID2",
                                                 "paid_amount": 149000, "status": "ACTIVE",
                                                 "input_data": rec_input_data}]
        class _UpBody:
            auth_token = "tok"; public_token = "PT"; target_tier_code = "PAID3"; payment_ref = "PR2"
        svc.upgrade_diagnosis(supabase=sb, body=_UpBody(), run_step1_func=fake_run_step1,
                              build_partial_func=lambda x: {},
                              paid_tier_prices={"PAID2": 149000, "PAID3": 249000},
                              current_user={"id": "U1", "ci_hash": "CI"},
                              now_func=lambda: "2026-09-03T00:00:00")
    finally:
        (svc.resolve_auth_log, svc._assert_linkable, svc._save_diagnosis_purchase,
         svc._bind_linked_user_id, svc._ensure_disclaimer_for_paid_entry) = _orig
    return build_facility(cap["step1"]), sink.get("saved_row")


def test_A_full_roundtrip_form_data():
    fac, saved = _run_full_roundtrip(form_data={"building_use_type": "오피스텔", "floor_count": 30,
                                                "total_floor_area": 300.0, "elevator_count": 0})
    assert saved["input_data"]["raw_structured_input"]["form_data"]["building_use_type"] == "오피스텔"
    assert fac.get("building_use_type") == "오피스텔"
    assert fac.get("floor_count") == 30
    assert fac.get("total_floor_area") == 300.0
    assert fac.get("has_building_elevator") is False

def test_B_raw_exact_absence():
    fac, saved = _run_full_roundtrip(form_data=None,
        raw_input={"building_use_type": "사무실", "floor_count": 50,
                   "total_floor_area": 9999.0, "elevator_count": 10})
    rsi = saved["input_data"].get("raw_structured_input", {})
    assert "form_data" not in rsi
    assert "building_use_type" not in fac
    assert "floor_count" not in fac
    assert "total_floor_area" not in fac
    assert "has_building_elevator" not in fac

def test_C_form_data_precedence():
    fac, _ = _run_full_roundtrip(form_data={"floor_count": 10}, raw_input={"floor_count": 50})
    assert fac.get("floor_count") == 10
    assert fac.get("floor_count") != 50
