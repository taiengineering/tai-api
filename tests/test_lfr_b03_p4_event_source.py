"""WO-LFR-OBJ-B03-P4A — Event source canonical binding tests.

E1: no event_id → 0 DB reads, fact absent
E2: exact CONFIRMED event → has_hazardous_material_in_out_event=True
E3: wrong factory → fact absent
E4: DRAFT status → fact absent
E5: VOID status → fact absent
E6: missing event (unknown id) → fact absent, not False
E7: DB failure → HazardousMaterialEventSourceLoadError raised
E8: canonical adapter never emits False for non-qualifying inputs

§49: Supertall integration — floor_count=50/height=199/event=True → input has event fact
§50: No-event integration — floor_count=50/no event → event fact absent
"""
from __future__ import annotations

import pytest
import services.safe_building_leg_runtime as bld_rt
from services.safe_building_leg_runtime import run_safe_building_leg
from services.hazardous_material_event_source.store import (
    HazardousMaterialEventSourceLoadError,
    load_confirmed_event_context,
)
from services.hazardous_material_event_source.canonical_adapter import (
    project_hazardous_material_event_fact,
)
from schemas.legal_engine import SafeBuildingConsumerInput


_EVENT_FIELD = "has_hazardous_material_in_out_event"
_FAC_ID = "F-b03-p4"
_EVENT_ID = "evt-b03-p4-0001"


class _Res:
    def __init__(self, d): self.data = d


class _Q:
    def __init__(self, rows): self._rows = rows
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def order(self, *a, **k): return self
    def execute(self): return _Res(self._rows)


class _FakeSB:
    """Fake supabase: factories table returns fac_row, event table returns event_rows."""
    def __init__(self, fac_row, event_rows=None, raise_on_event=False):
        self._fac = fac_row
        self._events = event_rows or []
        self._raise = raise_on_event
        self.event_reads = 0

    def table(self, name):
        if name == "factory_hazardous_material_events":
            self.event_reads += 1
            if self._raise:
                raise RuntimeError("DB simulated failure")
            return _Q(self._events)
        return _Q([self._fac] if self._fac else [])


def _fac(floor_count=50, building_height=199.0):
    return {
        "floor_count": floor_count,
        "has_boiler": False,
        "is_multi_use": False,
        "building_height": building_height,
        "building_register_updated_at": "2026-01-01T00:00:00+09:00",
        "employee_count": 10,
        "building_area": 5000.0,
        "elevator_count": 2,
        "bdmgtsn": None,
        "mgm_bldrgst_pk": None,
    }


def _confirmed_event(factory_id=_FAC_ID, event_id=_EVENT_ID):
    return {
        "id": event_id,
        "factory_id": factory_id,
        "event_direction": "INBOUND",
        "occurred_at": "2026-10-01T09:00:00+09:00",
        "status": "CONFIRMED",
        "confirmed_at": "2026-10-01T10:00:00+09:00",
    }


def _patch_leg(monkeypatch, cap):
    def fake(step1):
        cap["step1"] = step1
        return {"engine_family": "LEG", "sector": "BUILDING", "obligations": []}
    monkeypatch.setattr(bld_rt, "run_leg_diagnosis", fake)


# ── E1: no event_id → 0 DB reads ─────────────────────────────────────────────
def test_E1_no_event_id_no_db_read(monkeypatch):
    cap = {}; _patch_leg(monkeypatch, cap)
    sb = _FakeSB(_fac())
    run_safe_building_leg(sb, _FAC_ID, SafeBuildingConsumerInput())
    assert sb.event_reads == 0
    assert _EVENT_FIELD not in (cap["step1"].input or {})


# ── E2: exact CONFIRMED event → canonical TRUE ────────────────────────────────
def test_E2_confirmed_exact_event_canonical_true(monkeypatch):
    cap = {}; _patch_leg(monkeypatch, cap)
    sb = _FakeSB(_fac(), event_rows=[_confirmed_event()])
    run_safe_building_leg(
        sb, _FAC_ID, SafeBuildingConsumerInput(),
        material_inout_event_id=_EVENT_ID,
    )
    assert (cap["step1"].input or {}).get(_EVENT_FIELD) is True


# ── E3: wrong factory → fact absent ──────────────────────────────────────────
def test_E3_wrong_factory_fact_absent(monkeypatch):
    cap = {}; _patch_leg(monkeypatch, cap)
    # event exists but event_rows returned = [] (wrong factory query guard is in store; simulate empty)
    sb = _FakeSB(_fac(), event_rows=[])  # DB returns empty for wrong-factory query
    run_safe_building_leg(
        sb, _FAC_ID, SafeBuildingConsumerInput(),
        material_inout_event_id="evt-OTHER",
    )
    assert _EVENT_FIELD not in (cap["step1"].input or {})


