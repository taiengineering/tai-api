"""WO-EQUIPMENT-A2-REMAINING-CONSUMER-PARITY-IMPLEMENT-001 — 잔여 consumer parity 검증.

Coverage:
  BLD-01~05      BUILDING official 5-code transport (010/014/023/024/038)
  BLD-06         BUILDING has_boiler=False + equipment 014 → exactly False
  BLD-07         BUILDING factories.has_boiler absent + equipment 014 → True
  BLD-08         BUILDING router EquipmentSourceLoadError → HTTP 503 / LEG 0
  CST-01~05      CONSTRUCTION official 5-code transport
  CST-06         CONSTRUCTION router EquipmentSourceLoadError → HTTP 503 / LEG 0
  PAID-01        Paid BUILDING persistent Equipment: 023 → has_press=True
  PAID-02        Paid INDUSTRIAL persistent Equipment: 023 → has_press=True
  PAID-03        Paid CONSTRUCTION persistent Equipment regression: 023 → has_press=True
  CRANE-01       021 / CRANE → has_crane 미발생 (BUILDING/CONSTRUCTION 공통)
  PATCH1-A-BLD   run_diagnosis BUILDING paid → gate 통과 → has_press=True
  PATCH1-A-IND   run_diagnosis INDUSTRIAL paid → engine_sector=MANUFACTURING → has_conveyor=True
  PATCH1-A-CST   run_diagnosis CONSTRUCTION paid → gate 통과 → has_pressure_vessel=True
  PATCH1-A-EXF   run_diagnosis explicit has_press=False + 023 → setdefault 보존 (False 유지)
  PATCH1-A-OWN   run_diagnosis BUILDING paid → _ensure_factory_own 1회 호출 증명
  PATCH1-A-503   run_diagnosis equipment read fail → HTTPException 503 / step1 0호출
  PATCH1-B-BLD   run_safe_building_leg equipment read fail → EquipmentSourceLoadError / LEG 0
  PATCH1-B-CST   run_safe_construction_leg equipment read fail → EquipmentSourceLoadError / LEG 0
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import pytest

import services.safe_building_leg_runtime as bld_rt
from services.safe_building_leg_runtime import run_safe_building_leg
import services.safe_construction_leg_runtime as cst_rt
from services.safe_construction_leg_runtime import run_safe_construction_leg
from services.equipment_source.store import EquipmentSourceLoadError
from schemas.legal_engine import SafeBuildingConsumerInput, SafeConstructionConsumerInput


# ── Fake Supabase helpers ─────────────────────────────────────────────────────

class _Res:
    def __init__(self, data): self.data = data


class _Q:
    def __init__(self, rows): self._rows = rows

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def order(self, *a, **k): return self
    def execute(self): return _Res(self._rows)


class _FakeSBBuilding:
    """Fake SB for BUILDING runtime tests. Handles factories + equipment_assets."""

    def __init__(self, fac_row: dict, eq_rows: list):
        self._fac = fac_row
        self._eq = eq_rows

    def table(self, name):
        if name == "factories":
            return _Q([self._fac] if self._fac else [])
        if name == "equipment_assets":
            return _Q(self._eq)
        return _Q([])


class _FakeSBConstruction:
    """Fake SB for CONSTRUCTION runtime tests (site + factory_work_facts + equipment)."""

    def __init__(self, site_row: dict, eq_rows: list):
        self._site = site_row
        self._eq = eq_rows

    def table(self, name):
        if name == "construction_sites":
            return _Q([self._site] if self._site else [])
        if name == "equipment_assets":
            return _Q(self._eq)
        return _Q([])


# ── BUILDING official runtime patches ────────────────────────────────────────

def _patch_bld(monkeypatch, cap):
    def fake_leg(step1):
        cap["step1"] = step1
        return {"engine_family": "LEG", "sector": "BUILDING", "obligations": []}
    monkeypatch.setattr(bld_rt, "run_leg_diagnosis", fake_leg)
    monkeypatch.setattr(
        "services.work_source.store.load_work_rows_optional", lambda sb, fid: []
    )
    monkeypatch.setattr(
        "services.material_source.store.load_factory_material_rows_optional",
        lambda sb, fid: [],
    )


# ── CONSTRUCTION official runtime patches ────────────────────────────────────

def _patch_cst(monkeypatch, cap):
    def fake_leg(step1):
        cap["step1"] = step1
        return {"engine_family": "LEG", "sector": "CONSTRUCTION", "obligations": []}
    monkeypatch.setattr(cst_rt, "run_leg_diagnosis", fake_leg)
    monkeypatch.setattr(
        "services.work_source.store.load_work_rows_optional", lambda sb, fid: []
    )
    monkeypatch.setattr(
        "services.material_source.store.load_factory_material_rows_optional",
        lambda sb, fid: [],
    )


def _site_row(**kw):
    base = {
        "id": "S1", "factory_id": "F1", "total_workers": 10, "direct_workers": 5,
        "subcon_workers": 5, "site_type": "BUILDING", "site_address": "서울",
        "contract_amount": 10,
    }
    base.update(kw)
    return base


# ── BLD-01~05: BUILDING official 5-code transport ────────────────────────────

@pytest.mark.parametrize("code,fact", [
    ("010", "has_emergency_gen"),
    ("014", "has_boiler"),
    ("023", "has_press"),
    ("024", "has_conveyor"),
    ("038", "has_pressure_vessel"),
])
def test_BLD_a2_five_codes_transport(monkeypatch, code, fact):
    """BLD-01~05: BUILDING official runtime equipment_rows → canonical fact in step1.input."""
    cap = {}
    _patch_bld(monkeypatch, cap)
    sb = _FakeSBBuilding({"floor_count": 5}, [{"equipment_type_code": code, "is_operating": True}])
    run_safe_building_leg(sb, "F1", SafeBuildingConsumerInput())
    assert cap["step1"].input.get(fact) is True, (
        f"code={code!r}: expected {fact}=True in step1.input, got {cap['step1'].input.get(fact)!r}"
    )


# ── BLD-06: BUILDING has_boiler=False priority ───────────────────────────────

def test_BLD_boiler_false_priority(monkeypatch):
    """BLD-06: factories.has_boiler=False + equipment 014 → exactly False."""
    cap = {}
    _patch_bld(monkeypatch, cap)
    sb = _FakeSBBuilding(
        {"has_boiler": False},
        [{"equipment_type_code": "014", "is_operating": True}],
    )
    run_safe_building_leg(sb, "F1", SafeBuildingConsumerInput())
    assert cap["step1"].input.get("has_boiler") is False, (
        f"expected has_boiler=False (factory explicit); got {cap['step1'].input.get('has_boiler')!r}"
    )


# ── BLD-07: BUILDING has_boiler absent → equipment 014 fills ─────────────────

def test_BLD_boiler_absent_filled_by_equipment(monkeypatch):
    """BLD-07: factories.has_boiler absent (unresolved) + equipment 014 → True."""
    cap = {}
    _patch_bld(monkeypatch, cap)
    # has_boiler absent from factory row (not set → unresolved)
    sb = _FakeSBBuilding(
        {"floor_count": 5},
        [{"equipment_type_code": "014", "is_operating": True}],
    )
    run_safe_building_leg(sb, "F1", SafeBuildingConsumerInput())
    assert cap["step1"].input.get("has_boiler") is True, (
        f"expected has_boiler=True (absent filled by equipment 014); got {cap['step1'].input.get('has_boiler')!r}"
    )


# ── BLD-08: BUILDING router EquipmentSourceLoadError → 503 ───────────────────

def test_BLD_router_equipment_error_returns_503(monkeypatch):
    """BLD-08: diagnose_building_leg EquipmentSourceLoadError → HTTP 503 / LEG 0."""
    import fastapi
    import fastapi.testclient
    from routers.legal_engine import router

    app = fastapi.FastAPI()
    app.include_router(router)

    def _raise_eq(sb, fid):
        raise EquipmentSourceLoadError("injected", factory_id=fid)

    monkeypatch.setattr("routers.legal_engine.get_supabase", lambda: object())
    monkeypatch.setattr("routers.legal_engine.get_current_user", lambda _: {"user_id": "u1"})
    monkeypatch.setattr("routers.legal_engine._ensure_factory_own", lambda sb, fid, cur: None)
    monkeypatch.setattr("routers.legal_engine._assert_saas_tier_fit_http", lambda sb, cur, **kw: {"status": "FIT"})
    monkeypatch.setattr("routers.legal_engine.leg_runtime_client.is_enabled", lambda: True)
    monkeypatch.setattr(
        "routers.legal_engine.run_safe_building_leg",
        lambda sb, fid, inp: (_ for _ in ()).throw(EquipmentSourceLoadError("injected", factory_id=fid)),
    )

    client = fastapi.testclient.TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/legal-engine/diagnose/building-leg",
        json={"factory_id": "F1", "input": {}},
        headers={"authorization": "Bearer fake"},
    )
    assert resp.status_code == 503, f"expected 503, got {resp.status_code}: {resp.text}"
    assert resp.json().get("detail", {}).get("code") == "EQUIPMENT_SOURCE_UNAVAILABLE"


# ── CST-01~05: CONSTRUCTION official 5-code transport ────────────────────────

@pytest.mark.parametrize("code,fact", [
    ("010", "has_emergency_gen"),
    ("014", "has_boiler"),
    ("023", "has_press"),
    ("024", "has_conveyor"),
    ("038", "has_pressure_vessel"),
])
def test_CST_a2_five_codes_transport(monkeypatch, code, fact):
    """CST-01~05: CONSTRUCTION official runtime equipment_rows → canonical fact in step1.input."""
    cap = {}
    _patch_cst(monkeypatch, cap)
    sb = _FakeSBConstruction(_site_row(), [{"equipment_type_code": code, "is_operating": True}])
    run_safe_construction_leg(sb, "S1", SafeConstructionConsumerInput())
    assert cap["step1"].input.get(fact) is True, (
        f"code={code!r}: expected {fact}=True in step1.input, got {cap['step1'].input.get(fact)!r}"
    )


# ── CST-06: CONSTRUCTION router EquipmentSourceLoadError → 503 ───────────────

def test_CST_router_equipment_error_returns_503(monkeypatch):
    """CST-06: diagnose_construction_leg EquipmentSourceLoadError → HTTP 503 / LEG 0."""
    import fastapi
    import fastapi.testclient
    from services.safe_construction_leg_runtime import ConstructionSiteBridgeError
    from routers.legal_engine import router

    app = fastapi.FastAPI()
    app.include_router(router)

    monkeypatch.setattr("routers.legal_engine.get_supabase", lambda: object())
    monkeypatch.setattr("routers.legal_engine.get_current_user", lambda _: {"user_id": "u1"})

    class _FakeSBSite:
        def table(self, n):
            if n == "construction_sites":
                return _Q([{"company_id": "C1"}])
            return _Q([])

    monkeypatch.setattr("routers.legal_engine.get_supabase", lambda: _FakeSBSite())
    monkeypatch.setattr("routers.legal_engine._ensure_own_company", lambda cid, cur, sb, msg: None)
    monkeypatch.setattr("routers.legal_engine._assert_saas_tier_fit_http", lambda sb, cur, **kw: {"status": "FIT"})
    monkeypatch.setattr("routers.legal_engine.leg_runtime_client.is_enabled", lambda: True)
    monkeypatch.setattr(
        "routers.legal_engine.run_safe_construction_leg",
        lambda sb, sid, inp: (_ for _ in ()).throw(EquipmentSourceLoadError("injected", factory_id="F1")),
    )

    client = fastapi.testclient.TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/legal-engine/diagnose/construction-leg",
        json={"site_id": "S1", "input": {}},
        headers={"authorization": "Bearer fake"},
    )
    assert resp.status_code == 503, f"expected 503, got {resp.status_code}: {resp.text}"
    assert resp.json().get("detail", {}).get("code") == "EQUIPMENT_SOURCE_UNAVAILABLE"


# ── PAID-01~03: Paid persistent Equipment seam ───────────────────────────────

def _run_paid_equipment_seam(engine_sector: str, eq_rows: list) -> dict:
    """Direct seam test: shared reader → projector → setdefault (same logic as run_diagnosis block)."""
    from services.equipment_source.store import load_equipment_rows_optional
    from services.equipment_source.projector import project_equipment_rows

    class _FakePaidSB:
        def table(self, name):
            if name == "equipment_assets":
                return _Q(eq_rows)
            return _Q([])

    inp: dict = {}
    rows = load_equipment_rows_optional(_FakePaidSB(), "F1")
    for k, v in project_equipment_rows(rows).items():
        inp.setdefault(k, v)
    return inp


def test_PAID_building_persistent_equipment(monkeypatch):
    """PAID-01: Paid BUILDING persistent Equipment — 023 → has_press=True via shared seam."""
    inp = _run_paid_equipment_seam(
        "BUILDING",
        [{"equipment_type_code": "023", "is_operating": True}],
    )
    assert inp.get("has_press") is True


def test_PAID_industrial_persistent_equipment(monkeypatch):
    """PAID-02: Paid INDUSTRIAL persistent Equipment — 023 → has_press=True, 024 → has_conveyor=True."""
    inp = _run_paid_equipment_seam(
        "MANUFACTURING",
        [
            {"equipment_type_code": "023", "is_operating": True},
            {"equipment_type_code": "024", "is_operating": True},
        ],
    )
    assert inp.get("has_press") is True
    assert inp.get("has_conveyor") is True


def test_PAID_construction_persistent_equipment_regression(monkeypatch):
    """PAID-03: Paid CONSTRUCTION persistent Equipment regression — 038 → has_pressure_vessel=True."""
    inp = _run_paid_equipment_seam(
        "CONSTRUCTION",
        [{"equipment_type_code": "038", "is_operating": True}],
    )
    assert inp.get("has_pressure_vessel") is True


# ── PAID explicit False priority ──────────────────────────────────────────────

def test_PAID_explicit_false_wins_over_equipment():
    """Paid path: explicit has_press=False + equipment 023 → exactly False (setdefault contract)."""
    from services.equipment_source.store import load_equipment_rows_optional
    from services.equipment_source.projector import project_equipment_rows

    class _FakePaidSB:
        def table(self, name):
            if name == "equipment_assets":
                return _Q([{"equipment_type_code": "023", "is_operating": True}])
            return _Q([])

    inp: dict = {"has_press": False}  # explicit from canonical
    rows = load_equipment_rows_optional(_FakePaidSB(), "F1")
    for k, v in project_equipment_rows(rows).items():
        inp.setdefault(k, v)
    assert inp.get("has_press") is False, (
        f"expected has_press=False (explicit); got {inp.get('has_press')!r}"
    )


# ── CRANE-01: 021/CRANE firewall ─────────────────────────────────────────────

@pytest.mark.parametrize("code", ["021", "CRANE"])
def test_CRANE_no_has_crane_in_building_or_construction(monkeypatch, code):
    """CRANE-01: 021/CRANE → has_crane 미발생 (BUILDING + CONSTRUCTION 공통)."""
    # BUILDING path
    cap_bld = {}
    _patch_bld(monkeypatch, cap_bld)
    sb_bld = _FakeSBBuilding({}, [{"equipment_type_code": code, "is_operating": True}])
    run_safe_building_leg(sb_bld, "F1", SafeBuildingConsumerInput())
    assert "has_crane" not in cap_bld["step1"].input, (
        f"BUILDING code={code!r}: has_crane must not appear"
    )

    # CONSTRUCTION path
    cap_cst = {}
    _patch_cst(monkeypatch, cap_cst)
    sb_cst = _FakeSBConstruction(_site_row(), [{"equipment_type_code": code, "is_operating": True}])
    run_safe_construction_leg(sb_cst, "S1", SafeConstructionConsumerInput())
    assert "has_crane" not in cap_cst["step1"].input, (
        f"CONSTRUCTION code={code!r}: has_crane must not appear"
    )


# ── PATCH1 helpers ─────────────────────────────────────────────────────────────

import services.diagnosis_integrated_svc as _svc
from schemas.diagnosis_integrated import DiagnosisRunBody
from fastapi import HTTPException


class _AnyQ:
    """Any-operation fake query chain — select/insert/update all return the same rows."""
    def __init__(self, rows): self._rows = rows
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def order(self, *a, **k): return self
    def update(self, *a, **k): return self
    def insert(self, *a, **k): return self
    def execute(self): return _Res(self._rows)


class _PaidFakeSB:
    """Fake SB for paid run_diagnosis integration tests."""
    def __init__(self, eq_rows: list):
        self._eq = eq_rows

    def table(self, name: str):
        if name == "diagnosis_disclaimer_log":
            return _AnyQ([{"id": "DL1", "ci_hash": "H1", "agreed": True}])
        if name == "equipment_assets":
            return _AnyQ(self._eq)
        if name == "anonymous_diagnosis_results":
            return _AnyQ([{"id": "DIAG1", "public_token": "PT1"}])
        return _AnyQ([])


def _patch_svc(monkeypatch):
    """Patch all non-equipment svc dependencies for run_diagnosis integration."""
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
    monkeypatch.setattr("services.canonical.materialization.canonical_applicability", lambda avail: {})


def _diag_body(sector: str) -> DiagnosisRunBody:
    return DiagnosisRunBody(
        auth_token="tok",
        sector=sector,
        factory_id="F1",
        disclaimer_log_id="DL1",
        payment_ref="PAY1",
        worker_count=5,
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


# ── PATCH1-A: Paid run_diagnosis integration ──────────────────────────────────

def test_PATCH1_A_BLD_run_diagnosis_has_press(monkeypatch):
    """PATCH1-A-BLD: run_diagnosis BUILDING paid → engine_sector gate → has_press=True in step1.input."""
    _patch_svc(monkeypatch)
    sb = _PaidFakeSB([{"equipment_type_code": "023", "is_operating": True}])
    cap: dict = {}
    def fake_step1(sb, s1b): cap["inp"] = dict(s1b.input or {}); return {"status": "success", "data": {}}
    _run_diag(sb, _diag_body("BUILDING"), fake_step1)
    assert cap["inp"].get("has_press") is True, (
        f"BUILDING paid: expected has_press=True via run_diagnosis gate; got {cap['inp'].get('has_press')!r}"
    )


def test_PATCH1_A_IND_run_diagnosis_has_conveyor(monkeypatch):
    """PATCH1-A-IND: run_diagnosis INDUSTRIAL paid → engine_sector=MANUFACTURING → has_conveyor=True."""
    _patch_svc(monkeypatch)
    sb = _PaidFakeSB([{"equipment_type_code": "024", "is_operating": True}])
    cap: dict = {}
    def fake_step1(sb, s1b): cap["inp"] = dict(s1b.input or {}); return {"status": "success", "data": {}}
    _run_diag(sb, _diag_body("INDUSTRIAL"), fake_step1)
    assert cap["inp"].get("has_conveyor") is True, (
        f"INDUSTRIAL paid (→MANUFACTURING): expected has_conveyor=True; got {cap['inp'].get('has_conveyor')!r}"
    )


def test_PATCH1_A_CST_run_diagnosis_has_pressure_vessel(monkeypatch):
    """PATCH1-A-CST: run_diagnosis CONSTRUCTION paid → gate 통과 → has_pressure_vessel=True."""
    _patch_svc(monkeypatch)
    sb = _PaidFakeSB([{"equipment_type_code": "038", "is_operating": True}])
    cap: dict = {}
    def fake_step1(sb, s1b): cap["inp"] = dict(s1b.input or {}); return {"status": "success", "data": {}}
    _run_diag(sb, _diag_body("CONSTRUCTION"), fake_step1)
    assert cap["inp"].get("has_pressure_vessel") is True, (
        f"CONSTRUCTION paid: expected has_pressure_vessel=True; got {cap['inp'].get('has_pressure_vessel')!r}"
    )


def test_PATCH1_A_explicit_false_preserved(monkeypatch):
    """PATCH1-A-EXF: explicit has_press=False set before equipment projector → setdefault preserves False."""
    _patch_svc(monkeypatch)
    # Override merge_projection_after_canonical to inject explicit False into inp before equipment runs.
    monkeypatch.setattr(_svc, "merge_projection_after_canonical",
                        lambda inp, canon, proj: inp.update({"has_press": False}))
    sb = _PaidFakeSB([{"equipment_type_code": "023", "is_operating": True}])
    cap: dict = {}
    def fake_step1(sb, s1b): cap["inp"] = dict(s1b.input or {}); return {"status": "success", "data": {}}
    _run_diag(sb, _diag_body("BUILDING"), fake_step1)
    assert cap["inp"].get("has_press") is False, (
        f"explicit False + equipment 023: expected has_press=False (setdefault); got {cap['inp'].get('has_press')!r}"
    )


def test_PATCH1_A_ownership_check_called_once(monkeypatch):
    """PATCH1-A-OWN: run_diagnosis BUILDING paid → _ensure_factory_own called exactly once with factory_id."""
    _patch_svc(monkeypatch)
    calls: list = []
    monkeypatch.setattr("services.company_scope._ensure_factory_own",
                        lambda sb, fid, cu: calls.append(fid))
    sb = _PaidFakeSB([])
    def fake_step1(sb, s1b): return {"status": "success", "data": {}}
    _run_diag(sb, _diag_body("BUILDING"), fake_step1)
    assert calls == ["F1"], f"expected _ensure_factory_own(['F1']); got {calls}"


def test_PATCH1_A_equipment_read_fail_503_step1_zero(monkeypatch):
    """PATCH1-A-503: run_diagnosis equipment read fail → HTTPException 503, run_step1_func 0 calls."""
    _patch_svc(monkeypatch)

    def _raise_eq(sb, fid):
        raise EquipmentSourceLoadError("injected", factory_id=fid)
    monkeypatch.setattr("services.equipment_source.store.load_equipment_rows_optional", _raise_eq)

    step1_calls: list = []
    def fake_step1(sb, s1b): step1_calls.append(1); return {"status": "success", "data": {}}

    sb = _PaidFakeSB([])
    with pytest.raises(HTTPException) as exc_info:
        _run_diag(sb, _diag_body("BUILDING"), fake_step1)
    assert exc_info.value.status_code == 503, (
        f"expected 503 on equipment read fail; got {exc_info.value.status_code}"
    )
    assert step1_calls == [], f"run_step1_func must not be called; got {step1_calls}"


# ── PATCH1-B: Runtime fail-closed (LEG = 0 on equipment read error) ───────────

def test_PATCH1_B_BLD_runtime_read_failure_leg_zero(monkeypatch):
    """PATCH1-B-BLD: run_safe_building_leg equipment read fail → EquipmentSourceLoadError, run_leg_diagnosis 0."""

    def _raise_eq(sb, fid):
        raise EquipmentSourceLoadError("injected", factory_id=fid)
    monkeypatch.setattr("services.equipment_source.store.load_equipment_rows_optional", _raise_eq)
    monkeypatch.setattr("services.work_source.store.load_work_rows_optional", lambda sb, fid: [])
    monkeypatch.setattr(
        "services.material_source.store.load_factory_material_rows_optional", lambda sb, fid: []
    )
    leg_calls: list = []
    monkeypatch.setattr(bld_rt, "run_leg_diagnosis", lambda s1: leg_calls.append(1) or {})

    sb = _FakeSBBuilding({"floor_count": 5}, [])
    with pytest.raises(EquipmentSourceLoadError):
        run_safe_building_leg(sb, "F1", SafeBuildingConsumerInput())
    assert leg_calls == [], f"run_leg_diagnosis must not be called on equipment read error; got {leg_calls}"


def test_PATCH1_B_CST_runtime_read_failure_leg_zero(monkeypatch):
    """PATCH1-B-CST: run_safe_construction_leg equipment read fail → EquipmentSourceLoadError, run_leg_diagnosis 0."""
    monkeypatch.setattr(
        cst_rt,
        "assemble_construction_marketing_contract",
        lambda sb, sid: {"factory_id": "F1", "values": {}, "unresolved_fields": [], "provenance": {}},
    )

    def _raise_eq(sb, fid):
        raise EquipmentSourceLoadError("injected", factory_id=fid)
    monkeypatch.setattr("services.equipment_source.store.load_equipment_rows_optional", _raise_eq)
    monkeypatch.setattr("services.work_source.store.load_work_rows_optional", lambda sb, fid: [])
    monkeypatch.setattr(
        "services.material_source.store.load_factory_material_rows_optional", lambda sb, fid: []
    )
    leg_calls: list = []
    monkeypatch.setattr(cst_rt, "run_leg_diagnosis", lambda s1: leg_calls.append(1) or {})

    sb = _FakeSBConstruction(_site_row(), [])
    with pytest.raises(EquipmentSourceLoadError):
        run_safe_construction_leg(sb, "S1", SafeConstructionConsumerInput())
    assert leg_calls == [], f"run_leg_diagnosis must not be called on equipment read error; got {leg_calls}"
