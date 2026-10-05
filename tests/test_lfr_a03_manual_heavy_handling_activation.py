"""WO-LFR-OBJ-A03-FAST-01 — A03 manual-heavy-handling activation contract.

T1: parent TRUE preserved
T2: parent FALSE preserved (missing != false)
T3: parent absent → key absent
T4: normal weight preserved
T5: weight zero preserved (0 != absent)
T6: parent TRUE + weight zero → both preserved
T7: child present, parent absent → parent not inferred
T8: child None → key absent
"""
from __future__ import annotations

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
    inp = _step1({"has_manual_heavy_handling": True})
    assert inp.get("has_manual_heavy_handling") is True


# ── T2: parent FALSE preserved ────────────────────────────────────────────────
def test_T2_parent_false_preserved():
    inp = _step1({"has_manual_heavy_handling": False})
    assert "has_manual_heavy_handling" in inp
    assert inp["has_manual_heavy_handling"] is False


# ── T3: parent absent → key absent (missing != false) ─────────────────────────
def test_T3_parent_absent_yields_absent():
    inp = _step1({})
    assert "has_manual_heavy_handling" not in inp


# ── T4: normal weight preserved ───────────────────────────────────────────────
def test_T4_weight_normal_value_preserved():
    inp = _step1({"manual_handling_weight_kg": 25})
    assert inp.get("manual_handling_weight_kg") == 25


# ── T5: weight zero preserved (0 != absent) ──────────────────────────────────
def test_T5_weight_zero_preserved():
    inp = _step1({"manual_handling_weight_kg": 0})
    assert "manual_handling_weight_kg" in inp
    assert inp["manual_handling_weight_kg"] == 0


# ── T6: parent TRUE + weight zero → both preserved ───────────────────────────
def test_T6_parent_true_and_weight_zero_both_preserved():
    inp = _step1({"has_manual_heavy_handling": True, "manual_handling_weight_kg": 0})
    assert inp.get("has_manual_heavy_handling") is True
    assert "manual_handling_weight_kg" in inp
    assert inp["manual_handling_weight_kg"] == 0


# ── T7: child present, parent absent → parent not inferred ───────────────────
def test_T7_child_present_parent_not_inferred():
    inp = _step1({"manual_handling_weight_kg": 20})
    assert inp.get("manual_handling_weight_kg") == 20
    assert "has_manual_heavy_handling" not in inp


# ── T8: child None → key absent ──────────────────────────────────────────────
def test_T8_child_none_yields_absent():
    inp = _step1({"manual_handling_weight_kg": None})
    assert "manual_handling_weight_kg" not in inp
