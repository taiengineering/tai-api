"""WO-MATERIAL-PAID-PERSISTENT-EXISTING-SEAM-PATCH-001 — Paid persistent Material seam 검증.

Coverage:
  MAT-BLD    Paid BUILDING run_diagnosis() → persistent MANAGED → is_managed_hazardous_substance=True
  MAT-IND    Paid INDUSTRIAL run_diagnosis() → engine_sector=MANUFACTURING → is_permit_required_hazardous_substance=True
  MAT-CST    Paid CONSTRUCTION run_diagnosis() → persistent SPECIAL(BENZENE) → is_managed_hazardous_substance=True
  FC001-T    Paid persistent row MANAGED+INDOOR_HANDLING → fc001_managed_indoor_handling=True
  FC001-F    Paid persistent row MANAGED+other mode only → fc001_managed_indoor_handling=False
  FC001-U    Paid persistent row MANAGED, handling_mode_codes=None → fc001_managed_indoor_handling ABSENT
  CONF-409   explicit is_managed=False + persistent MANAGED=True → HTTPException 409 / step1=0
  SAME-VAL   explicit is_managed=True + persistent MANAGED=True → PASS / step1=1
  OWN-1      Paid BUILDING → _ensure_factory_own exactly 1 call (not doubled)
  FREE-FW    is_free=True → load_factory_material_rows_optional calls=0
  NO-FAC     paid, factory_id=None → persistent Material read=0
  MAT-503    MaterialSourceLoadError → HTTPException 503 / step1=0
  CAT-503    catalog/projector generic error → HTTPException 503 / step1=0
  TRANS-REG  transient body.material_rows still wired (existing contract preserved)
  UNION      persistent MANAGED + transient PERMIT → both True in step1.input
  EQ-REG     Equipment A2 seam unaffected (023 → has_press=True co-exists)
"""
from __future__ import annotations

from typing import Any, Dict
import pytest

import services.diagnosis_integrated_svc as _svc
from schemas.diagnosis_integrated import DiagnosisRunBody
from fastapi import HTTPException

# ── Material fixture keys (authority: catalog) ────────────────────────────────
BENZENE_KEY = "ISHL-RULE-APP12-G1-I046"    # MANAGED + SPECIAL
VINYL_KEY   = "ISHL-ENF-ART88-0088001-P-H7"  # PERMIT only
STODDARD_KEY = "ISHL-RULE-APP12-G1-I060"   # MANAGED only


# ── Fake Supabase helpers ─────────────────────────────────────────────────────

class _Res:
    def __init__(self, data): self.data = data


class _AnyQ:
    """Universal fake query chain — all verbs return self, execute returns rows."""
    def __init__(self, rows): self._rows = rows
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def order(self, *a, **k): return self
    def update(self, *a, **k): return self
    def insert(self, *a, **k): return self
    def execute(self): return _Res(self._rows)


def _mat_row(key: str, handling_mode_codes=None, is_active: bool = True) -> dict:
    return {
        "id": "M1", "factory_id": "F1",
        "material_name": "test-material",
        "material_category_code": None,
        "material_master_key": key,
        "handling_mode_codes": handling_mode_codes,
        "is_active": is_active,
        "created_at": "2026-01-01T00:00:00",
    }


class _PaidMatFakeSB:
    """Fake SB for paid persistent Material integration tests."""
    def __init__(self, mat_rows: list, eq_rows: list = None):
        self._mat = mat_rows
        self._eq = eq_rows or []

    def table(self, name: str):
        if name == "diagnosis_disclaimer_log":
            return _AnyQ([{"id": "DL1", "ci_hash": "H1", "agreed": True}])
        if name == "factory_materials":
            return _AnyQ(self._mat)
        if name == "equipment_assets":
            return _AnyQ(self._eq)
        if name == "anonymous_diagnosis_results":
            return _AnyQ([{"id": "DIAG1", "public_token": "PT1"}])
        return _AnyQ([])


# ── Patch helpers ─────────────────────────────────────────────────────────────

