"""WO-LFR-OBJ-B01-FAST-01 — B01 performance/assembly basement contract.

B1:  parent1 TRUE preserved
B2:  parent1 FALSE preserved
B3:  parent2 TRUE preserved
B4:  parent2 FALSE preserved
B5:  both parents absent
B6:  child normal numeric preserved
B7:  child zero preserved (0 != absent)
B8:  all TRUE + child → all three preserved
B9:  child present, parents absent → parents not inferred
B10: child None → key absent
"""
from __future__ import annotations

from services.canonical.saas_leg_source_adapter import build_saas_leg_step1


def _step1(source_facts: dict) -> dict:
    result = build_saas_leg_step1(
        sector="BUILDING",
        source_facts=source_facts,
        factory_id="F1",
    )
    return result.input or {}


# ── B1: parent1 TRUE ──────────────────────────────────────────────────────────
def test_B1_parent1_true_preserved():
    inp = _step1({"has_performance_assembly_use": True})
    assert inp.get("has_performance_assembly_use") is True


# ── B2: parent1 FALSE preserved ───────────────────────────────────────────────
def test_B2_parent1_false_preserved():
    inp = _step1({"has_performance_assembly_use": False})
    assert "has_performance_assembly_use" in inp
    assert inp["has_performance_assembly_use"] is False


# ── B3: parent2 TRUE ──────────────────────────────────────────────────────────
def test_B3_parent2_true_preserved():
    inp = _step1({"is_target_facility_in_basement": True})
    assert inp.get("is_target_facility_in_basement") is True


# ── B4: parent2 FALSE preserved ───────────────────────────────────────────────
def test_B4_parent2_false_preserved():
    inp = _step1({"is_target_facility_in_basement": False})
    assert "is_target_facility_in_basement" in inp
    assert inp["is_target_facility_in_basement"] is False


# ── B5: both parents absent ───────────────────────────────────────────────────
def test_B5_both_parents_absent():
    inp = _step1({})
    assert "has_performance_assembly_use" not in inp
    assert "is_target_facility_in_basement" not in inp


# ── B6: child normal numeric ──────────────────────────────────────────────────
def test_B6_child_normal_value_preserved():
    inp = _step1({"performance_use_floor_area_sum": 1500})
    assert inp.get("performance_use_floor_area_sum") == 1500


# ── B7: child zero preserved (0 != absent) ────────────────────────────────────
def test_B7_child_zero_preserved():
    inp = _step1({"performance_use_floor_area_sum": 0})
    assert "performance_use_floor_area_sum" in inp
    assert inp["performance_use_floor_area_sum"] == 0


# ── B8: all TRUE + child → all three preserved ───────────────────────────────
def test_B8_all_true_and_child_all_preserved():
    inp = _step1({
        "has_performance_assembly_use": True,
        "is_target_facility_in_basement": True,
        "performance_use_floor_area_sum": 1200,
    })
    assert inp.get("has_performance_assembly_use") is True
    assert inp.get("is_target_facility_in_basement") is True
    assert inp.get("performance_use_floor_area_sum") == 1200


# ── B9: child present → parents not inferred ─────────────────────────────────
def test_B9_child_present_parents_not_inferred():
    inp = _step1({"performance_use_floor_area_sum": 500})
    assert inp.get("performance_use_floor_area_sum") == 500
    assert "has_performance_assembly_use" not in inp
    assert "is_target_facility_in_basement" not in inp


# ── B10: child None → key absent ─────────────────────────────────────────────
def test_B10_child_none_yields_absent():
    inp = _step1({"performance_use_floor_area_sum": None})
    assert "performance_use_floor_area_sum" not in inp
