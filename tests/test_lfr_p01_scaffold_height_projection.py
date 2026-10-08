"""WO-LFR-OBJ-P01-C2-PROJECTION-IMPLEMENT-015 — scaffold_height_m C2 projection tests.

P01-T1 through P01-T10: single-row valid, zero, missing, invalid, multi-row, inactive,
mixed, end-to-end adapter (T9/T10).

Source atoms:
  5792aae3-bbc9-5448-a4d4-b509690dadf0
  69b81031-8f4c-5cba-8660-7b7063e7ddf1
Published runtime norm: 0ddbaec7-2a05-5c80-98e4-439301afe77a
  supersedes_atom_ids = [5792..., 69b81031...]
  applicable_condition = AND(has_scaffold=TRUE, scaffold_height_m >= 2)
"""
from __future__ import annotations

import pytest

from services.work_source.projector import project_work_rows
from services.canonical.saas_leg_source_adapter import build_saas_leg_step1


def _scaffold_row(height_m=None, active=True, **kwargs):
    row = {
        "work_type": "SCAFFOLD",
        "work_subtype": None,
        "attributes": {},
        "active": active,
    }
    if height_m is not None:
        row["attributes"] = {"height_m": height_m}
    row.update(kwargs)
    return row


def _other_row(work_type="FORKLIFT"):
    return {"work_type": work_type, "work_subtype": None, "attributes": {}, "active": True}


# ── P01-T1: 1 active SCAFFOLD, height_m=3 ─────────────────────────────────
def test_P01_T1_single_row_valid_height_projected():
    out = project_work_rows([_scaffold_row(height_m=3)])
    assert out.get("has_scaffold") is True
    assert out.get("scaffold_height_m") == 3


# ── P01-T2: 1 active SCAFFOLD, height_m=0 (valid distinct value) ───────────
def test_P01_T2_single_row_zero_height_preserved():
    out = project_work_rows([_scaffold_row(height_m=0)])
    assert out.get("has_scaffold") is True
    assert out.get("scaffold_height_m") == 0
    assert "scaffold_height_m" in out


# ── P01-T3: 1 active SCAFFOLD, height_m missing ────────────────────────────
def test_P01_T3_single_row_missing_height_absent():
    out = project_work_rows([_scaffold_row()])
    assert out.get("has_scaffold") is True
    assert "scaffold_height_m" not in out


# ── P01-T4: 1 active SCAFFOLD, invalid height_m ────────────────────────────
def test_P01_T4a_bool_height_absent():
    out = project_work_rows([_scaffold_row(height_m=True)])
    assert out.get("has_scaffold") is True
    assert "scaffold_height_m" not in out


def test_P01_T4b_negative_height_absent():
    out = project_work_rows([_scaffold_row(height_m=-1)])
    assert out.get("has_scaffold") is True
    assert "scaffold_height_m" not in out


def test_P01_T4c_string_height_absent():
    out = project_work_rows([_scaffold_row(height_m="3")])
    assert out.get("has_scaffold") is True
    assert "scaffold_height_m" not in out


# ── P01-T5: 2 active SCAFFOLD rows, different heights ──────────────────────
def test_P01_T5_two_rows_different_heights_no_aggregation():
    rows = [_scaffold_row(height_m=2), _scaffold_row(height_m=5)]
    out = project_work_rows(rows)
    assert out.get("has_scaffold") is True
    assert "scaffold_height_m" not in out


# ── P01-T6: 2 active SCAFFOLD rows, same height ────────────────────────────
def test_P01_T6_two_rows_same_height_still_absent():
    rows = [_scaffold_row(height_m=3), _scaffold_row(height_m=3)]
    out = project_work_rows(rows)
    assert out.get("has_scaffold") is True
    assert "scaffold_height_m" not in out


# ── P01-T7: inactive SCAFFOLD only ─────────────────────────────────────────
def test_P01_T7_inactive_scaffold_emits_nothing():
    out = project_work_rows([_scaffold_row(height_m=5, active=False)])
    assert "has_scaffold" not in out
    assert "scaffold_height_m" not in out


# ── P01-T8: 1 active SCAFFOLD + unrelated rows ─────────────────────────────
def test_P01_T8_unrelated_rows_do_not_affect_scaffold_height():
    rows = [
        _scaffold_row(height_m=7),
        _other_row("FORKLIFT"),
        _other_row("ELECTRICAL"),
    ]
    out = project_work_rows(rows)
    assert out.get("has_scaffold") is True
    assert out.get("scaffold_height_m") == 7
    assert out.get("uses_forklift") is True


# ── P01-T9: end-to-end adapter — single active SCAFFOLD row ────────────────
def test_P01_T9_adapter_single_row_height_in_leg_input():
    work_rows = [_scaffold_row(height_m=4.5)]
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts={},
        work_rows=work_rows,
    )
    leg_input = step1.input
    assert leg_input.get("has_scaffold") is True
    assert leg_input.get("scaffold_height_m") == 4.5


# ── P01-T10: end-to-end adapter — multi-row, scaffold_height_m absent ───────
def test_P01_T10_adapter_multi_row_height_absent():
    work_rows = [_scaffold_row(height_m=2), _scaffold_row(height_m=8)]
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts={},
        work_rows=work_rows,
    )
    leg_input = step1.input
    assert leg_input.get("has_scaffold") is True
    assert "scaffold_height_m" not in leg_input