# ── E4: DRAFT status → fact absent ───────────────────────────────────────────
def test_E4_draft_status_fact_absent(monkeypatch):
    cap = {}; _patch_leg(monkeypatch, cap)
    draft_event = {**_confirmed_event(), "status": "DRAFT", "confirmed_at": None}
    # load_confirmed_event_context queries status=CONFIRMED; simulate empty return
    sb = _FakeSB(_fac(), event_rows=[])
    run_safe_building_leg(
        sb, _FAC_ID, SafeBuildingConsumerInput(),
        material_inout_event_id=_EVENT_ID,
    )
    assert _EVENT_FIELD not in (cap["step1"].input or {})


# ── E5: VOID status → fact absent ────────────────────────────────────────────
def test_E5_void_status_fact_absent(monkeypatch):
    cap = {}; _patch_leg(monkeypatch, cap)
    sb = _FakeSB(_fac(), event_rows=[])  # VOID not returned by CONFIRMED query
    run_safe_building_leg(
        sb, _FAC_ID, SafeBuildingConsumerInput(),
        material_inout_event_id=_EVENT_ID,
    )
    assert _EVENT_FIELD not in (cap["step1"].input or {})


# ── E6: missing event (unknown id) → fact absent, not False ──────────────────
def test_E6_missing_event_absent_not_false(monkeypatch):
    cap = {}; _patch_leg(monkeypatch, cap)
    sb = _FakeSB(_fac(), event_rows=[])
    run_safe_building_leg(
        sb, _FAC_ID, SafeBuildingConsumerInput(),
        material_inout_event_id="evt-UNKNOWN-9999",
    )
    inp = cap["step1"].input or {}
    assert _EVENT_FIELD not in inp
    # must not be False
    assert inp.get(_EVENT_FIELD) is not False


# ── E7: DB failure → HazardousMaterialEventSourceLoadError ───────────────────
def test_E7_db_failure_raises_load_error(monkeypatch):
    monkeypatch.setattr(bld_rt, "run_leg_diagnosis", lambda s: {})
    sb = _FakeSB(_fac(), raise_on_event=True)
    with pytest.raises(HazardousMaterialEventSourceLoadError):
        run_safe_building_leg(
            sb, _FAC_ID, SafeBuildingConsumerInput(),
            material_inout_event_id=_EVENT_ID,
        )


# ── E8: canonical adapter never emits False ───────────────────────────────────
def test_E8_canonical_adapter_never_emits_false():
    assert project_hazardous_material_event_fact(None) == {}
    assert project_hazardous_material_event_fact({}) == {}
    assert project_hazardous_material_event_fact({"status": "DRAFT"}) == {}
    assert project_hazardous_material_event_fact({"status": "VOID", "id": "x", "factory_id": "f"}) == {}
    # No False value in any return
    for inp in [None, {}, {"status": "DRAFT"}, {"status": "VOID", "id": "x", "factory_id": "f"}]:
        result = project_hazardous_material_event_fact(inp)
        assert result.get(_EVENT_FIELD) is not False


# ── §49: Supertall integration — event=True → input preserved ────────────────
def test_supertall_with_event_input_contains_fact(monkeypatch):
    """floor_count=50, height=199, CONFIRMED event → step1.input has event fact."""
    cap = {}; _patch_leg(monkeypatch, cap)
    sb = _FakeSB(_fac(floor_count=50, building_height=199.0), event_rows=[_confirmed_event()])
    run_safe_building_leg(
        sb, _FAC_ID, SafeBuildingConsumerInput(),
        material_inout_event_id=_EVENT_ID,
    )
    inp = cap["step1"].input or {}
    assert inp.get("floor_count") == 50
    assert inp.get("building_height_m") == 199.0
    assert inp.get(_EVENT_FIELD) is True


# ── §50: No-event integration — event fact absent ────────────────────────────
def test_supertall_no_event_fact_absent(monkeypatch):
    """floor_count=50, no event_id → event fact absent (UNKNOWN in LEG)."""
    cap = {}; _patch_leg(monkeypatch, cap)
    sb = _FakeSB(_fac(floor_count=50, building_height=199.0))
    run_safe_building_leg(sb, _FAC_ID, SafeBuildingConsumerInput())
    inp = cap["step1"].input or {}
    assert inp.get("floor_count") == 50
    assert _EVENT_FIELD not in inp