def _patch_svc(monkeypatch):
    """Patch all non-material svc dependencies for run_diagnosis integration."""
    monkeypatch.setattr(_svc, "resolve_auth_log",
        lambda sb, tok: {"id": "AL1", "ci_hash": "H1", "free_count": 0, "free_limit": 3, "status": "ACTIVE"})
    monkeypatch.setattr(_svc, "validate_explicit_construction_predicates", lambda body, sector: None)
    monkeypatch.setattr(_svc, "validate_explicit_appendix3_classification", lambda body, sector: None)
    monkeypatch.setattr(_svc, "prepare_available_and_projection", lambda body, avail: ({}, {}))
    monkeypatch.setattr(_svc, "merge_projection_after_canonical", lambda inp, canon, proj: None)
    monkeypatch.setattr(_svc, "_assert_linkable", lambda auth_row, cu: None)
    monkeypatch.setattr(_svc, "_save_diagnosis_purchase", lambda sb, **kw: None)
    monkeypatch.setattr(_svc, "_bind_linked_user_id", lambda sb, ar, cu, now: None)
    monkeypatch.setattr(_svc, "collect_explicit_construction_predicates", lambda body: {})
    monkeypatch.setattr(_svc, "persist_explicit_appendix3_source", lambda src: {})
    monkeypatch.setattr(_svc, "sanitize_form_data_for_persist", lambda fd, src: fd)
    monkeypatch.setattr("services.company_scope._ensure_factory_own", lambda sb, fid, cu: None)
    monkeypatch.setattr("services.work_source.store.load_work_rows_optional", lambda sb, fid: [])
    monkeypatch.setattr("services.equipment_source.store.load_equipment_rows_optional", lambda sb, fid: [])
    monkeypatch.setattr("services.canonical.materialization.canonical_applicability", lambda avail: {})


def _diag_body(sector: str, **kwargs) -> DiagnosisRunBody:
    return DiagnosisRunBody(
        auth_token="tok",
        sector=sector,
        factory_id="F1",
        disclaimer_log_id="DL1",
        payment_ref="PAY1",
        worker_count=5,
        **kwargs,
    )


def _run_diag(sb, body, fake_step1):
    return _svc.run_diagnosis(
        sb, body,
        run_step1_func=fake_step1,
        auto_tier_func=lambda s, **kw: "PAID_TIER",
        build_partial_func=lambda r: {},
        now_func=lambda: "2026-01-01T00:00:00",
        paid_tier_prices={"PAID_TIER": 10000},
        free_tier_codes=set(),
        engine_version="v5.10",
        current_user={"user_id": "u1"},
    )


def _capture_step1(sb, body):
    cap: dict = {}
    def fake_step1(sb, s1b): cap["inp"] = dict(s1b.input or {}); return {"status": "success", "data": {}}
    _run_diag(sb, body, fake_step1)
    return cap.get("inp", {})


# ── MAT-BLD~CST: Paid 3-sector persistent Material transport ─────────────────

def test_MAT_BLD_managed_canonical(monkeypatch):
    """MAT-BLD: Paid BUILDING run_diagnosis() → STODDARD(MANAGED) → is_managed_hazardous_substance=True."""
    _patch_svc(monkeypatch)
    sb = _PaidMatFakeSB([_mat_row(STODDARD_KEY, is_active=True)])
    inp = _capture_step1(sb, _diag_body("BUILDING"))
    assert inp.get("is_managed_hazardous_substance") is True, (
        f"BUILDING paid: expected is_managed_hazardous_substance=True; got {inp.get('is_managed_hazardous_substance')!r}"
    )


def test_MAT_IND_permit_canonical(monkeypatch):
    """MAT-IND: Paid INDUSTRIAL(→MANUFACTURING) → VINYL(PERMIT) → is_permit_required_hazardous_substance=True."""
    _patch_svc(monkeypatch)
    sb = _PaidMatFakeSB([_mat_row(VINYL_KEY, is_active=True)])
    inp = _capture_step1(sb, _diag_body("INDUSTRIAL"))
    assert inp.get("is_permit_required_hazardous_substance") is True, (
        f"INDUSTRIAL paid: expected is_permit_required_hazardous_substance=True; got {inp.get('is_permit_required_hazardous_substance')!r}"
    )


def test_MAT_CST_special_canonical(monkeypatch):
    """MAT-CST: Paid CONSTRUCTION → BENZENE(MANAGED+SPECIAL) → is_managed + is_special both True."""
    _patch_svc(monkeypatch)
    sb = _PaidMatFakeSB([_mat_row(BENZENE_KEY, is_active=True)])
    inp = _capture_step1(sb, _diag_body("CONSTRUCTION"))
    assert inp.get("is_managed_hazardous_substance") is True, (
        f"CONSTRUCTION paid: expected is_managed_hazardous_substance=True; got {inp.get('is_managed_hazardous_substance')!r}"
    )
    assert inp.get("is_special_management_substance") is True, (
        f"CONSTRUCTION paid: expected is_special_management_substance=True; got {inp.get('is_special_management_substance')!r}"
    )


