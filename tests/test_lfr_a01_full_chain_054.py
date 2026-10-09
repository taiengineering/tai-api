"""WO-LFR-FF04A-VERIFY-054 — A01 full chain integration test.

Verifies: front payload → build_facility → LEG facility dict
for all 3 sectors (INDUSTRIAL / CONSTRUCTION / BUILDING).

Distinguishes from unit tests:
  - Unit (test_lfr_a01_work_height_activation.py): merge/projection logic
  - This file: consumer schema → build_facility → LEG input presence
    (LEG atom evaluation covered by test_lfr_a01_atom_matrix_054.py in engine repo)

SOURCE CHANGE = 0 / DB WRITE = 0 / DEPLOY = 0
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from clients.leg_runtime_client import build_facility
from schemas.diagnosis_integrated import DiagnosisRunBody
from schemas.legal_engine import (
    DiagnoseStep1Body,
    SafeIndustrialConsumerInput,
    SafeConstructionConsumerInput,
    SafeBuildingConsumerInput,
)
from services.canonical.leg_input_contract import build_unified_leg_input


# ── Helpers ───────────────────────────────────────────────────────────────────

def _industrial_facility(work_height_m):
    """Simulate INDUSTRIAL consumer input → build_facility."""
    consumer = SafeIndustrialConsumerInput(work_height_m=work_height_m)
    overrides = consumer.model_dump(exclude_none=True)
    source_facts = dict(overrides)
    step1 = build_unified_leg_input(sector="INDUSTRIAL", source_facts=source_facts)
    return build_facility(step1)


def _construction_facility(work_height_m):
    """Simulate CONSTRUCTION consumer input → build_facility."""
    consumer = SafeConstructionConsumerInput(work_height_m=work_height_m)
    overrides = consumer.model_dump(exclude_none=True)
    source_facts = dict(overrides)
    step1 = build_unified_leg_input(sector="CONSTRUCTION", source_facts=source_facts)
    return build_facility(step1)


def _building_facility(work_height_m):
    """Simulate BUILDING consumer input → build_facility."""
    consumer = SafeBuildingConsumerInput(work_height_m=work_height_m)
    overrides = consumer.model_dump(exclude_none=True)
    source_facts = dict(overrides)
    step1 = build_unified_leg_input(sector="BUILDING", source_facts=source_facts)
    return build_facility(step1)


# ── INDUSTRIAL: work_height_m → facility ─────────────────────────────────────

def test_ind_height_20_in_facility():
    """I1: INDUSTRIAL work_height_m=2.0 → facility includes 2.0."""
    fac = _industrial_facility(2.0)
    assert fac.get("work_height_m") == 2.0


def test_ind_height_19_in_facility():
    """I2: INDUSTRIAL work_height_m=1.9 → facility includes 1.9."""
    fac = _industrial_facility(1.9)
    assert fac.get("work_height_m") == 1.9


def test_ind_height_zero_preserved():
    """I3: INDUSTRIAL work_height_m=0 → 0 preserved (0 != ABSENT)."""
    fac = _industrial_facility(0.0)
    assert "work_height_m" in fac
    assert fac["work_height_m"] == 0.0


def test_ind_height_35_in_facility():
    """I4: INDUSTRIAL work_height_m=3.5 → facility includes 3.5."""
    fac = _industrial_facility(3.5)
    assert fac.get("work_height_m") == 3.5


def test_ind_height_negative_rejected_by_schema():
    """I5: INDUSTRIAL work_height_m=-1.0 → ValidationError (FF-06 _non_negative_finite rejects)."""
    with pytest.raises(ValidationError):
        SafeIndustrialConsumerInput(work_height_m=-1.0)


def test_ind_height_absent():
    """I6: INDUSTRIAL work_height_m=None → absent from facility (UNKNOWN in LEG)."""
    fac = _industrial_facility(None)
    assert "work_height_m" not in fac


# ── CONSTRUCTION: work_height_m → facility ───────────────────────────────────

def test_cst_height_20_in_facility():
    """C1: CONSTRUCTION work_height_m=2.0 → facility includes 2.0."""
    fac = _construction_facility(2.0)
    assert fac.get("work_height_m") == 2.0


def test_cst_height_19_in_facility():
    """C2: CONSTRUCTION work_height_m=1.9 → facility includes 1.9."""
    fac = _construction_facility(1.9)
    assert fac.get("work_height_m") == 1.9


def test_cst_height_zero_preserved():
    """C3: CONSTRUCTION work_height_m=0 → 0 preserved (0 != ABSENT)."""
    fac = _construction_facility(0.0)
    assert "work_height_m" in fac
    assert fac["work_height_m"] == 0.0


def test_cst_height_35_in_facility():
    """C4: CONSTRUCTION work_height_m=3.5 → facility includes 3.5."""
    fac = _construction_facility(3.5)
    assert fac.get("work_height_m") == 3.5


def test_cst_height_absent():
    """C5: CONSTRUCTION work_height_m=None → absent from facility (UNKNOWN in LEG)."""
    fac = _construction_facility(None)
    assert "work_height_m" not in fac


# ── BUILDING: work_height_m → facility ───────────────────────────────────────

def test_bld_height_20_in_facility():
    """B1: BUILDING work_height_m=2.0 → facility includes 2.0."""
    fac = _building_facility(2.0)
    assert fac.get("work_height_m") == 2.0


def test_bld_height_19_in_facility():
    """B2: BUILDING work_height_m=1.9 → facility includes 1.9."""
    fac = _building_facility(1.9)
    assert fac.get("work_height_m") == 1.9


def test_bld_height_zero_preserved():
    """B3: BUILDING work_height_m=0 → 0 preserved (0 != ABSENT)."""
    fac = _building_facility(0.0)
    assert "work_height_m" in fac
    assert fac["work_height_m"] == 0.0


def test_bld_height_35_in_facility():
    """B4: BUILDING work_height_m=3.5 → facility includes 3.5."""
    fac = _building_facility(3.5)
    assert fac.get("work_height_m") == 3.5


def test_bld_height_absent():
    """B5: BUILDING work_height_m=None → absent from facility (UNKNOWN in LEG)."""
    fac = _building_facility(None)
    assert "work_height_m" not in fac


# ── Cross-sector parity ───────────────────────────────────────────────────────

def test_all_sectors_20_parity():
    """X1: All 3 sectors deliver work_height_m=2.0 identically to LEG."""
    val = 2.0
    assert _industrial_facility(val).get("work_height_m") == val
    assert _construction_facility(val).get("work_height_m") == val
    assert _building_facility(val).get("work_height_m") == val


def test_all_sectors_absent_parity():
    """X2: All 3 sectors omit work_height_m when not provided."""
    assert "work_height_m" not in _industrial_facility(None)
    assert "work_height_m" not in _construction_facility(None)
    assert "work_height_m" not in _building_facility(None)


def test_all_sectors_zero_parity():
    """X3: All 3 sectors preserve 0 (0 != absent) in facility."""
    for fac in [_industrial_facility(0.0), _construction_facility(0.0), _building_facility(0.0)]:
        assert "work_height_m" in fac
        assert fac["work_height_m"] == 0.0
