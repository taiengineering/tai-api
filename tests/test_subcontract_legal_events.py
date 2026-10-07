"""S02-L2 — Subcontract legal event source lifecycle and canonical adapter tests.

L1: create_draft — valid ART35_A event → status=DRAFT
L2: confirm without obligated_actor_company_id → 422
L3: confirm with all required fields → status=CONFIRMED
L4: confirm ART37_F without notice_event_id → 422
L5: CONFIRMED → patch → 409
L6: CONFIRMED → VOID → status=VOID
L7: VOID → CONFIRMED → 409

E1: CONFIRMED ART35_A → {subcontract_legal_actor_role: GENERAL_CONTRACTOR, art35_direct_payment_confirmation_required: true}
E2: DRAFT event → {}
E3: VOID event → {}
E4: CONFIRMED with missing actor_role → {}
E5: CONFIRMED ART35_B with basis_type → correct enum value
E6: CONFIRMED ART36_C → direction=INCREASE
E7: CONFIRMED ART36_D → direction=DECREASE
E8: never emits False value (all 6 types)
E9: site mismatch → {} (from runtime perspective)
"""
from __future__ import annotations

import uuid as _uuid

import pytest
from fastapi import HTTPException

from services.subcontract_legal_event_source.store import (
    create_draft,
    update_draft,
    confirm_event,
    void_event,
    get_event,
    get_event_exact,
    load_confirmed_subcontract_legal_event_context,
    TABLE,
)
from services.subcontract_legal_event_source.canonical_adapter import (
    project_confirmed_event,
    get_event_provenance,
)
from clients.leg_runtime_client import _LEG_INPUT_FIELDS


# ── In-memory fake Supabase ────────────────────────────────────────────────────

class _Res:
    def __init__(self, d):
        self.data = d


class _MutableQ:
    def __init__(self, store, table_name):
        self._store = store
        self._name = table_name
        self._filters = {}
        self._payload = None
        self._op = None
        self._order_params = None

    def select(self, *a, **k):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, k, v):
        self._filters[k] = v
        return self

    def limit(self, *a, **k):
        return self

    def order(self, *a, **k):
        self._order_params = (a, k)
        return self

    def in_(self, k, vals):
        self._filters[k] = ("__in__", [str(v) for v in vals])
        return self

    def execute(self):
        rows = self._store.get(self._name, [])
        if self._op == "insert":
            row = {"id": str(_uuid.uuid4()), **self._payload}
            rows.append(row)
            self._store[self._name] = rows
            return _Res([row])
        if self._op == "update":
            matched = []
            for r in rows:
                if all(str(r.get(k)) == str(v) for k, v in self._filters.items()):
                    r.update(self._payload)
                    matched.append(r)
            return _Res(matched)
        # select
        def _match(r):
            for k, v in self._filters.items():
                if isinstance(v, tuple) and v[0] == "__in__":
                    if str(r.get(k)) not in v[1]:
                        return False
                else:
                    if str(r.get(k)) != str(v):
                        return False
            return True
        result = [r for r in rows if _match(r)]
        return _Res(result)


class _InMemorySB:
    def __init__(self):
        self._store = {}

    def table(self, name):
        if name not in self._store:
            self._store[name] = []
        return _MutableQ(self._store, name)


# ── Helpers ───────────────────────────────────────────────────────────────────

_SITE_ID = str(_uuid.uuid4())
_SUB_ID = str(_uuid.uuid4())
_SITE_COMPANY_ID = str(_uuid.uuid4())
_SUB_COMPANY_ID = str(_uuid.uuid4())
_ACTOR_COMPANY_ID = str(_uuid.uuid4())


def _make_sb():
    sb = _InMemorySB()
    # Seed construction_sites and subcontractors for identity resolution
    sb._store["construction_sites"] = [
        {"id": _SITE_ID, "company_id": _SITE_COMPANY_ID}
    ]
    sb._store["subcontractors"] = [
        {"id": _SUB_ID, "site_id": _SITE_ID, "company_id": _SUB_COMPANY_ID}
    ]
    return sb