# ── FC001-T/F/U: FC-001 tri-state transport ───────────────────────────────────

def test_FC001_TRUE_indoor_handling(monkeypatch):
    """FC001-T: MANAGED row with INDOOR_HANDLING → fc001_managed_indoor_handling=True in step1.input."""
    _patch_svc(monkeypatch)
    sb = _PaidMatFakeSB([_mat_row(STODDARD_KEY, handling_mode_codes=["INDOOR_HANDLING"])])
    inp = _capture_step1(sb, _diag_body("BUILDING"))
    assert inp.get("fc001_managed_indoor_handling") is True, (
        f"FC001-T: expected fc001_managed_indoor_handling=True; got {inp.get('fc001_managed_indoor_handling')!r}"
    )


def test_FC001_FALSE_other_mode_only(monkeypatch):
    """FC001-F: MANAGED row with only MANUFACTURE_OR_USE → fc001_managed_indoor_handling=False."""
    _patch_svc(monkeypatch)
    sb = _PaidMatFakeSB([_mat_row(STODDARD_KEY, handling_mode_codes=["MANUFACTURE_OR_USE"])])
    inp = _capture_step1(sb, _diag_body("BUILDING"))
    assert inp.get("fc001_managed_indoor_handling") is False, (
        f"FC001-F: expected fc001_managed_indoor_handling=False; got {inp.get('fc001_managed_indoor_handling')!r}"
    )


def test_FC001_UNKNOWN_null_handling_mode(monkeypatch):
    """FC001-U: MANAGED row with handling_mode_codes=None → fc001_managed_indoor_handling ABSENT (Missing != False)."""
    _patch_svc(monkeypatch)
    sb = _PaidMatFakeSB([_mat_row(STODDARD_KEY, handling_mode_codes=None)])
    inp = _capture_step1(sb, _diag_body("BUILDING"))
    assert "fc001_managed_indoor_handling" not in inp, (
        f"FC001-U: fc001_managed_indoor_handling must be ABSENT (UNKNOWN); got {inp.get('fc001_managed_indoor_handling')!r}"
    )


# ── CONF-409: Explicit False + persistent True → 409 ─────────────────────────

def test_CONF_409_explicit_false_persistent_managed(monkeypatch):
    """CONF-409: explicit is_managed=False + persistent MANAGED=True → HTTPException 409, step1=0."""
    _patch_svc(monkeypatch)
    # merge_projection_after_canonical injects explicit False into inp before Material projector.
    monkeypatch.setattr(_svc, "merge_projection_after_canonical",
                        lambda inp, canon, proj: inp.update({"is_managed_hazardous_substance": False}))
    sb = _PaidMatFakeSB([_mat_row(STODDARD_KEY, is_active=True)])
    step1_calls: list = []
    def fake_step1(sb, s1b): step1_calls.append(1); return {"status": "success", "data": {}}
    with pytest.raises(HTTPException) as exc_info:
        _run_diag(sb, _diag_body("BUILDING"), fake_step1)
    assert exc_info.value.status_code == 409, (
        f"CONF-409: expected 409; got {exc_info.value.status_code}"
    )
    assert exc_info.value.detail.get("code") == "MATERIAL_CANONICAL_CONFLICT", (
        f"CONF-409: expected MATERIAL_CANONICAL_CONFLICT code; got {exc_info.value.detail}"
    )
    assert step1_calls == [], f"run_step1_func must not be called on conflict; got {step1_calls}"


# ── SAME-VAL: Explicit True + persistent True → PASS ─────────────────────────

def test_SAME_VAL_no_conflict(monkeypatch):
    """SAME-VAL: explicit is_managed=True + persistent MANAGED=True → PASS, step1 called once."""
    _patch_svc(monkeypatch)
    monkeypatch.setattr(_svc, "merge_projection_after_canonical",
                        lambda inp, canon, proj: inp.update({"is_managed_hazardous_substance": True}))
    sb = _PaidMatFakeSB([_mat_row(STODDARD_KEY, is_active=True)])
    step1_calls: list = []
    def fake_step1(sb, s1b): step1_calls.append(1); return {"status": "success", "data": {}}
    _run_diag(sb, _diag_body("BUILDING"), fake_step1)
    assert step1_calls == [1], f"SAME-VAL: run_step1_func must be called once; got {step1_calls}"


