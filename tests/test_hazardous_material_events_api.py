"""WO-LFR-OBJ-B03-P4A — Event lifecycle and schema contract tests.


L1: POST draft creation → status=DRAFT
L2: incomplete DRAFT confirm → REJECT
L3: complete DRAFT confirm → status=CONFIRMED, confirmed_at non-null
L4: future occurred_at confirm → REJECT
L5: CONFIRMED PATCH → REJECT
L6: CONFIRMED → VOID → voided_at non-null
L7: VOID → CONFIRMED → REJECT
L8: hard delete endpoint does not exist

§46 regression: SafeBuildingConsumerInput(has_hazardous_material_in_out_event=True) → ValidationError
§47: SafeBuildingLegBody material_inout_event_id field accepted
§48: static factory_materials + no event_id → event fact absent
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from pydantic import ValidationError

import services.safe_building_leg_runtime as _bld_rt
from services.safe_building_leg_runtime import run_safe_building_leg
from schemas.legal_engine import SafeBuildingConsumerInput, SafeBuildingLegBody
from services.hazardous_material_event_source.store import (
    HazardousMaterialEventSourceLoadError,
    HazardousMaterialEventValidationError,
    confirm_event,
    create_event_draft,
    update_event_draft,
    void_event,
)


_FAC_ID = "F-lifecycle-test"
_EVENT_FIELD = "has_hazardous_material_in_out_event"


# ── Fake supabase for lifecycle tests ─────────────────────────────────────────

class _Res:
    def __init__(self, d): self.data = d


class _MutableQ:
    def __init__(self, store, table_name):
        self._store = store
        self._name = table_name
        self._filters = {}
        self._payload = None
        self._op = None

    def select(self, *a, **k): self._op = "select"; return self
    def insert(self, payload): self._op = "insert"; self._payload = payload; return self
    def update(self, payload): self._op = "update"; self._payload = payload; return self
    def eq(self, k, v): self._filters[k] = v; return self
    def limit(self, *a, **k): return self
    def order(self, *a, **k): return self

    def execute(self):
        rows = self._store.get(self._name, [])
        if self._op == "insert":
            import uuid as _uuid
            row = {"id": str(_uuid.uuid4()), **self._payload}
            rows.append(row)
            self._store[self._name] = rows
            return _Res([row])
        if self._op == "update":
            matched = []
            for r in rows:
                if all(r.get(k) == v for k, v in self._filters.items()):
                    r.update(self._payload)
                    matched.append(r)
            return _Res(matched)
        # select
        result = [r for r in rows if all(r.get(k) == v for k, v in self._filters.items())]
        return _Res(result)


class _InMemorySB:
    def __init__(self):
        self._store = {}

    def table(self, name):
        if name not in self._store:
            self._store[name] = []
        return _MutableQ(self._store, name)


TABLE = "factory_hazardous_material_events"

_FULL_PAYLOAD = dict(
    factory_id=_FAC_ID,
    event_direction="INBOUND",
    occurred_at="2026-10-01T09:00:00+09:00",
    purpose="제조 공정 원료",
    material_type="벤젠",
    quantity=10.5,
    quantity_unit="kg",
    material_use="원료",
    purchase_source="화학물질 공급사 A",
    carrier_name="운반사 B",
    responsible_person_name="홍길동",
    vehicle_type="탱크로리",
)


def _create_draft(sb, **overrides):
    payload = {**_FULL_PAYLOAD, **overrides}
    return create_event_draft(sb, **payload)


def _get_row(sb, event_id):
    res = sb.table(TABLE).select("*").eq("id", event_id).execute()
    rows = list(getattr(res, "data", None) or [])
    return rows[0] if rows else None


# ── L1: POST draft → status=DRAFT ────────────────────────────────────────────
def test_L1_create_draft_status_draft():
    sb = _InMemorySB()
    row = _create_draft(sb)
    assert row["status"] == "DRAFT"
    assert row["confirmed_at"] is None
    assert row["voided_at"] is None
    assert row["factory_id"] == _FAC_ID


# ── L2: incomplete DRAFT confirm → REJECT ─────────────────────────────────────
def test_L2_incomplete_draft_confirm_rejected():
    sb = _InMemorySB()
    # Draft missing required confirm fields
    row = create_event_draft(
        sb,
        factory_id=_FAC_ID,
        event_direction="INBOUND",
        # purpose, material_type, etc. all missing
    )
    with pytest.raises(HazardousMaterialEventValidationError):
        confirm_event(sb, factory_id=_FAC_ID, event_id=row["id"])


# ── L3: complete DRAFT confirm → CONFIRMED ────────────────────────────────────
def test_L3_complete_draft_confirms_successfully():
    sb = _InMemorySB()
    row = _create_draft(sb)
    confirmed = confirm_event(sb, factory_id=_FAC_ID, event_id=row["id"])
    assert confirmed["status"] == "CONFIRMED"
    assert confirmed["confirmed_at"] is not None
    assert confirmed["voided_at"] is None


# ── L4: future occurred_at confirm → REJECT ───────────────────────────────────
def test_L4_future_occurred_at_rejected():
    sb = _InMemorySB()
    future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    row = _create_draft(sb, occurred_at=future)
    with pytest.raises(HazardousMaterialEventValidationError):
        confirm_event(sb, factory_id=_FAC_ID, event_id=row["id"])


# ── L5: CONFIRMED PATCH → REJECT ──────────────────────────────────────────────
def test_L5_confirmed_patch_rejected():
    sb = _InMemorySB()
    row = _create_draft(sb)
    confirm_event(sb, factory_id=_FAC_ID, event_id=row["id"])
    with pytest.raises(HazardousMaterialEventValidationError):
        update_event_draft(
            sb, factory_id=_FAC_ID, event_id=row["id"],
            patch={"purpose": "변경 시도"},
        )


# ── L6: CONFIRMED → VOID ──────────────────────────────────────────────────────
def test_L6_confirmed_to_void():
    sb = _InMemorySB()
    row = _create_draft(sb)
    confirm_event(sb, factory_id=_FAC_ID, event_id=row["id"])
    voided = void_event(sb, factory_id=_FAC_ID, event_id=row["id"])
    assert voided["status"] == "VOID"
    assert voided["voided_at"] is not None
    assert voided["confirmed_at"] is not None


# ── L7: VOID → CONFIRMED → REJECT ────────────────────────────────────────────
def test_L7_void_to_confirmed_rejected():
    sb = _InMemorySB()
    row = _create_draft(sb)
    confirm_event(sb, factory_id=_FAC_ID, event_id=row["id"])
    void_event(sb, factory_id=_FAC_ID, event_id=row["id"])
    with pytest.raises(HazardousMaterialEventValidationError):
        confirm_event(sb, factory_id=_FAC_ID, event_id=row["id"])


# ── L8: hard delete endpoint does not exist ───────────────────────────────────
def test_L8_no_delete_endpoint():
    from routers.hazardous_material_events import router
    methods = {
        (r.path, m)
        for r in router.routes
        for m in getattr(r, "methods", [])
    }
    delete_routes = [(p, m) for p, m in methods if m == "DELETE"]
    assert not delete_routes, f"DELETE endpoints found: {delete_routes}"


# ── §46: Consumer firewall regression ────────────────────────────────────────
def test_S46_consumer_true_raises():
    with pytest.raises(ValidationError):
        SafeBuildingConsumerInput(**{_EVENT_FIELD: True})


def test_S46_consumer_false_raises():
    with pytest.raises(ValidationError):
        SafeBuildingConsumerInput(**{_EVENT_FIELD: False})


# ── §47: SafeBuildingLegBody accepts material_inout_event_id ─────────────────
def test_S47_body_accepts_event_id():
    body = SafeBuildingLegBody(
        factory_id="F-test",
        material_inout_event_id="evt-test-001",
        input=SafeBuildingConsumerInput(),
    )
    assert body.material_inout_event_id == "evt-test-001"
    assert body.factory_id == "F-test"


def test_S47_body_event_id_optional():
    body = SafeBuildingLegBody(factory_id="F-test", input=SafeBuildingConsumerInput())
    assert body.material_inout_event_id is None


# ── §48: Static factory_materials presence + no event → event fact absent ────
def test_S48_static_material_no_event_fact_absent():
    """factory_materials has hazardous rows but no event_id → no event fact emitted."""
    bld_rt = _bld_rt

    class _Res2:
        def __init__(self, d): self.data = d

    class _Q2:
        def __init__(self, rows): self._rows = rows
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def order(self, *a, **k): return self
        def execute(self): return _Res2(self._rows)

    fac_row = {
        "has_boiler": False, "is_multi_use": False,
        "floor_count": 5, "building_register_updated_at": "2026-01-01T00:00:00+09:00",
        "employee_count": 10, "building_area": 1000.0, "elevator_count": 0,
        "bdmgtsn": None, "mgm_bldrgst_pk": None, "building_height": 20.0,
    }
    mat_rows = [{"is_active": True, "material_master_key": "MANAGED_HAZARDOUS_SUBSTANCE_KEY"}]

    class _FakeSBWithMaterial:
        def table(self, name):
            if name == "factories": return _Q2([fac_row])
            if name == "factory_materials": return _Q2(mat_rows)
            return _Q2([])

    cap = {}
    def fake_leg(step1):
        cap["step1"] = step1
        return {"engine_family": "LEG"}
    import unittest.mock as mock
    with mock.patch.object(bld_rt, "run_leg_diagnosis", fake_leg):
        run_safe_building_leg(
            _FakeSBWithMaterial(), "F-mat-test", SafeBuildingConsumerInput(),
        )
    assert _EVENT_FIELD not in (cap["step1"].input or {})