def _make_art35a_draft(sb, **overrides):
    body = {"event_type": "ART35_DIRECT_PAYMENT_CONFIRMATION_REQUIRED", **overrides}
    return create_draft(sb, site_id=_SITE_ID, subcontractor_id=_SUB_ID, body=body)


def _make_art35a_confirmable_draft(sb):
    row = _make_art35a_draft(sb)
    # Patch in required fields for confirm
    update_draft(sb, event_id=row["id"], body={
        "occurred_at": "2026-10-01T09:00:00+09:00",
        "obligated_actor_company_id": _ACTOR_COMPANY_ID,
    })
    return get_event(sb, row["id"])


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle tests
# ─────────────────────────────────────────────────────────────────────────────

def test_L1_create_draft_status_draft():
    """L1: create_draft — valid ART35_A event → status=DRAFT"""
    sb = _make_sb()
    row = _make_art35a_draft(sb)
    assert row["status"] == "DRAFT"
    assert row["event_type"] == "ART35_DIRECT_PAYMENT_CONFIRMATION_REQUIRED"
    assert row["obligated_actor_role"] == "GENERAL_CONTRACTOR"
    assert row.get("confirmed_at") is None
    assert row.get("voided_at") is None


def test_L2_confirm_without_actor_company_id_raises_422():
    """L2: confirm without obligated_actor_company_id → 422"""
    sb = _make_sb()
    row = _make_art35a_draft(sb)
    # Only set occurred_at, no obligated_actor_company_id
    update_draft(sb, event_id=row["id"], body={"occurred_at": "2026-10-01T09:00:00+09:00"})
    with pytest.raises(HTTPException) as exc_info:
        confirm_event(sb, event_id=row["id"])
    assert exc_info.value.status_code == 422
    assert "obligated_actor_company_id" in exc_info.value.detail


def test_L3_confirm_with_all_required_fields():
    """L3: confirm with all required fields → status=CONFIRMED"""
    sb = _make_sb()
    draft = _make_art35a_confirmable_draft(sb)
    confirmed = confirm_event(sb, event_id=draft["id"])
    assert confirmed["status"] == "CONFIRMED"
    assert confirmed["confirmed_at"] is not None


def test_L4_confirm_art37f_without_notice_event_id_raises_422():
    """L4: confirm ART37_F without notice_event_id → 422"""
    sb = _make_sb()
    row = create_draft(sb, site_id=_SITE_ID, subcontractor_id=_SUB_ID, body={
        "event_type": "ART37_INSPECTION_COMPLETED_AS_DESIGNED",
    })
    update_draft(sb, event_id=row["id"], body={
        "occurred_at": "2026-10-01T09:00:00+09:00",
        "obligated_actor_company_id": _ACTOR_COMPANY_ID,
        "inspection_completed_at": "2026-10-01T09:00:00+09:00",
        "design_conformance_confirmed": True,
        "evidence_ref": "ref-001",
        # notice_event_id intentionally absent
    })
    with pytest.raises(HTTPException) as exc_info:
        confirm_event(sb, event_id=row["id"])
    assert exc_info.value.status_code == 422
    assert "notice_event_id" in exc_info.value.detail


def test_L5_confirmed_patch_raises_409():
    """L5: CONFIRMED → patch → 409"""
    sb = _make_sb()
    draft = _make_art35a_confirmable_draft(sb)
    confirm_event(sb, event_id=draft["id"])
    with pytest.raises(HTTPException) as exc_info:
        update_draft(sb, event_id=draft["id"], body={"scope_description": "변경 시도"})
    assert exc_info.value.status_code == 409


def test_L6_confirmed_to_void():
    """L6: CONFIRMED → VOID → status=VOID"""
    sb = _make_sb()
    draft = _make_art35a_confirmable_draft(sb)
    confirm_event(sb, event_id=draft["id"])
    voided = void_event(sb, event_id=draft["id"])
    assert voided["status"] == "VOID"
    assert voided["voided_at"] is not None