# ── OWN-1: ownership exactly once ────────────────────────────────────────────

def test_OWN_1_ownership_not_doubled(monkeypatch):
    """OWN-1: Paid BUILDING → _ensure_factory_own called exactly once (Material doesn't add a second call)."""
    _patch_svc(monkeypatch)
    calls: list = []
    monkeypatch.setattr("services.company_scope._ensure_factory_own",
                        lambda sb, fid, cu: calls.append(fid))
    sb = _PaidMatFakeSB([])
    def fake_step1(sb, s1b): return {"status": "success", "data": {}}
    _run_diag(sb, _diag_body("BUILDING"), fake_step1)
    assert calls == ["F1"], f"OWN-1: expected exactly 1 ownership call; got {calls}"


# ── FREE-FW: is_free → no persistent Material read ───────────────────────────

def test_FREE_FW_no_persistent_read(monkeypatch):
    """FREE-FW: is_free=True → load_factory_material_rows_optional never called."""
    _patch_svc(monkeypatch)
    mat_calls: list = []
    monkeypatch.setattr(
        "services.material_source.store.load_factory_material_rows_optional",
        lambda sb, fid: mat_calls.append(fid) or [],
    )
    sb = _PaidMatFakeSB([])
    def fake_step1(sb, s1b): return {"status": "success", "data": {}}
    # free_tier_codes includes the tier so is_free=True
    _svc.run_diagnosis(
        sb, _diag_body("BUILDING"),
        run_step1_func=fake_step1,
        auto_tier_func=lambda s, **kw: "FREE_TIER",
        build_partial_func=lambda r: {},
        now_func=lambda: "2026-01-01T00:00:00",
        paid_tier_prices={},
        free_tier_codes={"FREE_TIER"},
        engine_version="v5.10",
        current_user=None,
    )
    assert mat_calls == [], f"FREE-FW: persistent Material must not be read for free path; got {mat_calls}"


# ── NO-FAC: no factory_id → no persistent read ───────────────────────────────

def test_NO_FAC_no_factory_no_persistent_read(monkeypatch):
    """NO-FAC: paid, factory_id=None → load_factory_material_rows_optional not called."""
    _patch_svc(monkeypatch)
    mat_calls: list = []
    monkeypatch.setattr(
        "services.material_source.store.load_factory_material_rows_optional",
        lambda sb, fid: mat_calls.append(fid) or [],
    )
    sb = _PaidMatFakeSB([])
    body = DiagnosisRunBody(
        auth_token="tok",
        sector="BUILDING",
        factory_id=None,
        disclaimer_log_id="DL1",
        payment_ref="PAY1",
        worker_count=5,
    )
    def fake_step1(sb, s1b): return {"status": "success", "data": {}}
    _run_diag(sb, body, fake_step1)
    assert mat_calls == [], f"NO-FAC: persistent Material must not be read without factory_id; got {mat_calls}"


# ── MAT-503: MaterialSourceLoadError → HTTPException 503 ─────────────────────

def test_MAT_503_read_failure_http(monkeypatch):
    """MAT-503: MaterialSourceLoadError → HTTPException 503 / MATERIAL_SOURCE_UNAVAILABLE / step1=0."""
    from services.material_source.store import MaterialSourceLoadError
    _patch_svc(monkeypatch)
    monkeypatch.setattr(
        "services.material_source.store.load_factory_material_rows_optional",
        lambda sb, fid: (_ for _ in ()).throw(MaterialSourceLoadError("injected", factory_id=fid)),
    )
    step1_calls: list = []
    def fake_step1(sb, s1b): step1_calls.append(1); return {"status": "success", "data": {}}
    sb = _PaidMatFakeSB([])
    with pytest.raises(HTTPException) as exc_info:
        _run_diag(sb, _diag_body("BUILDING"), fake_step1)
    assert exc_info.value.status_code == 503, (
        f"MAT-503: expected 503; got {exc_info.value.status_code}"
    )
    assert exc_info.value.detail.get("code") == "MATERIAL_SOURCE_UNAVAILABLE"
    assert step1_calls == [], f"run_step1_func must not be called on read failure; got {step1_calls}"


# ── CAT-503: catalog/projector error → HTTPException 503 ─────────────────────

