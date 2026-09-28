"""WO-SHARED-INPUT-WAVE-A2-EQUIPMENT-SOURCE-BACKEND-IMPLEMENT-001

Covers:
  REGISTRY   — existing 5 codes registered; has_construction_machine/has_high_speed_rotor BLOCKED
  PROJECTOR  — has_emergency_gen/has_boiler/has_press/has_conveyor/has_pressure_vessel
  UNKNOWN    — unknown/absent code emits nothing (missing != false)
  IS_OPERATING — False row skipped; absent treated as operating
  SAME_ENTITY  — attributes from one row never combined with code from another
  NUMERIC_HOLD — weight_ton captured in row; no canonical numeric projection
  PARITY     — persistent/transient same projector, same output
  EXISTING_5_REGRESSION — exact parity with previous _EQ_FACT mapping
"""
import pytest

from services.equipment_source.registry import EQUIPMENT_CODE_MAP, KNOWN_CODES
from services.equipment_source.projector import project_equipment_row, project_equipment_rows


# ── helpers ──────────────────────────────────────────────────────────────────

def eq_row(code, *, is_operating=True, attrs=None):
    r = {"equipment_type_code": code, "is_operating": is_operating}
    if attrs:
        r["attributes"] = attrs
    return r


# ── REGISTRY ─────────────────────────────────────────────────────────────────

def test_registry_existing_5_codes_registered():
    for code in ("010", "014", "023", "024", "038"):
        assert code in EQUIPMENT_CODE_MAP, f"{code} missing from registry"


def test_registry_010_maps_to_has_emergency_gen():
    assert "has_emergency_gen" in EQUIPMENT_CODE_MAP["010"]["boolean_facts"]


def test_registry_014_maps_to_has_boiler():
    assert "has_boiler" in EQUIPMENT_CODE_MAP["014"]["boolean_facts"]


def test_registry_023_maps_to_has_press():
    assert "has_press" in EQUIPMENT_CODE_MAP["023"]["boolean_facts"]


def test_registry_024_maps_to_has_conveyor():
    assert "has_conveyor" in EQUIPMENT_CODE_MAP["024"]["boolean_facts"]


def test_registry_038_maps_to_has_pressure_vessel():
    assert "has_pressure_vessel" in EQUIPMENT_CODE_MAP["038"]["boolean_facts"]


def test_registry_construction_machine_code_absent():
    for code, spec in EQUIPMENT_CODE_MAP.items():
        assert "has_construction_machine" not in spec.get("boolean_facts", []), \
            f"has_construction_machine found on code {code!r} — AUTHORITY_BLOCKED"


def test_registry_high_speed_rotor_code_absent():
    for code, spec in EQUIPMENT_CODE_MAP.items():
        assert "has_high_speed_rotor" not in spec.get("boolean_facts", []), \
            f"has_high_speed_rotor found on code {code!r} — AUTHORITY_BLOCKED"


# ── PROJECTOR — existing 5 regression ────────────────────────────────────────

def test_projector_010_emits_has_emergency_gen():
    assert project_equipment_row(eq_row("010")) == {"has_emergency_gen": True}


def test_projector_014_emits_has_boiler():
    assert project_equipment_row(eq_row("014")) == {"has_boiler": True}


def test_projector_023_emits_has_press():
    assert project_equipment_row(eq_row("023")) == {"has_press": True}


def test_projector_024_emits_has_conveyor():
    assert project_equipment_row(eq_row("024")) == {"has_conveyor": True}


def test_projector_038_emits_has_pressure_vessel():
    assert project_equipment_row(eq_row("038")) == {"has_pressure_vessel": True}


def test_projector_all_5_union():
    rows = [eq_row(c) for c in ("010", "014", "023", "024", "038")]
    out = project_equipment_rows(rows)
    assert out == {
        "has_emergency_gen": True,
        "has_boiler": True,
        "has_press": True,
        "has_conveyor": True,
        "has_pressure_vessel": True,
    }


# ── PROJECTOR — unknown / absent code ────────────────────────────────────────

def test_projector_unknown_code_emits_nothing():
    assert project_equipment_row(eq_row("999")) == {}


def test_projector_absent_code_emits_nothing():
    row = {"is_operating": True}
    assert project_equipment_row(row) == {}


def test_projector_none_code_emits_nothing():
    row = {"equipment_type_code": None, "is_operating": True}
    assert project_equipment_row(row) == {}


def test_projector_empty_string_code_emits_nothing():
    row = {"equipment_type_code": "", "is_operating": True}
    assert project_equipment_row(row) == {}


