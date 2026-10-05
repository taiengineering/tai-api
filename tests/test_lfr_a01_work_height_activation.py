"""WO-LFR-OBJ-A01-IMPLEMENT-01 — A01b tri-state aggregation + A01a independence.

B1-B9: performs_work_with_fall_risk multi-row aggregation (LFR-013 §8-3).
A1-A4: work_height_m (A01a) independence from A01b.
D1:    downstream FALSE transport through merge pipeline.
C1-C2: explicit/projected conflict detection.
"""
from __future__ import annotations

import pytest

from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
from services.work_source.merge import (
    WorkSourceMergeConflict,
    merge_or_raise,
    merge_projected_into_facts,
)
from services.work_source.projector import project_work_row, project_work_rows


def _hp(**attrs_kwargs) -> dict:
    """Active HIGH_PLACE row with given attributes."""
    return {
        "work_type": "HIGH_PLACE",
        "work_subtype": None,
        "attributes": attrs_kwargs,
        "active": True,
    }


def _hp_inactive(**attrs_kwargs) -> dict:
    return {**_hp(**attrs_kwargs), "active": False}


def _row(work_type: str = "FORKLIFT", **kwargs) -> dict:
    base = {"work_type": work_type, "work_subtype": None, "attributes": {}, "active": True}
    base.update(kwargs)
    return base


# ── B1: ANY explicit TRUE → TRUE ─────────────────────────────────────────────
def test_B1_single_true_row_yields_true():
    result = project_work_rows([_hp(fall_risk=True)])
    assert result.get("performs_work_with_fall_risk") is True


def test_B1_multi_true_rows_yields_true():
    result = project_work_rows([_hp(fall_risk=True), _hp(fall_risk=True)])
    assert result.get("performs_work_with_fall_risk") is True


# ── B2: FALSE + TRUE → TRUE ───────────────────────────────────────────────────
def test_B2_false_plus_true_yields_true():
    result = project_work_rows([_hp(fall_risk=False), _hp(fall_risk=True)])
    assert result.get("performs_work_with_fall_risk") is True


def test_B2_true_first_then_false_yields_true():
    result = project_work_rows([_hp(fall_risk=True), _hp(fall_risk=False)])
    assert result.get("performs_work_with_fall_risk") is True


# ── B3: ALL explicit FALSE → FALSE ────────────────────────────────────────────
def test_B3_single_false_row_yields_false():
    result = project_work_rows([_hp(fall_risk=False)])
    assert result.get("performs_work_with_fall_risk") is False


def test_B3_all_false_rows_yield_false():
    result = project_work_rows([_hp(fall_risk=False), _hp(fall_risk=False)])
    assert result.get("performs_work_with_fall_risk") is False


# ── B4: FALSE + MISSING → UNKNOWN (absent) ───────────────────────────────────
def test_B4_false_plus_missing_attr_yields_absent():
    result = project_work_rows([_hp(fall_risk=False), _hp()])
    assert "performs_work_with_fall_risk" not in result


# ── B5: FALSE + NULL → UNKNOWN (absent) ──────────────────────────────────────
def test_B5_false_plus_null_fall_risk_yields_absent():
    result = project_work_rows([_hp(fall_risk=False), _hp(fall_risk=None)])
    assert "performs_work_with_fall_risk" not in result


# ── B6: ALL MISSING → UNKNOWN (absent) ───────────────────────────────────────
def test_B6_all_missing_fall_risk_yields_absent():
    result = project_work_rows([_hp()])
    assert "performs_work_with_fall_risk" not in result


def test_B6_multi_missing_fall_risk_yields_absent():
    result = project_work_rows([_hp(), _hp()])
    assert "performs_work_with_fall_risk" not in result


# ── B7: NO HIGH_PLACE rows → UNKNOWN (absent) ────────────────────────────────
def test_B7_no_high_place_rows_yields_absent():
    result = project_work_rows([_row("FORKLIFT")])
    assert "performs_work_with_fall_risk" not in result


def test_B7_empty_rows_yields_absent():
    result = project_work_rows([])
    assert "performs_work_with_fall_risk" not in result


def test_B7_none_rows_yields_absent():
    result = project_work_rows(None)
    assert "performs_work_with_fall_risk" not in result


# ── B8: inactive HIGH_PLACE rows ignored ────────────────────────────────────
def test_B8_inactive_true_row_yields_absent():
    result = project_work_rows([_hp_inactive(fall_risk=True)])
    assert "performs_work_with_fall_risk" not in result


def test_B8_inactive_false_row_yields_absent_not_false():
    result = project_work_rows([_hp_inactive(fall_risk=False)])
    assert "performs_work_with_fall_risk" not in result


def test_B8_inactive_and_active_false_yields_false():
    # Only active rows counted; inactive ignored; all active rows are False → FALSE
    result = project_work_rows([_hp_inactive(fall_risk=True), _hp(fall_risk=False)])
    assert result.get("performs_work_with_fall_risk") is False


# ── B9: unrelated work type does not affect A01b ────────────────────────────
def test_B9_unrelated_work_type_does_not_produce_fall_risk():
    result = project_work_rows([_row("FORKLIFT"), _row("EXCAVATION", attributes={"uses_machinery": True})])
    assert "performs_work_with_fall_risk" not in result


