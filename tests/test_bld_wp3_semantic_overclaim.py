"""WP-3 SEMANTIC OVERCLAIM — generic gas/chemical 이 specific 축으로 승격되지 않음.

LIVE: DiagnosisRunBody → run_diagnosis → DiagnoseStep1Body → build_facility → facility
UPGRADE: saved form_data → upgrade_diagnosis → build_facility → facility
ABSENCE: "key" not in facility 만 사용 (facility.get(key) is None 금지).
source-grep 없음. supabase/auth mock, step1→build_facility 실실행.
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


class _UpBody:
    auth_token = "tok"; public_token = "PT"; target_tier_code = "PAID3"; payment_ref = "PR2"


_PAID = {"PAID2": 149000, "PAID3": 249000}


def _patch_auth():
    orig = (svc.resolve_auth_log, svc._assert_linkable, svc._save_diagnosis_purchase,
            svc._bind_linked_user_id, svc._ensure_disclaimer_for_paid_entry)
    svc.resolve_auth_log = lambda sb, tok: {"id": "A1", "ci_hash": "CI", "free_count": 0, "free_limit": 3, "linked_user_id": None}
    svc._assert_linkable = lambda a, c: None
    svc._save_diagnosis_purchase = lambda *a, **k: None
    svc._bind_linked_user_id = lambda *a, **k: None
    svc._ensure_disclaimer_for_paid_entry = lambda sb, ar: "DISC1"
    return orig


def _restore_auth(orig):
    (svc.resolve_auth_log, svc._assert_linkable, svc._save_diagnosis_purchase,
     svc._bind_linked_user_id, svc._ensure_disclaimer_for_paid_entry) = orig


def _run_live(**fields):
    """DiagnosisRunBody top-level → run_diagnosis → real DiagnoseStep1Body → build_facility."""
    cap = {}
    def fake_run_step1(supabase, step1_body):
        cap["step1"] = step1_body
        return {"status": "success", "data": {"obligations": [], "diagnosis_id": "D"}}
    orig = _patch_auth()
    try:
        sink = {}; sb = _FakeSB({}, sink)
        body = DiagnosisRunBody(sector="BUILDING", auth_token="tok", payment_ref="PR", **fields)
        svc.run_diagnosis(supabase=sb, body=body, run_step1_func=fake_run_step1,
                          auto_tier_func=lambda *a, **k: "PAID2", build_partial_func=lambda x: {},
                          now_func=lambda: "2026-09-04T00:00:00",
                          paid_tier_prices=_PAID, free_tier_codes=set(), engine_version="v1",
                          current_user={"id": "U1", "ci_hash": "CI", "identity_verified": True, "identity_ci": "CI"})
    finally:
        _restore_auth(orig)
    assert "step1" in cap, "run_diagnosis DiagnoseStep1Body 미캡처"
    return build_facility(cap["step1"])


def _run_upgrade(form_data):
    """saved form_data → upgrade_diagnosis → real DiagnoseStep1Body → build_facility.

    run_diagnosis 로 form_data 를 실제 저장한 뒤 그 row 로 upgrade 한다
    (upgrade production 무수정, 저장 경로 실실행).
    """
    cap = {}
    def fake_run_step1(supabase, step1_body):
        cap["step1"] = step1_body
        return {"status": "success", "data": {"obligations": [], "diagnosis_id": "D"}}
    orig = _patch_auth()
    try:
        sink = {}; store = {}; sb = _FakeSB(store, sink)
        body = DiagnosisRunBody(sector="BUILDING", auth_token="tok", payment_ref="PR",
                                form_data=form_data)
        svc.run_diagnosis(supabase=sb, body=body, run_step1_func=fake_run_step1,
                          auto_tier_func=lambda *a, **k: "PAID2", build_partial_func=lambda x: {},
                          now_func=lambda: "2026-09-04T00:00:00",
                          paid_tier_prices=_PAID, free_tier_codes=set(), engine_version="v1",
                          current_user={"id": "U1", "ci_hash": "CI", "identity_verified": True, "identity_ci": "CI"})
        saved = sink.get("saved_row")
        assert saved is not None, "run_diagnosis insert row 미캡처"
        store["anonymous_diagnosis_results"] = [{"id": "R1", "ci_hash": "CI", "tier_code": "PAID2",
                                                 "paid_amount": 149000, "status": "ACTIVE",
                                                 "input_data": saved["input_data"]}]
        svc.upgrade_diagnosis(supabase=sb, body=_UpBody(), run_step1_func=fake_run_step1,
                              build_partial_func=lambda x: {}, paid_tier_prices=_PAID,
                              current_user={"id": "U1", "ci_hash": "CI"},
                              now_func=lambda: "2026-09-04T00:00:00")
    finally:
        _restore_auth(orig)
    assert "step1" in cap, "upgrade_diagnosis DiagnoseStep1Body 미캡처"
    return build_facility(cap["step1"])


# ── LIVE G1–G3 / C1–C3 ──────────────────────────────────────────────────────
def test_G1_has_gas_true_high_pressure_absent():
    fac = _run_live(has_gas=True)
    assert fac["has_gas"] is True
    assert "has_high_pressure_gas" not in fac


def test_G2_has_gas_and_high_pressure_true():
    fac = _run_live(has_gas=True, has_high_pressure_gas=True)
    assert fac["has_gas"] is True
    assert fac["has_high_pressure_gas"] is True


def test_G3_has_gas_false_high_pressure_absent():
    fac = _run_live(has_gas=False)
    assert fac["has_gas"] is False
    assert "has_high_pressure_gas" not in fac


def test_C1_has_chemical_true_hazardous_absent():
    fac = _run_live(has_chemical=True)
    assert fac["has_chemical"] is True
    assert "has_hazardous_material" not in fac


def test_C2_has_chemical_and_hazardous_true():
    fac = _run_live(has_chemical=True, has_hazardous_material=True)
    assert fac["has_chemical"] is True
    assert fac["has_hazardous_material"] is True


def test_C3_has_chemical_false_hazardous_absent():
    fac = _run_live(has_chemical=False)
    assert fac["has_chemical"] is False
    assert "has_hazardous_material" not in fac


# ── UPGRADE UP-G1/G2 / UP-C1/C2 ─────────────────────────────────────────────
def test_UP_G1_saved_high_pressure_true():
    fac = _run_upgrade({"has_high_pressure_gas": True})
    assert fac["has_high_pressure_gas"] is True


def test_UP_G2_saved_has_gas_high_pressure_absent():
    fac = _run_upgrade({"has_gas": True})
    assert fac["has_gas"] is True
    assert "has_high_pressure_gas" not in fac


def test_UP_C1_saved_hazardous_true():
    fac = _run_upgrade({"has_hazardous_material": True})
    assert fac["has_hazardous_material"] is True


def test_UP_C2_saved_has_chemical_hazardous_absent():
    fac = _run_upgrade({"has_chemical": True})
    assert fac["has_chemical"] is True
    assert "has_hazardous_material" not in fac