def test_projector_unknown_code_does_not_emit_false():
    out = project_equipment_row({"equipment_type_code": "999", "is_operating": True})
    assert "has_construction_machine" not in out
    assert "has_high_speed_rotor" not in out
    assert out == {}


# ── PROJECTOR — is_operating semantics ───────────────────────────────────────

def test_projector_is_operating_false_emits_nothing():
    assert project_equipment_row(eq_row("014", is_operating=False)) == {}


def test_projector_is_operating_true_emits_fact():
    assert project_equipment_row(eq_row("014", is_operating=True)) == {"has_boiler": True}


def test_projector_is_operating_absent_emits_fact():
    row = {"equipment_type_code": "014"}
    assert project_equipment_row(row) == {"has_boiler": True}


def test_projector_is_operating_none_emits_fact():
    row = {"equipment_type_code": "014", "is_operating": None}
    assert project_equipment_row(row) == {"has_boiler": True}


# ── SAME ENTITY — attributes from another row never combined ─────────────────

def test_same_entity_code_and_weight_on_same_row():
    row = eq_row("014", attrs={"weight_ton": 5.0})
    out = project_equipment_row(row)
    assert out == {"has_boiler": True}


def test_same_entity_code_row_and_weight_on_other_row_not_combined():
    row_with_code = eq_row("014")
    row_with_weight_only = {"is_operating": True, "attributes": {"weight_ton": 5.0}}
    out = project_equipment_rows([row_with_code, row_with_weight_only])
    assert out == {"has_boiler": True}
    assert "construction_machine_weight_ton" not in out


# ── NUMERIC HOLD ─────────────────────────────────────────────────────────────

def test_numeric_hold_weight_ton_not_projected():
    row = eq_row("038", attrs={"weight_ton": 10.0})
    out = project_equipment_row(row)
    assert out == {"has_pressure_vessel": True}
    assert "weight_ton" not in out
    assert "construction_machine_weight_ton" not in out


# ── PERSISTENT / TRANSIENT PARITY ────────────────────────────────────────────

def test_parity_persistent_and_transient_same_output():
    """equipment_assets row (is_operating=True) and equipment_list row (no is_operating)
    with same equipment_type_code produce identical canonical output."""
    persistent_row = {"equipment_type_code": "014", "is_operating": True}
    transient_row = {"equipment_type_code": "014"}
    assert project_equipment_row(persistent_row) == project_equipment_row(transient_row)


def test_parity_all_5_persistent_vs_transient():
    codes = ["010", "014", "023", "024", "038"]
    persistent = [{"equipment_type_code": c, "is_operating": True} for c in codes]
    transient = [{"equipment_type_code": c} for c in codes]
    assert project_equipment_rows(persistent) == project_equipment_rows(transient)


# ── BOOLEAN UNION ─────────────────────────────────────────────────────────────

def test_boolean_union_true_stays_true():
    rows = [eq_row("014"), eq_row("023")]
    out = project_equipment_rows(rows)
    assert out["has_boiler"] is True
    assert out["has_press"] is True


def test_boolean_union_missing_stays_absent():
    rows = [eq_row("014")]
    out = project_equipment_rows(rows)
    assert "has_press" not in out
    assert "has_conveyor" not in out


def test_project_equipment_rows_empty_list():
    assert project_equipment_rows([]) == {}


def test_project_equipment_rows_none():
    assert project_equipment_rows(None) == {}


# ── EXISTING EQUIPMENT_LIST REGRESSION ───────────────────────────────────────

def test_legacy_equipment_list_row_without_code_skipped():
    """Existing equipment_list rows that lack equipment_type_code are ignored."""
    legacy_row = {
        "equipment_type": "PRESS",
        "asset_name": "프레스",
        "quantity": 1,
        "capacity_value": 10,
        "capacity_unit": "t",
        "is_legal_target": True,
    }
    assert project_equipment_row(legacy_row) == {}


def test_legacy_equipment_list_row_with_code_projects():
    """equipment_list row with equipment_type_code added projects correctly."""
    row_with_code = {
        "equipment_type": "PRESS",
        "asset_name": "프레스",
        "quantity": 1,
        "equipment_type_code": "023",
    }
    assert project_equipment_row(row_with_code) == {"has_press": True}


def test_legacy_mixed_list_only_coded_rows_project():
    """Mixed list: legacy rows without code produce nothing; coded rows project."""
    rows = [
        {"equipment_type": "PRESS", "asset_name": "프레스"},
        {"equipment_type_code": "014", "asset_name": "보일러"},
    ]
    out = project_equipment_rows(rows)
    assert out == {"has_boiler": True}
    assert "has_press" not in out