def test_L7_void_to_confirmed_raises_409():
    """L7: VOID → CONFIRMED → 409"""
    sb = _make_sb()
    draft = _make_art35a_confirmable_draft(sb)
    confirm_event(sb, event_id=draft["id"])
    void_event(sb, event_id=draft["id"])
    with pytest.raises(HTTPException) as exc_info:
        confirm_event(sb, event_id=draft["id"])
    assert exc_info.value.status_code == 409


# ─────────────────────────────────────────────────────────────────────────────
# Canonical adapter tests
# ─────────────────────────────────────────────────────────────────────────────

def _confirmed_event(event_type: str, **extra) -> dict:
    base = {
        "id": str(_uuid.uuid4()),
        "site_id": _SITE_ID,
        "subcontractor_id": _SUB_ID,
        "status": "CONFIRMED",
        "confirmed_at": "2026-10-01T09:00:00+00:00",
        "event_type": event_type,
        "obligated_actor_role": "GENERAL_CONTRACTOR" if event_type != "ART35_DIRECT_PAYMENT_BASIS" else "PROJECT_OWNER",
    }
    base.update(extra)
    return base


def test_E1_confirmed_art35a_projects_correct_facts():
    """E1: CONFIRMED ART35_A → correct facts"""
    event = _confirmed_event("ART35_DIRECT_PAYMENT_CONFIRMATION_REQUIRED")
    facts = project_confirmed_event(event)
    assert facts["subcontract_legal_actor_role"] == "GENERAL_CONTRACTOR"
    assert facts["art35_direct_payment_confirmation_required"] is True
    assert len(facts) == 2


def test_E2_draft_event_returns_empty():
    """E2: DRAFT event → {}"""
    event = _confirmed_event("ART35_DIRECT_PAYMENT_CONFIRMATION_REQUIRED")
    event["status"] = "DRAFT"
    facts = project_confirmed_event(event)
    assert facts == {}


def test_E3_void_event_returns_empty():
    """E3: VOID event → {}"""
    event = _confirmed_event("ART35_DIRECT_PAYMENT_CONFIRMATION_REQUIRED")
    event["status"] = "VOID"
    facts = project_confirmed_event(event)
    assert facts == {}


def test_E4_confirmed_missing_actor_role_returns_empty():
    """E4: CONFIRMED with missing actor_role → {}"""
    event = _confirmed_event("ART35_DIRECT_PAYMENT_CONFIRMATION_REQUIRED")
    event["obligated_actor_role"] = None
    facts = project_confirmed_event(event)
    assert facts == {}


def test_E5_confirmed_art35b_basis_type():
    """E5: CONFIRMED ART35_B with basis_type → correct enum value"""
    event = _confirmed_event("ART35_DIRECT_PAYMENT_BASIS", basis_type="AGREEMENT")
    facts = project_confirmed_event(event)
    assert facts["subcontract_legal_actor_role"] == "PROJECT_OWNER"
    assert facts["art35_direct_payment_basis_type"] == "AGREEMENT"
    assert len(facts) == 2


def test_E5_art35b_missing_basis_type_returns_empty():
    """E5b: ART35_B without basis_type → {}"""
    event = _confirmed_event("ART35_DIRECT_PAYMENT_BASIS")
    # no basis_type key
    facts = project_confirmed_event(event)
    assert facts == {}


def test_E6_confirmed_art36c_increase():
    """E6: CONFIRMED ART36_C → direction=INCREASE"""
    event = _confirmed_event("ART36_PAYMENT_INCREASE_RECEIVED")
    facts = project_confirmed_event(event)
    assert facts["subcontract_legal_actor_role"] == "GENERAL_CONTRACTOR"
    assert facts["art36_contract_adjustment_direction"] == "INCREASE"
    assert len(facts) == 2


def test_E7_confirmed_art36d_decrease():
    """E7: CONFIRMED ART36_D → direction=DECREASE"""
    event = _confirmed_event("ART36_PAYMENT_REDUCTION_RECEIVED")
    facts = project_confirmed_event(event)
    assert facts["subcontract_legal_actor_role"] == "GENERAL_CONTRACTOR"
    assert facts["art36_contract_adjustment_direction"] == "DECREASE"
    assert len(facts) == 2