def test_B9_mixed_types_a01b_follows_high_place_only():
    # FORKLIFT row doesn't count toward A01b; only HIGH_PLACE false row does
    result = project_work_rows([_row("FORKLIFT"), _hp(fall_risk=False)])
    assert result.get("performs_work_with_fall_risk") is False
    assert result.get("uses_forklift") is True


# ── A1: A01a (work_height_m) not emitted by projector regardless of fall_risk ─
def test_A1_fall_risk_true_does_not_emit_work_height_m():
    result = project_work_rows([_hp(fall_risk=True)])
    assert "work_height_m" not in result


def test_A1_fall_risk_false_does_not_emit_work_height_m():
    result = project_work_rows([_hp(fall_risk=False)])
    assert "work_height_m" not in result


# ── A2: A01b result does not gate or block work_height_m in merge ────────────
def test_A2_a01b_false_does_not_block_explicit_work_height_m():
    # A01b=FALSE projected, explicit has work_height_m=10 → no conflict, 10 preserved
    rows = [_hp(fall_risk=False)]
    merged, conflicts = merge_projected_into_facts(
        explicit={"work_height_m": 10},
        work_rows=rows,
    )
    assert merged["work_height_m"] == 10
    assert merged.get("performs_work_with_fall_risk") is False
    assert not conflicts


def test_A2_a01b_true_does_not_block_explicit_work_height_m():
    rows = [_hp(fall_risk=True)]
    merged, conflicts = merge_projected_into_facts(
        explicit={"work_height_m": 5},
        work_rows=rows,
    )
    assert merged["work_height_m"] == 5
    assert merged.get("performs_work_with_fall_risk") is True
    assert not conflicts


# ── A3: A01a is independent: no HIGH_PLACE rows → work_height_m still passthrough
def test_A3_no_high_place_rows_work_height_m_preserved():
    merged, conflicts = merge_projected_into_facts(
        explicit={"work_height_m": 3.5},
        work_rows=[],
    )
    assert merged["work_height_m"] == 3.5
    assert not conflicts


# ── A4: work_height_m=0 is a resolved value (not absent); preserved through merge
def test_A4_work_height_m_zero_preserved_through_merge():
    merged, conflicts = merge_projected_into_facts(
        explicit={"work_height_m": 0},
        work_rows=[_hp(fall_risk=False)],
    )
    assert merged["work_height_m"] == 0
    assert merged.get("performs_work_with_fall_risk") is False
    assert not conflicts


# ── D1: downstream FALSE transport through merge pipeline ────────────────────
def test_D1_false_transport_through_merge_projected_into_facts():
    rows = [_hp(fall_risk=False)]
    merged, conflicts = merge_projected_into_facts(explicit={}, work_rows=rows)
    assert merged.get("performs_work_with_fall_risk") is False
    assert not conflicts


def test_D1_false_transport_merge_or_raise_no_conflict():
    rows = [_hp(fall_risk=False)]
    merged = merge_or_raise(explicit={}, work_rows=rows)
    assert merged.get("performs_work_with_fall_risk") is False


# ── C1: explicit TRUE + projected FALSE → WorkSourceMergeConflict ────────────
def test_C1_explicit_true_projected_false_raises_conflict():
    with pytest.raises(WorkSourceMergeConflict) as exc_info:
        merge_or_raise(
            explicit={"performs_work_with_fall_risk": True},
            work_rows=[_hp(fall_risk=False)],
        )
    conflict = exc_info.value.conflicts[0]
    assert conflict["field"] == "performs_work_with_fall_risk"
    assert conflict["explicit"] is True
    assert conflict["projected"] is False


# ── C2: explicit FALSE + projected TRUE → WorkSourceMergeConflict ────────────
def test_C2_explicit_false_projected_true_raises_conflict():
    with pytest.raises(WorkSourceMergeConflict) as exc_info:
        merge_or_raise(
            explicit={"performs_work_with_fall_risk": False},
            work_rows=[_hp(fall_risk=True)],
        )
    conflict = exc_info.value.conflicts[0]
    assert conflict["field"] == "performs_work_with_fall_risk"
    assert conflict["explicit"] is False
    assert conflict["projected"] is True


def test_C2_no_conflict_when_explicit_and_projected_agree_true():
    result = merge_or_raise(
        explicit={"performs_work_with_fall_risk": True},
        work_rows=[_hp(fall_risk=True)],
    )
    assert result.get("performs_work_with_fall_risk") is True


def test_C2_no_conflict_when_explicit_and_projected_agree_false():
    result = merge_or_raise(
        explicit={"performs_work_with_fall_risk": False},
        work_rows=[_hp(fall_risk=False)],
    )
    assert result.get("performs_work_with_fall_risk") is False


# ── D2: FALSE survives full SaaS LEG adapter chain ───────────────────────────
def test_D2_false_survives_full_saas_leg_adapter_chain():
    rows = [_hp(fall_risk=False)]
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts={},
        factory_id="F1",
        work_rows=rows,
    )
    assert "performs_work_with_fall_risk" in step1.input
    assert step1.input["performs_work_with_fall_risk"] is False
