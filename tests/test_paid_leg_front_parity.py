"""WO-PAID-LEG-FRONT-PARITY-IMPLEMENT-001

Paid diagnosis canonical transport parity tests.

Test registry:
  A1  BUILDING form_data vocab → canonical_applicability passes boolean facts
  A2  INDUSTRIAL form_data vocab → canonical_applicability passes boolean facts
  A3  CONSTRUCTION existing 20 vocab passes through canonical_applicability
  A4  CONSTRUCTION new 13 SEM-003+HPCC vocab in _LEG_INPUT_FIELDS
  A5  false preserved through canonical_applicability
  A6  numeric 0 preserved through canonical_applicability
  A7  missing key omitted (not defaulted to false/0)
  A8  RAW body.input does NOT auto-promote to canonical
  A9  process_list/equipment_list/ksic_list RAW containers do NOT auto-promote
  A10 BUILDING has_chemical_substance exact bridge → step1_body.input key present
  A11 BUILDING has_chemical does NOT imply has_chemical_substance in bridge
  A12 has_gas does NOT imply has_high_pressure_gas (no alias)
  A13 has_hazmat_storage does NOT imply has_hazardous_material (no alias)
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from clients.leg_runtime_client import _LEG_INPUT_FIELDS, build_facility
from schemas.diagnosis_integrated import DiagnosisRunBody
from schemas.legal_engine import DiagnoseStep1Body
from services.canonical.leg_input_contract import build_unified_leg_input
from services.canonical.materialization import canonical_applicability
from services.diagnosis_integrated_svc import _build_unified_step1_body


# ── Helpers ──────────────────────────────────────────────────────────────────

def _available_from_form_data(body: DiagnosisRunBody) -> dict:
    """Simulate run_diagnosis: _available = model_fields + form_data."""
    _available = {f: getattr(body, f, None) for f in type(body).model_fields}
    _available.update(getattr(body, "form_data", None) or {})
    return _available


def _canonical_from_form_data(body: DiagnosisRunBody) -> dict:
    return canonical_applicability(_available_from_form_data(body))


def _mk_body(**kwargs) -> DiagnosisRunBody:
    return DiagnosisRunBody(**{"sector": "BUILDING", "tier": "PAID", **kwargs})


def _mk_step1_body(engine_sector: str, source_facts: dict) -> DiagnoseStep1Body:
    return build_unified_leg_input(sector=engine_sector, source_facts=source_facts)


# ── A1: BUILDING form_data boolean facts reach canonical ─────────────────────

def test_a1_building_form_data_boolean_to_canonical():
    """A1: BUILDING form_data booleans pass through canonical_applicability."""
    body = _mk_body(
        sector="BUILDING",
        form_data={
            "has_gas": True,
            "has_high_pressure_gas": True,
            "has_hazardous_material": False,
            "total_floor_area": 5000.0,
        },
    )
    canon = _canonical_from_form_data(body)
    assert canon.get("has_gas") is True
    assert canon.get("has_high_pressure_gas") is True
    assert canon.get("has_hazardous_material") is False
    assert canon.get("total_floor_area") == 5000.0


# ── A2: INDUSTRIAL form_data boolean facts reach canonical ───────────────────

def test_a2_industrial_form_data_boolean_to_canonical():
    """A2: INDUSTRIAL form_data booleans pass through canonical_applicability."""
    body = _mk_body(
        sector="INDUSTRIAL",
        form_data={
            "has_boiler": True,
            "has_high_pressure_gas": False,
            "worker_count": 30,
        },
    )
    canon = _canonical_from_form_data(body)
    assert canon.get("has_boiler") is True
    assert canon.get("has_high_pressure_gas") is False
    assert canon.get("worker_count") == 30


# ── A3: CONSTRUCTION existing 20 vocab passes canonical ──────────────────────

_CONSTRUCTION_ORIGINAL_20 = [
    "has_excavation", "has_demolition", "has_tower_crane", "has_confined_space",
    "has_asbestos_demo", "has_blasting", "has_diving", "work_height_m",
    "has_truck_loading_unloading", "truck_loading_height_m",
    "has_manual_heavy_handling", "manual_handling_weight_kg",
    "has_chemical_substance", "has_subcontractor", "has_asbestos",
    "has_gas", "has_high_pressure_gas", "has_water_tank",
    "is_energy_intensive", "is_multi_use",
]

def test_a3_construction_original_20_in_leg_fields():
    """A3: All original 20 CONSTRUCTION consumer vocab fields are in _LEG_INPUT_FIELDS."""
    leg_set = set(_LEG_INPUT_FIELDS)
    missing = [f for f in _CONSTRUCTION_ORIGINAL_20 if f not in leg_set]
    # has_chemical_substance is NOT in _LEG_INPUT_FIELDS (handled by build_facility PATCH-A)
    # — exclude it from this check
    missing_except_hcs = [f for f in missing if f != "has_chemical_substance"]
    assert missing_except_hcs == [], f"CONSTRUCTION vocab missing from _LEG_INPUT_FIELDS: {missing_except_hcs}"


# ── A4: CONSTRUCTION new 13 SEM-003 + HPCC vocab in _LEG_INPUT_FIELDS ───────

_CONSTRUCTION_NEW_13 = [
    "has_scuba_diving",
    "has_surface_supplied_diving",
    "has_pressure_adjustment_chamber",
    "supplies_air_to_diver_from_air_compressor",
    "supplies_breathing_gas_to_diver_from_cylinder",
    "breathing_gas_cylinder_pressure_kgf_cm2",
    "diving_depth_m",
    "diving_surface_ascent_restricted",
    "diving_decompression_stop_required",
    "has_high_pressure_work",
    "has_air_compressor",
    "supplies_air_to_high_pressure_workroom_or_airlock",
    "has_caisson_work",
]

def test_a4_construction_new_13_in_leg_fields():
    """A4: All 13 new CONSTRUCTION SEM-003+HPCC vocab fields are in _LEG_INPUT_FIELDS."""
    leg_set = set(_LEG_INPUT_FIELDS)
    missing = [f for f in _CONSTRUCTION_NEW_13 if f not in leg_set]
    assert missing == [], f"New CONSTRUCTION vocab missing from _LEG_INPUT_FIELDS: {missing}"


# ── A5: false preserved through canonical ────────────────────────────────────

def test_a5_false_preserved_canonical():
    """A5: false values preserved (not dropped) by canonical_applicability."""
    body = _mk_body(
        form_data={"has_gas": False, "has_high_pressure_gas": False, "has_scaffold": False},
    )
    canon = _canonical_from_form_data(body)
    assert canon.get("has_gas") is False, "has_gas=False must be preserved"
    assert canon.get("has_high_pressure_gas") is False
    assert canon.get("has_scaffold") is False


# ── A6: numeric 0 preserved through canonical ────────────────────────────────

def test_a6_zero_preserved_canonical():
    """A6: numeric 0 preserved (not dropped) by canonical_applicability."""
    body = _mk_body(
        form_data={"total_floor_area": 0.0, "worker_count": 0, "work_height_m": 0.0},
    )
    canon = _canonical_from_form_data(body)
    assert canon.get("total_floor_area") == 0.0
    assert canon.get("worker_count") == 0
    assert canon.get("work_height_m") == 0.0


# ── A7: missing key omitted (no synthetic false/0) ───────────────────────────

def test_a7_missing_omitted_not_defaulted():
    """A7: Keys absent from form_data are omitted in canonical (not set to false/0/None)."""
    body = _mk_body(form_data={"has_gas": True})
    canon = _canonical_from_form_data(body)
    assert "has_high_pressure_gas" not in canon
    assert "has_diving" not in canon
    assert "worker_count" not in canon


# ── A8: RAW body.input does NOT auto-promote to canonical ────────────────────

def test_a8_raw_input_no_autopromote():
    """A8: body.input (RAW) is NOT unpacked into canonical applicability.
    Backend RAW→CANONICAL FIREWALL: only form_data reaches canonical_applicability."""
    body = _mk_body(
        input={"has_diving": True, "total_floor_area": 9999},
        form_data={},  # empty form_data
    )
    canon = _canonical_from_form_data(body)
    # input dict is model_field → _available["input"] = nested dict, not expanded
    # canonical_applicability only checks top-level keys matching _LEG_INPUT_FIELDS
    assert "has_diving" not in canon, "body.input contents must not reach canonical"
    # Note: total_floor_area from body.total_floor_area (model field) might be None,
    # but from body.input it should not surface
    assert canon.get("total_floor_area") is None or "total_floor_area" not in canon or \
           canon.get("total_floor_area") != 9999, \
        "body.input total_floor_area=9999 must not reach canonical"


# ── A9: RAW container fields (process_list etc.) do NOT auto-promote ─────────

def test_a9_raw_containers_no_autopromote():
    """A9: process_list/equipment_list/ksic_list do not reach _LEG_INPUT_FIELDS."""
    leg_set = set(_LEG_INPUT_FIELDS)
    assert "process_list" not in leg_set
    assert "equipment_list" not in leg_set
    assert "ksic_list" not in leg_set


# ── A10: BUILDING has_chemical_substance exact bridge ────────────────────────

def _build_step1(engine_sector: str, inp: dict, body) -> DiagnoseStep1Body:
    """Wrapper for _build_unified_step1_body with standard dummy args."""
    return _build_unified_step1_body(
        engine_sector=engine_sector,
        inp=inp,
        workers=0,
        body=body,
        factory_id=None,
        construction_type_fallback=None,
        unified_factory=build_unified_leg_input,
        contract_amount_eok=None,
    )


def test_a10_building_hcs_exact_bridge():
    """A10: BUILDING explicit has_chemical_substance=True → step1_body.input key present."""
    body = _mk_body(
        sector="BUILDING",
        form_data={"has_gas": True, "has_chemical_substance": True},
    )
    inp = canonical_applicability(_available_from_form_data(body))
    # has_chemical_substance NOT in _LEG_INPUT_FIELDS → not in inp
    assert "has_chemical_substance" not in inp
    step1_body = _build_step1("BUILDING", inp, body)
    # bridge injects it into step1_body.input
    assert step1_body.input.get("has_chemical_substance") is True, \
        "PATCH-B bridge must inject has_chemical_substance into step1_body.input"


def test_a10b_building_hcs_false_preserved():
    """A10b: BUILDING has_chemical_substance=False → step1_body.input preserves false."""
    body = _mk_body(
        sector="BUILDING",
        form_data={"has_chemical_substance": False},
    )
    inp = canonical_applicability(_available_from_form_data(body))
    step1_body = _build_step1("BUILDING", inp, body)
    assert step1_body.input.get("has_chemical_substance") is False, \
        "false must be preserved in BUILDING HCS bridge"


def test_a10c_building_hcs_missing_not_injected():
    """A10c: BUILDING has_chemical_substance absent → not injected (missing != false)."""
    body = _mk_body(
        sector="BUILDING",
        form_data={"has_gas": True},  # no has_chemical_substance
    )
    inp = canonical_applicability(_available_from_form_data(body))
    step1_body = _build_step1("BUILDING", inp, body)
    assert "has_chemical_substance" not in step1_body.input, \
        "missing has_chemical_substance must not be injected as false"


def test_a10d_building_hcs_reaches_build_facility():
    """A10d: BUILDING has_chemical_substance=True → build_facility returns it."""
    body = _mk_body(
        sector="BUILDING",
        form_data={"has_chemical_substance": True},
    )
    inp = canonical_applicability(_available_from_form_data(body))
    step1_body = _build_step1("BUILDING", inp, body)
    facility = build_facility(step1_body)
    assert facility.get("has_chemical_substance") is True, \
        "build_facility must pass has_chemical_substance for BUILDING"


# ── A11: BUILDING has_chemical does NOT imply has_chemical_substance ─────────

def test_a11_building_has_chemical_no_alias():
    """A11: BUILDING has_chemical in form_data does NOT become has_chemical_substance."""
    body = _mk_body(
        sector="BUILDING",
        form_data={"has_chemical": True},
    )
    inp = canonical_applicability(_available_from_form_data(body))
    step1_body = _build_step1("BUILDING", inp, body)
    # has_chemical_substance must NOT be injected from has_chemical
    assert "has_chemical_substance" not in step1_body.input, \
        "has_chemical must not alias to has_chemical_substance for BUILDING"


# ── A12: has_gas does NOT imply has_high_pressure_gas ────────────────────────

def test_a12_has_gas_no_alias_to_high_pressure():
    """A12: has_gas=True does NOT set has_high_pressure_gas."""
    body = _mk_body(form_data={"has_gas": True})
    inp = canonical_applicability(_available_from_form_data(body))
    step1_body = _build_step1("BUILDING", inp, body)
    # has_gas IS in _LEG_INPUT_FIELDS, has_high_pressure_gas IS in _LEG_INPUT_FIELDS too
    assert step1_body.input.get("has_gas") is True
    assert "has_high_pressure_gas" not in step1_body.input, \
        "has_gas must not imply has_high_pressure_gas"


# ── A13: has_hazmat_storage does NOT imply has_hazardous_material ────────────

def test_a13_has_hazmat_storage_no_alias():
    """A13: has_hazmat_storage=True does NOT set has_hazardous_material."""
    body = _mk_body(form_data={"has_hazmat_storage": True})
    inp = canonical_applicability(_available_from_form_data(body))
    step1_body = _build_step1("BUILDING", inp, body)
    assert step1_body.input.get("has_hazmat_storage") is True
    assert "has_hazardous_material" not in step1_body.input, \
        "has_hazmat_storage must not alias to has_hazardous_material"