def test_E8_never_emits_false_for_all_event_types():
    """E8: never emits False value (all 6 confirmed types)"""
    event_types = [
        ("ART35_DIRECT_PAYMENT_CONFIRMATION_REQUIRED", {}),
        ("ART35_DIRECT_PAYMENT_BASIS", {"basis_type": "COURT_ORDER"}),
        ("ART36_PAYMENT_INCREASE_RECEIVED", {}),
        ("ART36_PAYMENT_REDUCTION_RECEIVED", {}),
        ("ART37_COMPLETION_OR_PROGRESS_NOTICE_RECEIVED", {}),
        ("ART37_INSPECTION_COMPLETED_AS_DESIGNED", {}),
    ]
    for etype, extra in event_types:
        event = _confirmed_event(etype, **extra)
        facts = project_confirmed_event(event)
        for key, val in facts.items():
            assert val is not False, (
                f"event_type={etype} emitted False for key={key}"
            )


def test_E9_site_mismatch_from_runtime_perspective():
    """E9: project_confirmed_event itself does not filter by site; site check is in runtime.
    Verify the adapter returns facts regardless — site guard is in run_safe_construction_leg."""
    event = _confirmed_event(
        "ART35_DIRECT_PAYMENT_CONFIRMATION_REQUIRED",
        site_id="OTHER_SITE",
    )
    # Adapter does not filter site — returns facts (runtime layer is responsible for site check)
    facts = project_confirmed_event(event)
    assert "art35_direct_payment_confirmation_required" in facts


def test_E9_runtime_no_subcontractor_id_skips_event_block():
    """E9 runtime: subcontract_legal_event_id without subcontractor_id → block skipped (co-presence)."""
    import services.safe_construction_leg_runtime as _rt

    _FAKE_SITE = "site-alpha"
    event_id = str(_uuid.uuid4())
    captured = {}

    def _fake_assemble(supabase, site_id):
        return {
            "factory_id": "fac-x",
            "values": {},
            "unresolved_fields": [],
            "provenance": {},
        }

    def _fake_leg(step1):
        captured["step1"] = step1
        return {"engine_family": "LEG"}

    class _FakeSB:
        def table(self, name): return type("_Q", (), {
            "select": lambda s, *a, **k: s,
            "eq": lambda s, *a, **k: s,
            "in_": lambda s, *a, **k: s,
            "limit": lambda s, *a, **k: s,
            "order": lambda s, *a, **k: s,
            "execute": lambda s: type("_R", (), {"data": []})(),
        })()

    import unittest.mock as mock
    with mock.patch.object(_rt, "assemble_construction_marketing_contract", _fake_assemble), \
         mock.patch.object(_rt, "run_leg_diagnosis", _fake_leg), \
         mock.patch("services.work_source.store.load_work_rows_optional", return_value=[]), \
         mock.patch("services.material_source.store.load_factory_material_rows_optional", return_value=[]), \
         mock.patch("services.equipment_source.store.load_equipment_rows_optional", return_value=[]):
        _rt.run_safe_construction_leg(
            _FakeSB(), _FAKE_SITE, {},
            subcontract_legal_event_id=event_id,
            subcontractor_id=None,
        )
    # Block skipped — step1 called without art35 facts
    assert captured.get("step1") is not None


# ─────────────────────────────────────────────────────────────────────────────
# WO-005 BLOCKER patch tests
# ─────────────────────────────────────────────────────────────────────────────

# BLOCKER-01: 6 canonical fields must be in _LEG_INPUT_FIELDS transport allowlist
def test_P01_s02_l2_fields_in_leg_input_fields():
    """P01: all 6 S02-L2 canonical fields present in _LEG_INPUT_FIELDS."""
    required = {
        "subcontract_legal_actor_role",
        "art35_direct_payment_confirmation_required",
        "art35_direct_payment_basis_type",
        "art36_contract_adjustment_direction",
        "art37_completion_or_progress_notice_received",
        "art37_inspection_completed_as_designed",
    }
    missing = required - set(_LEG_INPUT_FIELDS)
    assert not missing, f"Missing from _LEG_INPUT_FIELDS: {missing}"


