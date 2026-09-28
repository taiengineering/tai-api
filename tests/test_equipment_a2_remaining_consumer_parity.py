"""WO-EQUIPMENT-A2-REMAINING-CONSUMER-PARITY-IMPLEMENT-001 — 잔여 consumer parity 검증.

Coverage:
  BLD-01~05  BUILDING official 5-code transport (010/014/023/024/038)
  BLD-06     BUILDING has_boiler=False + equipment 014 → exactly False
  BLD-07     BUILDING factories.has_boiler absent + equipment 014 → True
  BLD-08     BUILDING router EquipmentSourceLoadError → HTTP 503 / LEG 0
  CST-01~05  CONSTRUCTION official 5-code transport
  CST-06     CONSTRUCTION router EquipmentSourceLoadError → HTTP 503 / LEG 0
  PAID-01    Paid BUILDING persistent Equipment: 023 → has_press=True
  PAID-02    Paid INDUSTRIAL persistent Equipment: 023 → has_press=True
  PAID-03    Paid CONSTRUCTION persistent Equipment regression: 023 → has_press=True
  CRANE-01   021 / CRANE → has_crane 미발생 (BUILDING/CONSTRUCTION 공통)
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
