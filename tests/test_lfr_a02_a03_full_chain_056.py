"""WO-LFR-A02-A03-FASTTRACK-056 — A02/A03 full chain integration test.

Verifies: consumer input → build_facility → LEG facility dict
for all 3 sectors (INDUSTRIAL / CONSTRUCTION / BUILDING).

A02: has_truck_loading_unloading (parent) + truck_loading_height_m (detail)
A03: has_manual_heavy_handling (parent) + manual_handling_weight_kg (detail)

Distinguishes from unit tests:
  - Unit (test_lfr_a02_truck_loading_activation.py / test_lfr_a03_manual_heavy_handling_activation.py):
      build_saas_leg_step1 merge/projection logic, INDUSTRIAL only
  - This file: SafeConsumerInput → build_facility → LEG facility presence
    (LEG atom evaluation covered by test_lfr_a02_a03_atom_matrix_056.py in engine repo)

SOURCE CHANGE = 0 / DB WRITE = 0 / DEPLOY = 0
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from clients.leg_runtime_client import build_facility
from schemas.legal_engine import (
    SafeIndustrialConsumerInput,
    SafeConstructionConsumerInput,
    SafeBuildingConsumerInput,
)
from services.canonical.leg_input_contract import build_unified_leg_input


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ind(*, has_truck=None, truck_height=None, has_manual=None, manual_weight=None):
    consumer = SafeIndustrialConsumerInput(
        has_truck_loading_unloading=has_truck,
        truck_loading_height_m=truck_height,
        has_manual_heavy_handling=has_manual,
        manual_handling_weight_kg=manual_weight,
    )
    overrides = consumer.model_dump(exclude_none=True)
    step1 = build_unified_leg_input(sector="INDUSTRIAL", source_facts=dict(overrides))
    return build_facility(step1)


def _cst(*, has_truck=None, truck_height=None, has_manual=None, manual_weight=None):
    consumer = SafeConstructionConsumerInput(
        has_truck_loading_unloading=has_truck,
        truck_loading_height_m=truck_height,
        has_manual_heavy_handling=has_manual,
        manual_handling_weight_kg=manual_weight,
    )
    overrides = consumer.model_dump(exclude_none=True)
    step1 = build_unified_leg_input(sector="CONSTRUCTION", source_facts=dict(overrides))
    return build_facility(step1)


def _bld(*, has_truck=None, truck_height=None, has_manual=None, manual_weight=None):
    consumer = SafeBuildingConsumerInput(
        has_truck_loading_unloading=has_truck,
        truck_loading_height_m=truck_height,
        has_manual_heavy_handling=has_manual,
        manual_handling_weight_kg=manual_weight,
    )
    overrides = consumer.model_dump(exclude_none=True)
    step1 = build_unified_leg_input(sector="BUILDING", source_facts=dict(overrides))
    return build_facility(step1)


# ── A02: INDUSTRIAL ──────────────────────────────────────────────────────────

def test_ind_a02_parent_true_in_facility():
    fac = _ind(has_truck=True)
    assert fac.get("has_truck_loading_unloading") is True


def test_ind_a02_parent_false_preserved_in_facility():
    fac = _ind(has_truck=False)
    assert "has_truck_loading_unloading" in fac
    assert fac["has_truck_loading_unloading"] is False


def test_ind_a02_parent_absent_from_facility():
    fac = _ind()
    assert "has_truck_loading_unloading" not in fac


def test_ind_a02_detail_value_in_facility():
    fac = _ind(has_truck=True, truck_height=2.0)
    assert fac.get("truck_loading_height_m") == 2.0


def test_ind_a02_detail_zero_preserved():
    """0.0 != ABSENT — preserved in facility."""
    fac = _ind(has_truck=True, truck_height=0.0)
    assert "truck_loading_height_m" in fac
    assert fac["truck_loading_height_m"] == 0.0


def test_ind_a02_detail_without_parent_schema_rejects():
    """detail without parent → ValidationError (FF-06 _parent_detail_consistency)."""
    with pytest.raises(ValidationError):
        SafeIndustrialConsumerInput(truck_loading_height_m=2.0)


def test_ind_a02_detail_absent_from_facility():
    fac = _ind()
    assert "truck_loading_height_m" not in fac


def test_ind_a02_parent_true_and_detail_present():
    fac = _ind(has_truck=True, truck_height=2.0)
    assert fac.get("has_truck_loading_unloading") is True
    assert fac.get("truck_loading_height_m") == 2.0


# ── A03: INDUSTRIAL ──────────────────────────────────────────────────────────

def test_ind_a03_parent_true_in_facility():
    fac = _ind(has_manual=True)
    assert fac.get("has_manual_heavy_handling") is True


def test_ind_a03_parent_false_preserved_in_facility():
    fac = _ind(has_manual=False)
    assert "has_manual_heavy_handling" in fac
    assert fac["has_manual_heavy_handling"] is False


def test_ind_a03_parent_absent_from_facility():
    fac = _ind()
    assert "has_manual_heavy_handling" not in fac


def test_ind_a03_detail_value_in_facility():
    fac = _ind(has_manual=True, manual_weight=25.0)
    assert fac.get("manual_handling_weight_kg") == 25.0


def test_ind_a03_detail_zero_preserved():
    """0.0 != ABSENT — preserved in facility."""
    fac = _ind(has_manual=True, manual_weight=0.0)
    assert "manual_handling_weight_kg" in fac
    assert fac["manual_handling_weight_kg"] == 0.0


def test_ind_a03_detail_absent_from_facility():
    fac = _ind()
    assert "manual_handling_weight_kg" not in fac


# ── A02: CONSTRUCTION ────────────────────────────────────────────────────────

def test_cst_a02_parent_true_in_facility():
    fac = _cst(has_truck=True)
    assert fac.get("has_truck_loading_unloading") is True


def test_cst_a02_parent_false_preserved_in_facility():
    fac = _cst(has_truck=False)
    assert "has_truck_loading_unloading" in fac
    assert fac["has_truck_loading_unloading"] is False


def test_cst_a02_parent_absent_from_facility():
    fac = _cst()
    assert "has_truck_loading_unloading" not in fac


def test_cst_a02_detail_value_in_facility():
    fac = _cst(has_truck=True, truck_height=1.9)
    assert fac.get("truck_loading_height_m") == 1.9


def test_cst_a02_detail_zero_preserved():
    fac = _cst(has_truck=True, truck_height=0.0)
    assert "truck_loading_height_m" in fac
    assert fac["truck_loading_height_m"] == 0.0


def test_cst_a03_parent_true_in_facility():
    fac = _cst(has_manual=True)
    assert fac.get("has_manual_heavy_handling") is True


def test_cst_a03_detail_value_in_facility():
    fac = _cst(has_manual=True, manual_weight=5.0)
    assert fac.get("manual_handling_weight_kg") == 5.0


def test_cst_a03_detail_zero_preserved():
    fac = _cst(has_manual=True, manual_weight=0.0)
    assert "manual_handling_weight_kg" in fac
    assert fac["manual_handling_weight_kg"] == 0.0


# ── A02: BUILDING ─────────────────────────────────────────────────────────────

def test_bld_a02_parent_true_in_facility():
    fac = _bld(has_truck=True)
    assert fac.get("has_truck_loading_unloading") is True


def test_bld_a02_parent_false_preserved_in_facility():
    fac = _bld(has_truck=False)
    assert "has_truck_loading_unloading" in fac
    assert fac["has_truck_loading_unloading"] is False


def test_bld_a02_parent_absent_from_facility():
    fac = _bld()
    assert "has_truck_loading_unloading" not in fac


def test_bld_a02_detail_value_in_facility():
    fac = _bld(has_truck=True, truck_height=2.0)
    assert fac.get("truck_loading_height_m") == 2.0


def test_bld_a02_detail_zero_preserved():
    fac = _bld(has_truck=True, truck_height=0.0)
    assert "truck_loading_height_m" in fac
    assert fac["truck_loading_height_m"] == 0.0


def test_bld_a03_parent_true_in_facility():
    fac = _bld(has_manual=True)
    assert fac.get("has_manual_heavy_handling") is True


def test_bld_a03_detail_value_in_facility():
    fac = _bld(has_manual=True, manual_weight=10.0)
    assert fac.get("manual_handling_weight_kg") == 10.0


def test_bld_a03_detail_zero_preserved():
    fac = _bld(has_manual=True, manual_weight=0.0)
    assert "manual_handling_weight_kg" in fac
    assert fac["manual_handling_weight_kg"] == 0.0


# ── Cross-sector parity ───────────────────────────────────────────────────────

def test_all_sectors_a02_parent_true_parity():
    """All 3 sectors deliver has_truck_loading_unloading=True identically."""
    assert _ind(has_truck=True).get("has_truck_loading_unloading") is True
    assert _cst(has_truck=True).get("has_truck_loading_unloading") is True
    assert _bld(has_truck=True).get("has_truck_loading_unloading") is True


def test_all_sectors_a02_parent_false_parity():
    """All 3 sectors preserve FALSE for has_truck_loading_unloading."""
    for fac in [_ind(has_truck=False), _cst(has_truck=False), _bld(has_truck=False)]:
        assert "has_truck_loading_unloading" in fac
        assert fac["has_truck_loading_unloading"] is False


def test_all_sectors_a02_absent_parity():
    """All 3 sectors omit has_truck_loading_unloading when not provided."""
    assert "has_truck_loading_unloading" not in _ind()
    assert "has_truck_loading_unloading" not in _cst()
    assert "has_truck_loading_unloading" not in _bld()


def test_all_sectors_a03_parent_true_parity():
    """All 3 sectors deliver has_manual_heavy_handling=True identically."""
    assert _ind(has_manual=True).get("has_manual_heavy_handling") is True
    assert _cst(has_manual=True).get("has_manual_heavy_handling") is True
    assert _bld(has_manual=True).get("has_manual_heavy_handling") is True


def test_all_sectors_a02_detail_zero_parity():
    """All 3 sectors preserve 0 for truck_loading_height_m (0 != absent)."""
    for fac in [_ind(has_truck=True, truck_height=0.0), _cst(has_truck=True, truck_height=0.0), _bld(has_truck=True, truck_height=0.0)]:
        assert "truck_loading_height_m" in fac
        assert fac["truck_loading_height_m"] == 0.0


def test_all_sectors_a03_detail_zero_parity():
    """All 3 sectors preserve 0 for manual_handling_weight_kg (0 != absent)."""
    for fac in [_ind(has_manual=True, manual_weight=0.0), _cst(has_manual=True, manual_weight=0.0), _bld(has_manual=True, manual_weight=0.0)]:
        assert "manual_handling_weight_kg" in fac
        assert fac["manual_handling_weight_kg"] == 0.0


def test_all_sectors_both_parent_and_detail_present():
    """All 3 sectors carry both parent+detail simultaneously."""
    for fac in [
        _ind(has_truck=True, truck_height=2.0, has_manual=True, manual_weight=5.0),
        _cst(has_truck=True, truck_height=2.0, has_manual=True, manual_weight=5.0),
        _bld(has_truck=True, truck_height=2.0, has_manual=True, manual_weight=5.0),
    ]:
        assert fac.get("has_truck_loading_unloading") is True
        assert fac.get("truck_loading_height_m") == 2.0
        assert fac.get("has_manual_heavy_handling") is True
        assert fac.get("manual_handling_weight_kg") == 5.0