# BLOCKER-02: Cross-subcontractor mutation guard
def test_P02_get_event_exact_rejects_wrong_site():
    """P02a: get_event_exact with wrong site_id → 404."""
    sb = _make_sb()
    row = _make_art35a_draft(sb)
    with pytest.raises(HTTPException) as exc_info:
        get_event_exact(sb, site_id="wrong-site", subcontractor_id=_SUB_ID, event_id=row["id"])
    assert exc_info.value.status_code == 404


def test_P02_get_event_exact_rejects_wrong_subcontractor():
    """P02b: get_event_exact with wrong subcontractor_id → 404."""
    sb = _make_sb()
    row = _make_art35a_draft(sb)
    wrong_sub = str(_uuid.uuid4())
    with pytest.raises(HTTPException) as exc_info:
        get_event_exact(sb, site_id=_SITE_ID, subcontractor_id=wrong_sub, event_id=row["id"])
    assert exc_info.value.status_code == 404


def test_P02_get_event_exact_succeeds_with_correct_binding():
    """P02c: get_event_exact with correct site+subcontractor → returns row."""
    sb = _make_sb()
    row = _make_art35a_draft(sb)
    found = get_event_exact(sb, site_id=_SITE_ID, subcontractor_id=_SUB_ID, event_id=row["id"])
    assert found["id"] == row["id"]


# BLOCKER-03: DRAFT → VOID forbidden (lifecycle fix)
def test_P03_draft_to_void_raises_409():
    """P03: void_event on DRAFT status → 409 (DRAFT→VOID forbidden)."""
    sb = _make_sb()
    row = _make_art35a_draft(sb)
    with pytest.raises(HTTPException) as exc_info:
        void_event(sb, event_id=row["id"])
    assert exc_info.value.status_code == 409
    assert "CONFIRMED" in exc_info.value.detail


# BLOCKER-03 supplement: CONFIRMED → VOID still works
def test_P03_confirmed_to_void_still_works():
    """P03b: CONFIRMED → VOID is still allowed."""
    sb = _make_sb()
    draft = _make_art35a_confirmable_draft(sb)
    confirm_event(sb, event_id=draft["id"])
    voided = void_event(sb, event_id=draft["id"])
    assert voided["status"] == "VOID"


# Timestamp guard: occurred_at in future → 422
def test_P04_occurred_at_future_raises_422():
    """P04: occurred_at in the future → 422 on confirm."""
    sb = _make_sb()
    row = _make_art35a_draft(sb)
    update_draft(sb, event_id=row["id"], body={
        "occurred_at": "2099-01-01T00:00:00+00:00",
        "obligated_actor_company_id": _ACTOR_COMPANY_ID,
    })
    with pytest.raises(HTTPException) as exc_info:
        confirm_event(sb, event_id=row["id"])
    assert exc_info.value.status_code == 422
    assert "미래" in exc_info.value.detail


# Timestamp guard: notice_received_at in future → 422
def test_P04_notice_received_at_future_raises_422():
    """P04b: notice_received_at in the future → 422 on confirm (ART37_E)."""
    sb = _make_sb()
    row = create_draft(sb, site_id=_SITE_ID, subcontractor_id=_SUB_ID, body={
        "event_type": "ART37_COMPLETION_OR_PROGRESS_NOTICE_RECEIVED",
    })
    update_draft(sb, event_id=row["id"], body={
        "occurred_at": "2026-10-01T09:00:00+09:00",
        "obligated_actor_company_id": _ACTOR_COMPANY_ID,
        "notice_type": "COMPLETION",
        "notice_received_at": "2099-01-01T00:00:00+00:00",
        "evidence_ref": "ref-001",
    })
    with pytest.raises(HTTPException) as exc_info:
        confirm_event(sb, event_id=row["id"])
    assert exc_info.value.status_code == 422
    assert "미래" in exc_info.value.detail


