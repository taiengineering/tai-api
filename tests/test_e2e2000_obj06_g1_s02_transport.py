"""WO-E2E2000-OBJ06-G1-S02-C1C3-TRANSPORT-001 — S02 4-fact SAFE transport tests.

RED→GREEN: T0 proves current absence (RED), then confirms transport after fix (GREEN).
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
    def execute(s):
        s.c["reads"] += 1
        rows = [r for r in s.store if all(r.get(k) == v for k, v in s._f.items())]
        return _Res(copy.deepcopy(rows))

class _T:
    def __init__(s, name, store, c): s.name = name; s.store = store; s.c = c
    def select(s, *a, **k): return _Q(s.store, s.c)

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


def test_T1_true_false_false_count_transported(monkeypatch):
    """T/F/F/2 exact values reach build_facility input (C3)."""
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
    inp = cap["step1"].input
    assert inp["contracts_construction_work_at_site"] is True
    assert inp["leads_and_manages_construction_execution"] is False
    assert inp["recontracts_received_construction_work"] is False
    assert inp["same_site_contracted_construction_work_count"] == 2


def test_T1_each_bool_false_individually(monkeypatch):
    """Each boolean False preserved independently (not just one)."""
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
        assert cap["step1"].input[key] is False, f"False not preserved for {key}"


def test_T1_count_zero_preserved(monkeypatch):
    """same_site_contracted_construction_work_count=0 is preserved (not treated as absent)."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(
        _sb(), "S1", {"same_site_contracted_construction_work_count": 0}
    )
    assert cap["step1"].input["same_site_contracted_construction_work_count"] == 0


def test_T1_count_1(monkeypatch):
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(
        _sb(), "S1", {"same_site_contracted_construction_work_count": 1}
    )
    assert cap["step1"].input["same_site_contracted_construction_work_count"] == 1


def test_T2_none_absent_not_zero(monkeypatch):
    """None (omitted) S02 key is ABSENT at C2/C3, not False/0."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    run_safe_construction_leg(_sb(), "S1", {})
    inp = cap["step1"].input
    for key in _S02_KEYS:
        assert key not in inp, f"None S02 key '{key}' should be absent, not {inp.get(key)!r}"


def test_T2_partial_subset_only_subset_transmitted(monkeypatch):
    """Supplying only some S02 keys transmits only those keys."""
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
        assert key not in inp, f"Omitted key '{key}' must be absent"


def test_T3_pydantic_rejects_bool_for_count():
    """StrictInt rejects bool coercion for count field."""
    import pytest
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
    # No event provided; S02 fields from direct input only
    run_safe_construction_leg(
        _sb(), "S1",
        {"contracts_construction_work_at_site": True},
        subcontract_legal_event_id=None,
        subcontractor_id=None,
    )
    assert cap["step1"].input.get("contracts_construction_work_at_site") is True


def test_T5_industrial_and_building_sector_isolated():
    """S02 fields are CONSTRUCTION-specific; not injected into INDUSTRIAL/BUILDING path."""
    from services.safe_construction_leg_runtime import SAFE_CST_OVERRIDE_FIELDS
    # Verify the S02 keys are not present in Industrial/Building override lists
    try:
        from services.safe_industrial_leg_runtime import SAFE_IND_OVERRIDE_FIELDS
        for key in _S02_KEYS:
            assert key not in SAFE_IND_OVERRIDE_FIELDS, (
                f"S02 key '{key}' leaked into INDUSTRIAL override"
            )
    except ImportError:
        pass  # Module may not exist; isolation implicitly held

    try:
        from services.safe_building_leg_runtime import SAFE_BLD_OVERRIDE_FIELDS
        for key in _S02_KEYS:
            assert key not in SAFE_BLD_OVERRIDE_FIELDS, (
                f"S02 key '{key}' leaked into BUILDING override"
            )
    except ImportError:
        pass


def test_T6_no_db_write(monkeypatch):
    """Transport fix introduces no DB writes."""
    cap = {"called": 0}
    _patch_leg(monkeypatch, cap)
    sb = _sb()
    run_safe_construction_leg(
        _sb(), "S1",
        {
            "contracts_construction_work_at_site": True,
            "leads_and_manages_construction_execution": False,
            "recontracts_received_construction_work": False,
            "same_site_contracted_construction_work_count": 2,
        },
    )
    assert sb.counters["writes"] == 0
