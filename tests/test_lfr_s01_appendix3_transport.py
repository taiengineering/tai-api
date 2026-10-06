"""WO-LFR-OBJ-S01-P1-001 — TAI-API S01 Appendix3 Transport Tests (A1-A10).

A1  appendix3_item_no in _LEG_INPUT_FIELDS (S01 transport registration)
A2  CONSTRUCTION missing appendix3_item_no → 422 APPENDIX3_EXPLICIT_CLASSIFICATION_REQUIRED
A3  CONSTRUCTION item_no=48 present → appendix3 gate PASS
A4  CONSTRUCTION item_no=49 → children (is_relationship_contractor, is_civil_construction) required
A5  CONSTRUCTION item_no=48 → children NOT required
A6  is_construction now optional for CONSTRUCTION (no longer root gate)
A7  appendix3_item_no transported as exact integer to facility (DIRECT_CANONICAL)
A8  BUILDING/INDUSTRIAL appendix3 gate still requires item_no (GATED sectors unchanged)
A9  stored_explicit_predicate_body extracts appendix3_item_no for child gate
A10 GATED_NORMALIZED_SECTORS includes CONSTRUCTION
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from clients.leg_runtime_client import _LEG_INPUT_FIELDS, build_facility
from services.canonical.explicit_appendix3_classification import (
    GATED_NORMALIZED_SECTORS,
    missing_explicit_appendix3_fields,
)
from services.canonical.explicit_construction_predicates import (
    missing_explicit_construction_predicates,
    stored_explicit_predicate_body,
)
from services.canonical.leg_input_contract import build_unified_leg_input
from schemas.diagnosis_integrated import DiagnosisRunBody
from services import diagnosis_integrated_svc as svc


# ─────────────────────────────────────────────────────────────────────────────
# Stub infrastructure (shared with test_free_consumer_c1_c3_guard.py pattern)
# ─────────────────────────────────────────────────────────────────────────────

class _StubTable:
    def __init__(self, rows): self._rows = rows
    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def insert(self, row): self._last = row; return self
    def update(self, *a, **k): return self
    def execute(self):
        class R: pass
        r = R(); r.data = self._rows if self._rows is not None else [{"id": "x"}]
        return r


class _StubSupabase:
    def __init__(self):
        self._auth = [{
            "id": "auth1", "ci_hash": "cihash", "name": "t", "phone": "",
            "free_count": 0, "free_limit": 3, "status": "ACTIVE",
        }]
        self._disc = [{"id": "disc1", "ci_hash": "cihash", "agreed": True}]
        self._ins = [{"id": "res1", "public_token": "tok"}]

    def table(self, name):
        if name == "diagnosis_auth_log":       return _StubTable(self._auth)
        if name == "diagnosis_disclaimer_log": return _StubTable(self._disc)
        if name == "anonymous_diagnosis_results": return _StubTable(self._ins)
        return _StubTable([{"id": "x"}])


_CAPTURED: dict = {}


def _fake_run_step1(supabase, step1_body):
    _CAPTURED["step1_body"] = step1_body
    _CAPTURED["facility"] = build_facility(step1_body)
    return {"status": "success", "data": {"rules_table": [], "applicable_count": 0}}


def _auto_tier(sector, floor_area=0.0, contract_amount_eok=0.0, user_tier=None):
    return {
        "BUILDING": "BUILDING_FREE",
        "INDUSTRIAL": "INDUSTRY_FREE",
        "CONSTRUCTION": "CONSTRUCTION_FREE",
    }.get(sector, "BUILDING_FREE")


def _build_partial(full): return {}
def _now(): return "2026-01-01T00:00:00Z"


_FREE_CODES = frozenset({"BUILDING_FREE", "INDUSTRY_FREE", "CONSTRUCTION_FREE"})
_PRICES: dict = {}


def _run_cst(form_data: dict):
    """Run a CONSTRUCTION diagnosis through the full C1→C3 path."""
    _CAPTURED.clear()
    body = DiagnosisRunBody(
        auth_token="tok",
        disclaimer_log_id="disc1",
        sector="CONSTRUCTION",
        form_data=form_data,
    )
    svc.run_diagnosis(
        supabase=_StubSupabase(),
        body=body,
        run_step1_func=_fake_run_step1,
        auto_tier_func=_auto_tier,
        build_partial_func=_build_partial,
        now_func=_now,
        paid_tier_prices=_PRICES,
        free_tier_codes=_FREE_CODES,
        engine_version="test",
        unified_step1_factory_func=build_unified_leg_input,
    )
    return _CAPTURED.get("facility", {})


# ─────────────────────────────────────────────────────────────────────────────
# A1: appendix3_item_no in _LEG_INPUT_FIELDS
# ─────────────────────────────────────────────────────────────────────────────

def test_A1_appendix3_item_no_in_leg_input_fields():
    """A1: appendix3_item_no registered in transport allowlist for S01 LEG evaluation."""
    assert "appendix3_item_no" in _LEG_INPUT_FIELDS, (
        "appendix3_item_no must be in _LEG_INPUT_FIELDS so S01 CORE22 norms can evaluate it"
    )


# ─────────────────────────────────────────────────────────────────────────────
# A2: CONSTRUCTION missing appendix3_item_no → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_A2_construction_missing_item_no_raises_422():
    """A2: CONSTRUCTION without appendix3_item_no → 422 APPENDIX3_EXPLICIT_CLASSIFICATION_REQUIRED."""
    with pytest.raises(HTTPException) as exc_info:
        _run_cst({"worker_count": 10})
    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert detail.get("code") == "APPENDIX3_EXPLICIT_CLASSIFICATION_REQUIRED"
    assert "appendix3_item_no" in detail.get("missing_fields", [])


def test_A2_construction_missing_item_no_gate():
    """A2: missing_explicit_appendix3_fields returns [appendix3_item_no] for CONSTRUCTION."""
    body = SimpleNamespace(appendix3_item_no=None, form_data={})
    missing = missing_explicit_appendix3_fields(body, "CONSTRUCTION")
    assert missing == ["appendix3_item_no"]


# ─────────────────────────────────────────────────────────────────────────────
# A3: CONSTRUCTION item_no=48 → appendix3 gate PASS
# ─────────────────────────────────────────────────────────────────────────────

def test_A3_construction_item48_passes_appendix3_gate():
    """A3: CONSTRUCTION with appendix3_item_no=48 → appendix3 gate passes, facility reached."""
    fac = _run_cst({"appendix3_item_no": 48})
    # No exception raised — gate passes
    assert fac.get("appendix3_item_no") == 48


def test_A3_construction_item_no_present_gate_pass():
    """A3: missing_explicit_appendix3_fields returns [] when item_no present."""
    body = SimpleNamespace(appendix3_item_no=48, form_data={})
    missing = missing_explicit_appendix3_fields(body, "CONSTRUCTION")
    assert missing == []


# ─────────────────────────────────────────────────────────────────────────────
# A4: CONSTRUCTION item_no=49 → children required
# ─────────────────────────────────────────────────────────────────────────────

def test_A4_item49_children_required_missing():
    """A4: item_no=49 without children → 422 CONSTRUCTION_EXPLICIT_PREDICATE_REQUIRED."""
    with pytest.raises(HTTPException) as exc_info:
        _run_cst({"appendix3_item_no": 49})
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "CONSTRUCTION_EXPLICIT_PREDICATE_REQUIRED"


def test_A4_item49_children_gate():
    """A4: missing_explicit_construction_predicates returns children for item_no=49."""
    body = SimpleNamespace(appendix3_item_no=49, is_relationship_contractor=None,
                           is_civil_construction=None, form_data={})
    missing = missing_explicit_construction_predicates(body, "CONSTRUCTION")
    assert "is_relationship_contractor" in missing
    assert "is_civil_construction" in missing


def test_A4_item49_with_children_passes():
    """A4: item_no=49 + both children → full pipeline PASS."""
    fac = _run_cst({
        "appendix3_item_no": 49,
        "is_relationship_contractor": False,
        "is_civil_construction": False,
    })
    assert fac.get("appendix3_item_no") == 49
    assert fac.get("is_relationship_contractor") is False
    assert fac.get("is_civil_construction") is False


# ─────────────────────────────────────────────────────────────────────────────
# A5: CONSTRUCTION item_no=48 → children NOT required
# ─────────────────────────────────────────────────────────────────────────────

def test_A5_item48_children_not_required():
    """A5: item_no=48 → missing_explicit_construction_predicates returns [] (children not required)."""
    body = SimpleNamespace(appendix3_item_no=48, is_relationship_contractor=None,
                           is_civil_construction=None, form_data={})
    missing = missing_explicit_construction_predicates(body, "CONSTRUCTION")
    assert missing == []


def test_A5_item_not_49_any_value_no_children():
    """A5: item_no=1 → children not required."""
    body = SimpleNamespace(appendix3_item_no=1, is_relationship_contractor=None,
                           is_civil_construction=None, form_data={})
    missing = missing_explicit_construction_predicates(body, "CONSTRUCTION")
    assert missing == []


# ─────────────────────────────────────────────────────────────────────────────
# A6: is_construction now optional (no longer root gate)
# ─────────────────────────────────────────────────────────────────────────────

def test_A6_is_construction_not_required():
    """A6: CONSTRUCTION without is_construction → no gate failure (it's optional now)."""
    fac = _run_cst({"appendix3_item_no": 48})
    assert "is_construction" not in fac  # absent, not required


def test_A6_is_construction_false_preserved():
    """A6: is_construction=False still preserved when explicitly submitted."""
    fac = _run_cst({"appendix3_item_no": 48, "is_construction": False})
    assert fac.get("is_construction") is False


def test_A6_is_construction_true_optional():
    """A6: is_construction=True without children → no child gate (item_no=48 not 49)."""
    fac = _run_cst({"appendix3_item_no": 48, "is_construction": True})
    assert fac.get("is_construction") is True


# ─────────────────────────────────────────────────────────────────────────────
# A7: appendix3_item_no transported as integer to facility (DIRECT_CANONICAL)
# ─────────────────────────────────────────────────────────────────────────────

def test_A7_item_no_48_in_facility():
    """A7: appendix3_item_no=48 appears in facility as exact integer."""
    fac = _run_cst({"appendix3_item_no": 48})
    assert fac.get("appendix3_item_no") == 48
    assert isinstance(fac["appendix3_item_no"], int)


def test_A7_item_no_49_in_facility():
    """A7: appendix3_item_no=49 appears in facility as exact integer."""
    fac = _run_cst({
        "appendix3_item_no": 49,
        "is_relationship_contractor": False,
        "is_civil_construction": False,
    })
    assert fac.get("appendix3_item_no") == 49
    assert isinstance(fac["appendix3_item_no"], int)


def test_A7_missing_item_no_absent_from_facility():
    """A7: missing appendix3_item_no → absent from facility (OMIT, never false)."""
    source_facts = {"worker_count": 10}
    step1 = build_unified_leg_input(sector="CONSTRUCTION", source_facts=source_facts)
    fac = build_facility(step1)
    assert "appendix3_item_no" not in fac


# ─────────────────────────────────────────────────────────────────────────────
# A8: BUILDING/INDUSTRIAL appendix3 gate still requires item_no
# ─────────────────────────────────────────────────────────────────────────────

def test_A8_building_still_requires_item_no():
    """A8: BUILDING without appendix3_item_no → appendix3 gate still fires."""
    body = SimpleNamespace(appendix3_item_no=None, form_data={})
    missing = missing_explicit_appendix3_fields(body, "BUILDING")
    assert missing == ["appendix3_item_no"]


def test_A8_industrial_still_requires_item_no():
    """A8: INDUSTRIAL without appendix3_item_no → appendix3 gate still fires."""
    body = SimpleNamespace(appendix3_item_no=None, form_data={})
    missing = missing_explicit_appendix3_fields(body, "INDUSTRIAL")
    assert missing == ["appendix3_item_no"]


def test_A8_building_item_no_28_passes():
    """A8: BUILDING with item_no=28 → appendix3 gate passes."""
    body = SimpleNamespace(appendix3_item_no=28, form_data={})
    missing = missing_explicit_appendix3_fields(body, "BUILDING")
    assert missing == []


# ─────────────────────────────────────────────────────────────────────────────
# A9: stored_explicit_predicate_body extracts appendix3_item_no for child gate
# ─────────────────────────────────────────────────────────────────────────────

def test_A9_stored_body_extracts_item_no():
    """A9: stored_explicit_predicate_body exposes appendix3_item_no for child gate evaluation."""
    input_data = {
        "appendix3_item_no": 49,
        "is_relationship_contractor": False,
        "is_civil_construction": True,
        "raw_structured_input": {"form_data": {}},
    }
    body = stored_explicit_predicate_body(input_data)
    assert body.appendix3_item_no == 49


def test_A9_stored_body_item_no_49_triggers_children_gate():
    """A9: stored body with item_no=49 → children gate fires (not item_no=48)."""
    input_data = {
        "appendix3_item_no": 49,
        "raw_structured_input": {"form_data": {}},
    }
    body = stored_explicit_predicate_body(input_data)
    missing = missing_explicit_construction_predicates(body, "CONSTRUCTION")
    assert "is_relationship_contractor" in missing


def test_A9_stored_body_item_no_48_no_children_gate():
    """A9: stored body with item_no=48 → children gate does not fire."""
    input_data = {
        "appendix3_item_no": 48,
        "raw_structured_input": {"form_data": {}},
    }
    body = stored_explicit_predicate_body(input_data)
    missing = missing_explicit_construction_predicates(body, "CONSTRUCTION")
    assert missing == []


def test_A9_stored_body_non_int_item_no_ignored():
    """A9: string appendix3_item_no in stored data → treated as None (not int)."""
    input_data = {
        "appendix3_item_no": "49",  # string, not int
        "raw_structured_input": {"form_data": {}},
    }
    body = stored_explicit_predicate_body(input_data)
    assert body.appendix3_item_no is None


# ─────────────────────────────────────────────────────────────────────────────
# A10: GATED_NORMALIZED_SECTORS includes CONSTRUCTION
# ─────────────────────────────────────────────────────────────────────────────

def test_A10_gated_sectors_includes_construction():
    """A10: CONSTRUCTION added to GATED_NORMALIZED_SECTORS for appendix3 completeness gate."""
    assert "CONSTRUCTION" in GATED_NORMALIZED_SECTORS
    assert "BUILDING" in GATED_NORMALIZED_SECTORS
    assert "INDUSTRIAL" in GATED_NORMALIZED_SECTORS


def test_A10_special_facility_not_gated():
    """A10: SPECIAL_FACILITY still not in GATED_NORMALIZED_SECTORS."""
    assert "SPECIAL_FACILITY" not in GATED_NORMALIZED_SECTORS


def test_A10_construction_gate_fires_for_construction_sector():
    """A10: missing_explicit_appendix3_fields fires for CONSTRUCTION (returns field list)."""
    body = SimpleNamespace(appendix3_item_no=None, form_data={})
    result = missing_explicit_appendix3_fields(body, "CONSTRUCTION")
    assert result == ["appendix3_item_no"]
