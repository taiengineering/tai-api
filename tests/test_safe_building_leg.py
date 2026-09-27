"""WO-BLD-FINALIZATION + WO-SAAS-BUILDING-VERIFIED-AUTO-SOURCE-IMPLEMENT-001

SAFE BUILDING leg runtime 검증.

기존 계약 (6 tests):
  test_owned_exact_read         — OWNED_EXACT 3 factories→step1
  test_override_runtime         — consumer explicit override
  test_none_not_override        — None은 override 아님
  test_owned_absent_unresolved  — OWNED_EXACT absent → unresolved
  test_leg_once_no_write        — run_leg_diagnosis 1회, DB WRITE 0
  test_floor_count_not_overridable — SafeBuildingConsumerInput extra=forbid

신규 (T1–T8):
  T1  employee_count → worker_count 자동 source
  T2  building_area  → total_floor_area 자동 source
  T3  elevator_count=2 → step1.elevator_count=2 → has_building_elevator=True
  T4  elevator_count=0 → step1.elevator_count=0 → has_building_elevator=False
  T5  None → absent (worker_count/total_floor_area/elevator_count 모두 누락)
  T6  consumer explicit override가 factory source보다 우선
  T7  Gas/Chem firewall — factory 값 있어도 자동 주입 0
  T8  consumer explicit false/True → 보존
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import services.safe_building_leg_runtime as bld_rt
from services.safe_building_leg_runtime import run_safe_building_leg
from schemas.legal_engine import SafeBuildingConsumerInput, SafeBuildingLegBody


class _Res:
    def __init__(s, d): s.data = d


class _Q:
    def __init__(s, rows): s._rows = rows
    def select(s, *a, **k): return s
    def eq(s, *a, **k): return s
    def limit(s, *a, **k): return s
    def order(s, *a, **k): return s
    def execute(s): return _Res(s._rows)


class _FakeSB:
    def __init__(s, fac): s._fac = fac; s.writes = 0
    def table(s, n): return _Q([s._fac] if (n == "factories" and s._fac) else [])


def _patch(monkeypatch, cap):
    def fake(step1):
        cap["step1"] = step1
        return {"engine_family": "LEG", "sector": "BUILDING", "obligations": []}
    monkeypatch.setattr(bld_rt, "run_leg_diagnosis", fake)


# ── 기존 계약 ────────────────────────────────────────────────────────────────

def test_owned_exact_read(monkeypatch):
    cap = {}; _patch(monkeypatch, cap)
    out = run_safe_building_leg(
        _FakeSB({"floor_count": 12, "has_boiler": True, "is_multi_use": False}),
        "F1", SafeBuildingConsumerInput(),
    )
    inp = cap["step1"].input
    assert inp["floor_count"] == 12 and inp["has_boiler"] is True and inp["is_multi_use"] is False
    assert cap["step1"].sector == "BUILDING" and cap["step1"].factory_id == "F1"


def test_override_runtime(monkeypatch):
    cap = {}; _patch(monkeypatch, cap)
    ci = SafeBuildingConsumerInput(
        building_use_type="오피스텔", building_height_m=250.0,
        has_high_pressure_gas=True, has_flat_plate_structure=True, is_collapse_risk_land=False,
    )
    run_safe_building_leg(_FakeSB({"floor_count": 5}), "F1", ci)
    inp = cap["step1"].input
    assert inp["building_use_type"] == "오피스텔" and inp["building_height_m"] == 250.0
    assert inp["has_high_pressure_gas"] is True
    assert inp["has_flat_plate_structure"] is True and inp["is_collapse_risk_land"] is False


def test_none_not_override(monkeypatch):
    cap = {}; _patch(monkeypatch, cap)
    run_safe_building_leg(
        _FakeSB({"floor_count": 5}), "F1",
        SafeBuildingConsumerInput(building_use_type=None),
    )
    assert "building_use_type" not in cap["step1"].input


def test_owned_absent_unresolved(monkeypatch):
    cap = {}; _patch(monkeypatch, cap)
    out = run_safe_building_leg(_FakeSB({"floor_count": 5}), "F1", SafeBuildingConsumerInput())
    assert "has_boiler" in out["unresolved_fields"] and "is_multi_use" in out["unresolved_fields"]


def test_leg_once_no_write(monkeypatch):
    cap = {"n": 0}
    def fake(step1): cap["n"] += 1; cap["step1"] = step1; return {"engine_family": "LEG"}
    monkeypatch.setattr(bld_rt, "run_leg_diagnosis", fake)
    sb = _FakeSB({"floor_count": 5})
    run_safe_building_leg(sb, "F1", SafeBuildingConsumerInput())
    assert cap["n"] == 1 and sb.writes == 0


def test_floor_count_not_overridable():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SafeBuildingLegBody(factory_id="F1", input={"floor_count": 5})


# ── T1: employee_count → worker_count ────────────────────────────────────────

def test_t1_worker_count_from_factory(monkeypatch):
    """T1: factory.employee_count=37 → step1.input['worker_count']==37."""
    cap = {}; _patch(monkeypatch, cap)
    run_safe_building_leg(
        _FakeSB({"employee_count": 37}), "F1", SafeBuildingConsumerInput(),
    )
    assert cap["step1"].input.get("worker_count") == 37


# ── T2: building_area → total_floor_area ─────────────────────────────────────

def test_t2_total_floor_area_from_factory(monkeypatch):
    """T2: factory.building_area=5234.5 → step1.input['total_floor_area']==5234.5. 단위 변환 없음."""
    cap = {}; _patch(monkeypatch, cap)
    run_safe_building_leg(
        _FakeSB({"building_area": 5234.5}), "F1", SafeBuildingConsumerInput(),
    )
    assert cap["step1"].input.get("total_floor_area") == 5234.5


# ── T3: elevator_count=2 → True ──────────────────────────────────────────────

def test_t3_elevator_true(monkeypatch):
    """T3: factory.elevator_count=2 → step1.elevator_count==2 → has_building_elevator=True."""
    cap = {}; _patch(monkeypatch, cap)
    run_safe_building_leg(
        _FakeSB({"elevator_count": 2}), "F1", SafeBuildingConsumerInput(),
    )
    assert cap["step1"].elevator_count == 2
    from clients.leg_runtime_client import build_facility
    facility = build_facility(cap["step1"])
    assert facility.get("has_building_elevator") is True


# ── T4: elevator_count=0 → False ─────────────────────────────────────────────

def test_t4_elevator_false(monkeypatch):
    """T4: factory.elevator_count=0 → step1.elevator_count==0 → has_building_elevator=False."""
    cap = {}; _patch(monkeypatch, cap)
    run_safe_building_leg(
        _FakeSB({"elevator_count": 0}), "F1", SafeBuildingConsumerInput(),
    )
    assert cap["step1"].elevator_count == 0
    from clients.leg_runtime_client import build_facility
    facility = build_facility(cap["step1"])
    assert facility.get("has_building_elevator") is False


# ── T5: None → absent ────────────────────────────────────────────────────────

def test_t5_none_yields_absent(monkeypatch):
    """T5: factory values all None → worker_count/total_floor_area/elevator_count/has_building_elevator absent."""
    cap = {}; _patch(monkeypatch, cap)
    run_safe_building_leg(
        _FakeSB({"employee_count": None, "building_area": None, "elevator_count": None}),
        "F1", SafeBuildingConsumerInput(),
    )
    inp = cap["step1"].input
    assert "worker_count" not in inp
    assert "total_floor_area" not in inp
    # elevator_count absent → DiagnoseStep1Body.elevator_count 기본값 None
    assert cap["step1"].elevator_count is None
    from clients.leg_runtime_client import build_facility
    facility = build_facility(cap["step1"])
    assert "has_building_elevator" not in facility


# ── T6: consumer override 우선 ────────────────────────────────────────────────

def test_t6_consumer_override_wins(monkeypatch):
    """T6: factory.employee_count=30, building_area=5000; consumer worker_count=55, total_floor_area=7000 → consumer wins."""
    cap = {}; _patch(monkeypatch, cap)
    run_safe_building_leg(
        _FakeSB({"employee_count": 30, "building_area": 5000.0}),
        "F1",
        SafeBuildingConsumerInput(worker_count=55, total_floor_area=7000.0),
    )
    inp = cap["step1"].input
    assert inp.get("worker_count") == 55
    assert inp.get("total_floor_area") == 7000.0


# ── T7: Gas/Chem/Hazmat firewall ─────────────────────────────────────────────

def test_t7_gas_chem_firewall(monkeypatch):
    """T7: factory has gas/chem flags; consumer empty → has_high_pressure_gas/has_chemical_substance/has_hazardous_material absent."""
    cap = {}; _patch(monkeypatch, cap)
    run_safe_building_leg(
        _FakeSB({
            "has_high_pressure_gas": True,
            "has_chemical_substance": True,
            "is_hazardous_material": True,
        }),
        "F1", SafeBuildingConsumerInput(),
    )
    inp = cap["step1"].input
    assert "has_high_pressure_gas" not in inp, "has_high_pressure_gas must not auto-inject"
    assert "has_chemical_substance" not in inp, "has_chemical_substance must not auto-inject"
    assert "has_hazardous_material" not in inp, "has_hazardous_material must not auto-inject"


# ── T8: consumer explicit false/True 보존 ─────────────────────────────────────

def test_t8_explicit_false_true_preserved(monkeypatch):
    """T8: consumer explicit has_high_pressure_gas=False/has_chemical_substance=True/has_hazardous_material=False → preserved."""
    cap = {}; _patch(monkeypatch, cap)
    run_safe_building_leg(
        _FakeSB({}),
        "F1",
        SafeBuildingConsumerInput(
            has_high_pressure_gas=False,
            has_chemical_substance=True,
            has_hazardous_material=False,
        ),
    )
    inp = cap["step1"].input
    assert inp.get("has_high_pressure_gas") is False
    assert inp.get("has_chemical_substance") is True
    assert inp.get("has_hazardous_material") is False
