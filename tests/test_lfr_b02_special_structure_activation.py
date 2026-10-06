"""WO-LFR-OBJ-B02-FAST-01 — B02 Art.6-3 special structure contract.

T1-T3:   building_activity_type gate transport
T4-T6:   article32_3_alternative_confirmation_subject transport
T7-T10:  numeric detail (cantilever, column_span) + zero
T11-T12: has_flat_plate_structure boolean transport
T13-T14: flat_plate_column_section_ratio numeric + zero
T15:     authority_designated_special_structure FALSE preserved
T16:     child/detail does not infer parent/gate
T17:     all-seven combined transport
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


# ── Gate parent 1: building_activity_type ────────────────────────────────────
def test_T1_building_activity_type_construction_preserved():
    inp = _step1({"building_activity_type": "건축"})
    assert inp.get("building_activity_type") == "건축"


def test_T2_building_activity_type_major_repair_preserved():
    inp = _step1({"building_activity_type": "대수선"})
    assert inp.get("building_activity_type") == "대수선"


def test_T3_building_activity_type_absent_yields_absent():
    inp = _step1({})
    assert "building_activity_type" not in inp


# ── Gate parent 2: article32_3_alternative_confirmation_subject ───────────────
def test_T4_article32_3_true_preserved():
    inp = _step1({"article32_3_alternative_confirmation_subject": True})
    assert inp.get("article32_3_alternative_confirmation_subject") is True


def test_T5_article32_3_false_preserved():
    inp = _step1({"article32_3_alternative_confirmation_subject": False})
    assert "article32_3_alternative_confirmation_subject" in inp
    assert inp["article32_3_alternative_confirmation_subject"] is False


def test_T6_article32_3_absent_yields_absent():
    inp = _step1({})
    assert "article32_3_alternative_confirmation_subject" not in inp


# ── Numeric detail: cantilever ────────────────────────────────────────────────
def test_T7_cantilever_projection_m_preserved():
    inp = _step1({"cantilever_projection_m": 2.5})
    assert inp.get("cantilever_projection_m") == 2.5


def test_T8_cantilever_projection_m_zero_preserved():
    inp = _step1({"cantilever_projection_m": 0})
    assert "cantilever_projection_m" in inp
    assert inp["cantilever_projection_m"] == 0


# ── Numeric detail: column_span ───────────────────────────────────────────────
def test_T9_column_span_m_preserved():
    inp = _step1({"column_span_m": 12})
    assert inp.get("column_span_m") == 12


def test_T10_column_span_m_zero_preserved():
    inp = _step1({"column_span_m": 0})
    assert "column_span_m" in inp
    assert inp["column_span_m"] == 0


# ── Flat plate parent ─────────────────────────────────────────────────────────
def test_T11_has_flat_plate_structure_true_preserved():
    inp = _step1({"has_flat_plate_structure": True})
    assert inp.get("has_flat_plate_structure") is True


def test_T12_has_flat_plate_structure_false_preserved():
    inp = _step1({"has_flat_plate_structure": False})
    assert "has_flat_plate_structure" in inp
    assert inp["has_flat_plate_structure"] is False


# ── Flat plate child ──────────────────────────────────────────────────────────
def test_T13_flat_plate_ratio_preserved():
    inp = _step1({"flat_plate_column_section_ratio": 0.35})
    assert inp.get("flat_plate_column_section_ratio") == 0.35


def test_T14_flat_plate_ratio_zero_preserved():
    inp = _step1({"flat_plate_column_section_ratio": 0})
    assert "flat_plate_column_section_ratio" in inp
    assert inp["flat_plate_column_section_ratio"] == 0


# ── Other detail ──────────────────────────────────────────────────────────────
def test_T15_authority_designated_false_preserved():
    inp = _step1({"authority_designated_special_structure": False})
    assert "authority_designated_special_structure" in inp
    assert inp["authority_designated_special_structure"] is False


# ── No inference ──────────────────────────────────────────────────────────────
def test_T16_child_detail_does_not_infer_parents():
    inp = _step1({"flat_plate_column_section_ratio": 0.4})
    assert inp.get("flat_plate_column_section_ratio") == 0.4
    assert "has_flat_plate_structure" not in inp
    assert "building_activity_type" not in inp
    assert "article32_3_alternative_confirmation_subject" not in inp


# ── Combined: all seven preserved ────────────────────────────────────────────
def test_T17_all_seven_preserved():
    inp = _step1({
        "building_activity_type": "건축",
        "article32_3_alternative_confirmation_subject": False,
        "cantilever_projection_m": 0,
        "column_span_m": 0,
        "has_flat_plate_structure": True,
        "flat_plate_column_section_ratio": 0,
        "authority_designated_special_structure": False,
    })
    assert inp.get("building_activity_type") == "건축"
    assert "article32_3_alternative_confirmation_subject" in inp
    assert inp["article32_3_alternative_confirmation_subject"] is False
    assert "cantilever_projection_m" in inp and inp["cantilever_projection_m"] == 0
    assert "column_span_m" in inp and inp["column_span_m"] == 0
    assert inp.get("has_flat_plate_structure") is True
    assert "flat_plate_column_section_ratio" in inp and inp["flat_plate_column_section_ratio"] == 0
    assert "authority_designated_special_structure" in inp
    assert inp["authority_designated_special_structure"] is False
