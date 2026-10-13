"""WO-E2E2000-OBJ06-G1-S02-PR608-TEST-CORRECTION-001 — S02 4-fact SAFE transport tests.

RED→GREEN: T0 proves current absence (RED), then confirms transport after fix (GREEN).
T1: step1.input(C2) AND build_facility(step1) output(C3) both verified.
T5: Correct sector constants + extra=forbid schema rejection (no ImportError suppression).
T6: Same FakeSB instance used in call and assertion; write sentinel active.
No LEG server, no DB, no production calls.
"""
from __future__ import annotations
import copy
import pytest

import services.safe_construction_leg_runtime as cst_rt
from services.safe_construction_leg_runtime import (
    run_safe_construction_leg, SAFE_CST_OVERRIDE_FIELDS,
)
from schemas.legal_engine import SafeConstructionConsumerInput
from clients.leg_runtime_client import build_facility


# ── shared fixtures ────────────────────────────────────────────────────────────

class _Res:
    def __init__(s, d): s.data = d

class _Q:
    def __init__(s, store, c): s.store = store; s.c = c; s._f = {}
    def select(s, *a, **k): return s
    def eq(s, col, val): s._f[col] = val; return s
    def in_(s, col, vals): return s
    def limit(s, n): return s
    def order(s, *a, **k): return s
    def insert(s, *a, **k): s.c["writes"] += 1; return s
    def update(s, *a, **k): s.c["writes"] += 1; return s
    def upsert(s, *a, **k): s.c["writes"] += 1; return s
    def delete(s, *a, **k): s.c["writes"] += 1; return s
    def execute(s):
        s.c["reads"] += 1
        rows = [r for r in s.store if all(r.get(k) == v for k, v in s._f.items())]
        return _Res(copy.deepcopy(rows))

class _T:
    def __init__(s, name, store, c): s.name = name; s.store = store; s.c = c
    def select(s, *a, **k): return _Q(s.store, s.c)
    def insert(s, *a, **k): s.c["writes"] += 1; return _Q(s.store, s.c)
    def update(s, *a, **k): s.c["writes"] += 1; return _Q(s.store, s.c)
    def upsert(s, *a, **k): s.c["writes"] += 1; return _Q(s.store, s.c)
    def delete(s, *a, **k): s.c["writes"] += 1; return _Q(s.store, s.c)

class FakeSB:
    def __init__(s, **stores):
        s.stores = {"construction_sites": []}
        s.stores.update(stores)
        s.counters = {"writes": 0, "reads": 0}
    def table(s, n): s.stores.setdefault(n, []); return _T(n, s.stores[n], s.counters)


def _site(**kw):
    base = {"id": "S1", "factory_id": "F1", "total_workers": 30, "direct_workers": 10,
            "subcon_workers": 20, "site_type": "BUILDING", "site_address": "서울",
            "contract_amount": 50}
    base.update(kw)
    return base

def _sb(**kw): return FakeSB(construction_sites=[_site()], **kw)


def _patch_leg(monkeypatch, capture):
    def fake_run(step1):
        capture["called"] += 1; capture["step1"] = step1
        return {"engine_family": "LEG", "sector": "CONSTRUCTION", "status_ok": True}
    monkeypatch.setattr(cst_rt, "run_leg_diagnosis", fake_run)


_S02_KEYS = (
    "contracts_construction_work_at_site",
    "leads_and_manages_construction_execution",
    "recontracts_received_construction_work",
    "same_site_contracted_construction_work_count",
)

# ── T0: RED → GREEN transport proof ───────────────────────────────────────────

def test_T0_s02_four_facts_in_override_allowlist():
    """_S02_OVERRIDE_FIELDS must be present in SAFE_CST_OVERRIDE_FIELDS."""
    for key in _S02_KEYS:
        assert key in SAFE_CST_OVERRIDE_FIELDS, (
            f"S02 key '{key}' missing from SAFE_CST_OVERRIDE_FIELDS — transport blocked"
        )


# ── T1: C2 (step1.input) AND C3 (build_facility output) verified ──────────────