def test_CAT_503_projector_failure_http(monkeypatch):
    """CAT-503: catalog/projector generic error → HTTPException 503, step1=0."""
    _patch_svc(monkeypatch)
    # Return a non-empty row list but make the projector raise a generic error.
    sb = _PaidMatFakeSB([_mat_row(STODDARD_KEY)])
    monkeypatch.setattr(
        "services.material_source.canonical_adapter.project_material_canonical_facts_from_rows",
        lambda rows, **kw: (_ for _ in ()).throw(RuntimeError("catalog load failed")),
    )
    step1_calls: list = []
    def fake_step1(sb, s1b): step1_calls.append(1); return {"status": "success", "data": {}}
    with pytest.raises(HTTPException) as exc_info:
        _run_diag(sb, _diag_body("BUILDING"), fake_step1)
    assert exc_info.value.status_code == 503, (
        f"CAT-503: expected 503; got {exc_info.value.status_code}"
    )
    assert exc_info.value.detail.get("code") == "MATERIAL_SOURCE_UNAVAILABLE"
    assert step1_calls == [], f"run_step1_func must not be called on projector failure; got {step1_calls}"


# ── TRANS-REG: transient body.material_rows still works ──────────────────────

def test_TRANS_REG_transient_material_still_wired(monkeypatch):
    """TRANS-REG: existing transient body.material_rows path unaffected by persistent addition."""
    _patch_svc(monkeypatch)
    # No persistent rows, but transient VINYL(PERMIT) via body.material_rows
    sb = _PaidMatFakeSB([])
    body = DiagnosisRunBody(
        auth_token="tok",
        sector="BUILDING",
        factory_id="F1",
        disclaimer_log_id="DL1",
        payment_ref="PAY1",
        worker_count=5,
        material_rows=[{
            "material_master_key": VINYL_KEY,
            "handling_mode_codes": None,
            "is_active": True,
        }],
    )
    inp = _capture_step1(sb, body)
    assert inp.get("is_permit_required_hazardous_substance") is True, (
        f"TRANS-REG: expected is_permit_required=True from transient; got {inp.get('is_permit_required_hazardous_substance')!r}"
    )


# ── UNION: persistent + transient union ──────────────────────────────────────

def test_UNION_persistent_plus_transient(monkeypatch):
    """UNION: persistent MANAGED(STODDARD) + transient PERMIT(VINYL) → both canonical facts True."""
    _patch_svc(monkeypatch)
    sb = _PaidMatFakeSB([_mat_row(STODDARD_KEY, is_active=True)])
    body = DiagnosisRunBody(
        auth_token="tok",
        sector="BUILDING",
        factory_id="F1",
        disclaimer_log_id="DL1",
        payment_ref="PAY1",
        worker_count=5,
        material_rows=[{
            "material_master_key": VINYL_KEY,
            "handling_mode_codes": None,
            "is_active": True,
        }],
    )
    inp = _capture_step1(sb, body)
    assert inp.get("is_managed_hazardous_substance") is True, (
        f"UNION: expected is_managed=True (persistent); got {inp.get('is_managed_hazardous_substance')!r}"
    )
    assert inp.get("is_permit_required_hazardous_substance") is True, (
        f"UNION: expected is_permit=True (transient); got {inp.get('is_permit_required_hazardous_substance')!r}"
    )


# ── EQ-REG: Equipment A2 seam unaffected ─────────────────────────────────────

def test_EQ_REG_equipment_coexists_with_material(monkeypatch):
    """EQ-REG: persistent Material patch doesn't break Equipment A2 (023 → has_press=True co-exists)."""
    _patch_svc(monkeypatch)
    # Restore real equipment loader to test co-existence
    monkeypatch.setattr(
        "services.equipment_source.store.load_equipment_rows_optional",
        lambda sb, fid: [{"equipment_type_code": "023", "is_operating": True}],
    )
    sb = _PaidMatFakeSB([_mat_row(STODDARD_KEY, is_active=True)])
    inp = _capture_step1(sb, _diag_body("BUILDING"))
    assert inp.get("has_press") is True, (
        f"EQ-REG: expected has_press=True (Equipment A2); got {inp.get('has_press')!r}"
    )
    assert inp.get("is_managed_hazardous_substance") is True, (
        f"EQ-REG: expected is_managed=True (Material); got {inp.get('is_managed_hazardous_substance')!r}"
    )
