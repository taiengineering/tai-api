"""WO-LFR-OBJ-P03-C2-PROJECTION-IMPLEMENT-029 — object_drop_height_m C2 projection tests.

P03-T1 through P03-T10: single-row valid, zero, missing, invalid (bool/negative/string/
NaN/inf), multi-row, inactive, unrelated rows, end-to-end adapter (T9/T10).

Source atoms:
  5ba52aa3-c1e2-5196-badb-2794e48f75ca
  6f04708b-b9b0-577b-8fa5-d99c8f062e2b
Current runtime condition: AND(has_object_drop=TRUE, object_drop_height_m >= 3)
Law: 산업안전보건기준에 관한 규칙 제15조
"""
from __future__ import annotations

import math

import pytest

from services.work_source.projector import project_work_rows
from services.canonical.saas_leg_source_adapter import build_saas_leg_step1


def _drop_row(height_m=None, active=True, **kwargs):
    row = {
        "work_type": "OBJECT_DROP",
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


# ── P03-T1: 1 active OBJECT_DROP, height_m=5 ─────────────────────────────────
def test_P03_T1_single_row_valid_height_projected():
    out = project_work_rows([_drop_row(height_m=5)])
    assert out.get("has_object_drop") is True
    assert out.get("object_drop_height_m") == 5


# ── P03-T2: 1 active OBJECT_DROP, height_m=0 (valid distinct value) ──────────
def test_P03_T2_single_row_zero_height_preserved():
    out = project_work_rows([_drop_row(height_m=0)])
    assert out.get("has_object_drop") is True
    assert out.get("object_drop_height_m") == 0
    assert "object_drop_height_m" in out


# ── P03-T3: 1 active OBJECT_DROP, height_m missing ───────────────────────────
def test_P03_T3_single_row_missing_height_absent():
    out = project_work_rows([_drop_row()])
    assert out.get("has_object_drop") is True
    assert "object_drop_height_m" not in out


# ── P03-T4: 1 active OBJECT_DROP, invalid height_m ───────────────────────────
def test_P03_T4a_bool_height_absent():
    out = project_work_rows([_drop_row(height_m=True)])
    assert out.get("has_object_drop") is True
    assert "object_drop_height_m" not in out


def test_P03_T4b_negative_height_absent():
    out = project_work_rows([_drop_row(height_m=-1)])
    assert out.get("has_object_drop") is True
    assert "object_drop_height_m" not in out


def test_P03_T4c_string_height_absent():
    out = project_work_rows([_drop_row(height_m="5")])
    assert out.get("has_object_drop") is True
    assert "object_drop_height_m" not in out


def test_P03_T4d_nan_height_absent():
    out = project_work_rows([_drop_row(height_m=float("nan"))])
    assert out.get("has_object_drop") is True
    assert "object_drop_height_m" not in out


def test_P03_T4e_inf_height_absent():
    out = project_work_rows([_drop_row(height_m=float("inf"))])
    assert out.get("has_object_drop") is True
    assert "object_drop_height_m" not in out

    out2 = project_work_rows([_drop_row(height_m=float("-inf"))])
    assert out2.get("has_object_drop") is True
    assert "object_drop_height_m" not in out2


# ── P03-T5: 2 rows, different heights — no aggregation ───────────────────────
def test_P03_T5_two_rows_different_heights_no_aggregation():
    rows = [_drop_row(height_m=3), _drop_row(height_m=10)]
    out = project_work_rows(rows)
    assert out.get("has_object_drop") is True
    assert "object_drop_height_m" not in out


# ── P03-T6: 2 rows, same height — still absent ───────────────────────────────
def test_P03_T6_two_rows_same_height_still_absent():
    rows = [_drop_row(height_m=5), _drop_row(height_m=5)]
    out = project_work_rows(rows)
    assert out.get("has_object_drop") is True
    assert "object_drop_height_m" not in out


# ── P03-T7: inactive OBJECT_DROP only ────────────────────────────────────────
def test_P03_T7_inactive_object_drop_emits_nothing():
    out = project_work_rows([_drop_row(height_m=10, active=False)])
    assert "has_object_drop" not in out
    assert "object_drop_height_m" not in out


# ── P03-T8: 1 active OBJECT_DROP + unrelated rows ────────────────────────────
def test_P03_T8_unrelated_rows_do_not_affect_object_drop_height():
    rows = [
        _drop_row(height_m=7),
        _other_row("FORKLIFT"),
        _other_row("ELECTRICAL"),
    ]
    out = project_work_rows(rows)
    assert out.get("has_object_drop") is True
    assert out.get("object_drop_height_m") == 7
    assert out.get("uses_forklift") is True


# ── P03-T9: end-to-end adapter — single active OBJECT_DROP row ───────────────
def test_P03_T9_adapter_single_row_height_in_leg_input():
    work_rows = [_drop_row(height_m=7.5)]
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts={},
        work_rows=work_rows,
    )
    leg_input = step1.input
    assert leg_input.get("has_object_drop") is True
    assert leg_input.get("object_drop_height_m") == 7.5


# ── P03-T10: end-to-end adapter — multi-row, height absent ───────────────────
def test_P03_T10_adapter_multi_row_height_absent():
    work_rows = [_drop_row(height_m=3), _drop_row(height_m=10)]
    step1 = build_saas_leg_step1(
        sector="INDUSTRIAL",
        source_facts={},
        work_rows=work_rows,
    )
    leg_input = step1.input
    assert leg_input.get("has_object_drop") is True
    assert "object_drop_height_m" not in leg_input