def test_T1_true_false_false_count_transported(monkeypatch):
    """T/F/F/2 exact values reach C2 step1.input and C3 build_facility output."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(
        _sb(), "S1",
        {
            "contracts_construction_work_at_site": True,
            "leads_and_manages_construction_execution": False,
            "recontracts_received_construction_work": False,
            "same_site_contracted_construction_work_count": 2,
        },
    )
    # C2: step1.input
    inp = cap["step1"].input
    assert inp["contracts_construction_work_at_site"] is True
    assert inp["leads_and_manages_construction_execution"] is False
    assert inp["recontracts_received_construction_work"] is False
    assert inp["same_site_contracted_construction_work_count"] == 2
    # C3: build_facility output (direct call — no LEG server)
    facility = build_facility(cap["step1"])
    assert facility["contracts_construction_work_at_site"] is True
    assert facility["leads_and_manages_construction_execution"] is False
    assert facility["recontracts_received_construction_work"] is False
    assert facility["same_site_contracted_construction_work_count"] == 2


def test_T1_each_bool_false_individually(monkeypatch):
    """Each boolean False preserved independently at both C2 and C3."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    bools = (
        "contracts_construction_work_at_site",
        "leads_and_manages_construction_execution",
        "recontracts_received_construction_work",
    )
    for key in bools:
        cap["called"] = 0
        run_safe_construction_leg(_sb(), "S1", {key: False})
        assert cap["step1"].input[key] is False, f"False not preserved at C2 for {key}"
        facility = build_facility(cap["step1"])
        assert facility[key] is False, f"False not preserved at C3 for {key}"


def test_T1_count_zero_preserved(monkeypatch):
    """same_site_contracted_construction_work_count=0 preserved at C2 and C3."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(
        _sb(), "S1", {"same_site_contracted_construction_work_count": 0}
    )
    assert cap["step1"].input["same_site_contracted_construction_work_count"] == 0
    facility = build_facility(cap["step1"])
    assert facility["same_site_contracted_construction_work_count"] == 0


def test_T1_count_1(monkeypatch):
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(
        _sb(), "S1", {"same_site_contracted_construction_work_count": 1}
    )
    assert cap["step1"].input["same_site_contracted_construction_work_count"] == 1
    facility = build_facility(cap["step1"])
    assert facility["same_site_contracted_construction_work_count"] == 1


def test_T2_none_absent_not_zero(monkeypatch):
    """None (omitted) S02 key is ABSENT at C2/C3, not False/0."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {})
    inp = cap["step1"].input
    for key in _S02_KEYS:
        assert key not in inp, f"None S02 key '{key}' should be absent, not {inp.get(key)!r}"
    facility = build_facility(cap["step1"])
    for key in _S02_KEYS:
        assert key not in facility, f"None S02 key '{key}' should be absent from facility"


def test_T2_partial_subset_only_subset_transmitted(monkeypatch):
    """Supplying only some S02 keys transmits only those keys at C2 and C3."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(
        _sb(), "S1",
        {
            "contracts_construction_work_at_site": True,
            # other 3 omitted
        },
    )
    inp = cap["step1"].input
    assert inp.get("contracts_construction_work_at_site") is True
    for key in (
        "leads_and_manages_construction_execution",
        "recontracts_received_construction_work",
        "same_site_contracted_construction_work_count",
    ):
        assert key not in inp, f"Omitted key '{key}' must be absent at C2"
    facility = build_facility(cap["step1"])
    assert facility.get("contracts_construction_work_at_site") is True
    for key in (
        "leads_and_manages_construction_execution",
        "recontracts_received_construction_work",
        "same_site_contracted_construction_work_count",
    ):
        assert key not in facility, f"Omitted key '{key}' must be absent at C3"


# ── T3: Pydantic StrictInt contract ───────────────────────────────────────────

def test_T3_pydantic_rejects_bool_for_count():
    """StrictInt rejects bool coercion for count field."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SafeConstructionConsumerInput(same_site_contracted_construction_work_count=True)
    with pytest.raises(ValidationError):
        SafeConstructionConsumerInput(same_site_contracted_construction_work_count=False)