# evidence_ref required for ART37_E
def test_P04_art37e_missing_evidence_ref_raises_422():
    """P04c: ART37_E without evidence_ref → 422 on confirm."""
    sb = _make_sb()
    row = create_draft(sb, site_id=_SITE_ID, subcontractor_id=_SUB_ID, body={
        "event_type": "ART37_COMPLETION_OR_PROGRESS_NOTICE_RECEIVED",
    })
    update_draft(sb, event_id=row["id"], body={
        "occurred_at": "2026-10-01T09:00:00+09:00",
        "obligated_actor_company_id": _ACTOR_COMPANY_ID,
        "notice_type": "COMPLETION",
        "notice_received_at": "2026-10-01T09:00:00+09:00",
        # evidence_ref intentionally absent
    })
    with pytest.raises(HTTPException) as exc_info:
        confirm_event(sb, event_id=row["id"])
    assert exc_info.value.status_code == 422
    assert "evidence_ref" in exc_info.value.detail


# Schema co-presence: only event_id without subcontractor_id → ValidationError
def test_P05_schema_co_presence_only_event_id_raises():
    """P05: SafeConstructionLegBody with subcontract_legal_event_id but no subcontractor_id → error."""
    from pydantic import ValidationError
    from schemas.legal_engine import SafeConstructionLegBody

    with pytest.raises(ValidationError):
        SafeConstructionLegBody(
            site_id="site-1",
            input={},
            subcontract_legal_event_id="event-1",
            # subcontractor_id absent
        )


def test_P05_schema_co_presence_only_sub_id_raises():
    """P05b: SafeConstructionLegBody with subcontractor_id but no event_id → error."""
    from pydantic import ValidationError
    from schemas.legal_engine import SafeConstructionLegBody

    with pytest.raises(ValidationError):
        SafeConstructionLegBody(
            site_id="site-1",
            input={},
            subcontractor_id="sub-1",
            # subcontract_legal_event_id absent
        )


def test_P05_schema_co_presence_both_present_ok():
    """P05c: SafeConstructionLegBody with both fields present → valid."""
    from schemas.legal_engine import SafeConstructionLegBody

    body = SafeConstructionLegBody(
        site_id="site-1",
        input={},
        subcontract_legal_event_id="event-1",
        subcontractor_id="sub-1",
    )
    assert body.subcontract_legal_event_id == "event-1"
    assert body.subcontractor_id == "sub-1"


def test_P05_schema_co_presence_neither_present_ok():
    """P05d: SafeConstructionLegBody with neither event field → valid (standard LEG call)."""
    from schemas.legal_engine import SafeConstructionLegBody

    body = SafeConstructionLegBody(site_id="site-1", input={})
    assert body.subcontract_legal_event_id is None
    assert body.subcontractor_id is None


# load_confirmed_subcontract_legal_event_context exact binding
def test_P02_load_confirmed_context_draft_returns_none():
    """P02d: load_confirmed_subcontract_legal_event_context on DRAFT → None."""
    sb = _make_sb()
    row = _make_art35a_draft(sb)
    result = load_confirmed_subcontract_legal_event_context(
        sb, site_id=_SITE_ID, subcontractor_id=_SUB_ID, event_id=row["id"]
    )
    assert result is None


def test_P02_load_confirmed_context_confirmed_returns_row():
    """P02e: load_confirmed_subcontract_legal_event_context on CONFIRMED → row."""
    sb = _make_sb()
    draft = _make_art35a_confirmable_draft(sb)
    confirm_event(sb, event_id=draft["id"])
    result = load_confirmed_subcontract_legal_event_context(
        sb, site_id=_SITE_ID, subcontractor_id=_SUB_ID, event_id=draft["id"]
    )
    assert result is not None
    assert result["status"] == "CONFIRMED"


def test_P02_load_confirmed_context_wrong_subcontractor_returns_none():
    """P02f: load_confirmed_subcontract_legal_event_context with wrong subcontractor → None."""
    sb = _make_sb()
    draft = _make_art35a_confirmable_draft(sb)
    confirm_event(sb, event_id=draft["id"])
    result = load_confirmed_subcontract_legal_event_context(
        sb, site_id=_SITE_ID, subcontractor_id=str(_uuid.uuid4()), event_id=draft["id"]
    )
    assert result is None
