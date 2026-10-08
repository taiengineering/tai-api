"""WO-LFR-OBJ-P02-C2-PROJECTION-IMPLEMENT-021 — grinding_wheel_diameter_cm C2 projection tests.

P02-T1 through P02-T10: single-row valid, zero, missing, invalid, multi-row, inactive,
unrelated rows, end-to-end adapter (T9/T10).

Source atoms:
  f1b39cc7-e4de-5abf-846e-cbec5caa93cb
  c342a5be-31dc-5efd-889f-ff2a4eb5bc44
Current runtime condition: AND(has_grinding=TRUE, grinding_wheel_diameter_cm >= 5)
"""
from __future__ import annotations

import pytest

from services.work_source.projector import project_work_rows
from services.canonical.saas_leg_source_adapter import build_saas_leg_step1


def _grinding_row(wheel_diameter_cm=None, active=True, **kwargs):
    row = {
        "work_type": "GRINDING",
        "work_subtype": None,
        "attributes": {},
        "active": active,
    }
    if wheel_diameter_cm is not None:
        row["attributes"] = {"wheel_diameter_cm": wheel_diameter_cm}
    row.update(kwargs)
    return row


def _other_row(work_type="FORKLIFT"):
    return {"work_type": work_type, "work_subtype": None, "attributes": {}, "active": True}


# ── P02-T1: 1 active GRINDING, wheel_diameter_cm=10 ──────────────────────────
def test_P02_T1_single_row_valid_diameter_projected():
    out = project_work_rows([_grinding_row(wheel_diameter_cm=10)])
    assert out.get("has_grinding") is True
    assert out.get("grinding_wheel_diameter_cm") == 10


# ── P02-T2: 1 active GRINDING, wheel_diameter_cm=0 (valid distinct value) ────
def test_P02_T2_single_row_zero_diameter_preserved():
    out = project_work_rows([_grinding_row(wheel_diameter_cm=0)])
    assert out.get("has_grinding") is True
    assert out.get("grinding_wheel_diameter_cm") == 0
    assert "grinding_wheel_diameter_cm" in out


# ── P02-T3: 1 active GRINDING, wheel_diameter_cm missing ─────────────────────
def test_P02_T3_single_row_missing_diameter_absent():
    out = project_work_rows([_grinding_row()])
    assert out.get("has_grinding") is True
    assert "grinding_wheel_diameter_cm" not in out


# ── P02-T4: 1 active GRINDING, invalid wheel_diameter_cm ─────────────────────
def test_P02_T4a_bool_diameter_absent():
    out = project_work_rows([_grinding_row(wheel_diameter_cm=True)])
    assert out.get("has_grinding") is True
    assert "grinding_wheel_diameter_cm" not in out


def test_P02_T4b_negative_diameter_absent():
    out = project_work_rows([_grinding_row(wheel_diameter_cm=-1)])
    assert out.get("has_grinding") is True
    assert "grinding_wheel_diameter_cm" not in out


def test_P02_T4c_string_diameter_absent():
    out = project_work_rows([_grinding_row(wheel_diameter_cm="10")])
    assert out.get("has_grinding") is True
    assert "grinding_wheel_diameter_cm" not in out


# ── P02-T5: 2 rows, different diameters — no aggregation ─────────────────────
def test_P02_T5_two_rows_different_diameters_no_aggregation():
    rows = [_grinding_row(wheel_diameter_cm=4), _grinding_row(wheel_diameter_cm=10)]
    out = project_work_rows(rows)
    assert out.get("has_grinding") is True
    assert "grinding_wheel_diameter_cm" not in out


# ── P02-T6: 2 rows, same diameter — still absent ─────────────────────────────
def test_P02_T6_two_rows_same_diameter_still_absent():
    rows = [_grinding_row(wheel_diameter_cm=10), _grinding_row(wheel_diameter_cm=10)]
    out = project_work_rows(rows)
    assert out.get("has_grinding") is True
    assert "grinding_wheel_diameter_cm" not in out


# ── P02-T7: inactive GRINDING only ───────────────────────────────────────────
def test_P02_T7_inactive_grinding_emits_nothing():
    out = project_work_rows([_grinding_row(wheel_diameter_cm=20, active=False)])
    assert "has_grinding" not in out
    assert "grinding_wheel_diameter_cm" not in out


# ── P02-T8: 1 active GRINDING + unrelated rows ───────────────────────────────
def test_P02_T8_unrelated_rows_do_not_affect_grinding_diameter():
    rows = [
        _grinding_row(wheel_diameter_cm=15),
        _other_row("FORKLIFT"),
        _other_row("ELECTRICAL"),
    ]
    out = project_work_rows(rows)
    assert out.get("has_grinding") is True
    assert out.get("grinding_wheel_diameter_cm") == 15
    assert out.get("uses_forklift") is True


# ── P02-T9: end-to-end adapter — single active GRINDING row ──────────────────
def test_P02_T9_adapter_single_row_diameter_in_leg_input():
    work_rows = [_grinding_row(wheel_diameter_cm=7.5)]
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts={},
        work_rows=work_rows,
    )
    leg_input = step1.input
    assert leg_input.get("has_grinding") is True
    assert leg_input.get("grinding_wheel_diameter_cm") == 7.5


# ── P02-T10: end-to-end adapter — multi-row, diameter absent ─────────────────
def test_P02_T10_adapter_multi_row_diameter_absent():
    work_rows = [_grinding_row(wheel_diameter_cm=4), _grinding_row(wheel_diameter_cm=10)]
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts={},
        work_rows=work_rows,
    )
    leg_input = step1.input
    assert leg_input.get("has_grinding") is True
    assert "grinding_wheel_diameter_cm" not in leg_input