def test_T3_pydantic_rejects_negative_count():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SafeConstructionConsumerInput(same_site_contracted_construction_work_count=-1)


def test_T3_pydantic_rejects_float_count():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SafeConstructionConsumerInput(same_site_contracted_construction_work_count=1.5)


def test_T3_pydantic_rejects_numeric_string_count():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SafeConstructionConsumerInput(same_site_contracted_construction_work_count="2")


def test_T3_pydantic_valid_nonneg_int_passes():
    for n in (0, 1, 2, 10):
        obj = SafeConstructionConsumerInput(same_site_contracted_construction_work_count=n)
        assert obj.same_site_contracted_construction_work_count == n


# ── T4: cross-sector and event source isolation ───────────────────────────────

def test_T4_unrelated_runtime20_unaffected(monkeypatch):
    """Existing RUNTIME20 / SEM003 / HP-COMMON override fields still work."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(
        _sb(), "S1",
        {
            "has_excavation": True,
            "has_scuba_diving": False,
            "has_high_pressure_work": True,
        },
    )
    inp = cap["step1"].input
    assert inp.get("has_excavation") is True
    assert inp.get("has_scuba_diving") is False
    assert inp.get("has_high_pressure_work") is True


def test_T4_event_projector_not_used_for_s02(monkeypatch):
    """S02 facts come from consumer input, never from subcontract event source."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(
        _sb(), "S1",
        {"contracts_construction_work_at_site": True},
        subcontract_legal_event_id=None,
        subcontractor_id=None,
    )
    assert cap["step1"].input.get("contracts_construction_work_at_site") is True


# ── T5: sector isolation — correct constants, no ImportError suppression ──────

def test_T5_industrial_override_allowlist_excludes_s02():
    """S02 keys must NOT be in SAFE_UI_OVERRIDE_FIELDS (INDUSTRIAL sector allowlist)."""
    from services.safe_industrial_leg_runtime import SAFE_UI_OVERRIDE_FIELDS
    for key in _S02_KEYS:
        assert key not in SAFE_UI_OVERRIDE_FIELDS, (
            f"S02 key '{key}' leaked into INDUSTRIAL SAFE_UI_OVERRIDE_FIELDS"
        )


def test_T5_industrial_schema_rejects_s02_via_extra_forbid():
    """SafeIndustrialConsumerInput(extra=forbid) rejects each S02 key."""
    from schemas.legal_engine import SafeIndustrialConsumerInput
    from pydantic import ValidationError
    for key in _S02_KEYS:
        with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs are not permitted"):
            SafeIndustrialConsumerInput(**{key: True})


def test_T5_building_schema_rejects_s02_via_extra_forbid():
    """SafeBuildingConsumerInput(extra=forbid) rejects each S02 key."""
    from schemas.legal_engine import SafeBuildingConsumerInput
    from pydantic import ValidationError
    for key in _S02_KEYS:
        with pytest.raises(ValidationError, match="extra_forbidden|Extra inputs are not permitted"):
            SafeBuildingConsumerInput(**{key: True})


# ── T6: DB write 0 — same FakeSB instance, write sentinel active ──────────────

def test_T6_no_db_write(monkeypatch):
    """Transport fix introduces no DB writes. Same sb used in call and assertion."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    sb = _sb()
    run_safe_construction_leg(
        sb, "S1",   # same sb instance — sentinel active
        {
            "contracts_construction_work_at_site": True,
            "leads_and_manages_construction_execution": False,
            "recontracts_received_construction_work": False,
            "same_site_contracted_construction_work_count": 2,
        },
    )
    assert sb.counters["writes"] == 0, (
        f"Expected 0 DB writes, got {sb.counters['writes']}"
    )


def test_T6_write_sentinel_detects_writes():
    """Sentinel actually increments on insert/update/delete calls."""
    sb = _sb()
    sb.table("any_table").insert({"x": 1}).execute()
    assert sb.counters["writes"] >= 1
    sb2 = _sb()
    sb2.table("any_table").update({"x": 2}).eq("id", 1).execute()
    assert sb2.counters["writes"] >= 1
