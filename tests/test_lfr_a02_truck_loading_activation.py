"""WO-LFR-OBJ-A02-FAST-01 — A02 truck-loading activation contract.

T1: parent TRUE preserved
T2: parent FALSE preserved (missing != false)
T3: parent absent → key absent
T4: child height normal value preserved
T5: child height zero preserved (0 != absent)
T6: parent TRUE + height zero → both preserved
T7: child present, parent absent → parent not inferred
T8: child None → key absent
"""
from __future__ import annotations

import pytest

from services.canonical.saas_leg_source_adapter import build_saas_leg_step1


def _step1(source_facts: dict) -> dict:
    result = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts=source_facts,
        factory_id="F1",
    )
    return result.input or {}


# ── T1: parent TRUE ───────────────────────────────────────────────────────────
def test_T1_parent_true_preserved():
    inp = _step1({"has_truck_loading_unloading": True})
    assert inp.get("has_truck_loading_unloading") is True


# ── T2: parent FALSE preserved ────────────────────────────────────────────────
def test_T2_parent_false_preserved():
    inp = _step1({"has_truck_loading_unloading": False})
    assert "has_truck_loading_unloading" in inp
    assert inp["has_truck_loading_unloading"] is False


# ── T3: parent absent → key absent (missing != false) ─────────────────────────
def test_T3_parent_absent_yields_absent():
    inp = _step1({})
    assert "has_truck_loading_unloading" not in inp


# ── T4: child height normal value preserved ───────────────────────────────────
def test_T4_height_normal_value_preserved():
    inp = _step1({"truck_loading_height_m": 1.5})
    assert inp.get("truck_loading_height_m") == 1.5


# ── T5: child height zero preserved (0 != absent) ────────────────────────────
def test_T5_height_zero_preserved():
    inp = _step1({"truck_loading_height_m": 0})
    assert "truck_loading_height_m" in inp
    assert inp["truck_loading_height_m"] == 0


# ── T6: parent TRUE + height zero → both preserved ───────────────────────────
def test_T6_parent_true_and_height_zero_both_preserved():
    inp = _step1({"has_truck_loading_unloading": True, "truck_loading_height_m": 0})
    assert inp.get("has_truck_loading_unloading") is True
    assert "truck_loading_height_m" in inp
    assert inp["truck_loading_height_m"] == 0


# ── T7: child present, parent absent → parent not inferred ───────────────────
def test_T7_child_present_parent_not_inferred():
    inp = _step1({"truck_loading_height_m": 2.0})
    assert inp.get("truck_loading_height_m") == 2.0
    assert "has_truck_loading_unloading" not in inp


# ── T8: child None → key absent ──────────────────────────────────────────────
def test_T8_child_none_yields_absent():
    inp = _step1({"truck_loading_height_m": None})
    assert "truck_loading_height_m" not in inp
