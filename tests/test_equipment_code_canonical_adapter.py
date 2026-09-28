"""WO-EQUIPMENT-CODE-CANONICAL-ADAPTER-PATCH-001

Covers:
  A. NORMALIZER           — identity + alias + whitespace contracts
  B. ALIAS_PROJECTOR      — PRESS/CONVEYOR/PRESSURE_VESSEL emit canonical facts via alias
  C. CRANE_FIREWALL       — CRANE normalizes to 021; 021 absent from A2 map → {} (no has_crane)
  D. LOWERCASE_FIREWALL   — lowercase free-text not normalized; validator rejects them
  E. NUMERIC_PARITY       — existing 5 numeric codes unchanged after adapter insertion
  F. ROUTER_CREATE        — PRESS stored as "023" at write time
  G. ROUTER_COMPAT        — absent / None code still accepted (backward compat)
  H. ROUTER_INVALID       — lowercase / unknown / out-of-range → 422
"""
import pytest

from services.equipment_source.canonicalizer import normalize_equipment_type_code
from services.equipment_source.store import (
    EQUIPMENT_AUTHORITY_CODES,
    EquipmentSourceValidationError,
    validate_equipment_source_row,
)
from services.equipment_source.projector import project_equipment_row, project_equipment_rows
from routers.equipment_assets import EquipmentAssetCreate, EquipmentAssetUpdate


# ── A. NORMALIZER ─────────────────────────────────────────────────────────────

def test_normalizer_none_returns_none():
    assert normalize_equipment_type_code(None) is None


def test_normalizer_numeric_passthrough():
    for code in ("010", "014", "023", "024", "038"):
        assert normalize_equipment_type_code(code) == code


def test_normalizer_numeric_whitespace_stripped():
    assert normalize_equipment_type_code(" 023 ") == "023"


def test_normalizer_press_to_023():
    assert normalize_equipment_type_code("PRESS") == "023"


def test_normalizer_conveyor_to_024():
    assert normalize_equipment_type_code("CONVEYOR") == "024"


def test_normalizer_pressure_vessel_to_038():
    assert normalize_equipment_type_code("PRESSURE_VESSEL") == "038"


def test_normalizer_crane_to_021():
    assert normalize_equipment_type_code("CRANE") == "021"


def test_normalizer_lowercase_not_inferred():
    for lc in ("press", "crane", "boiler", "forklift", "compressor"):
        result = normalize_equipment_type_code(lc)
        assert result == lc, f"expected pass-through for {lc!r}, got {result!r}"


def test_normalizer_unknown_string_passthrough():
    assert normalize_equipment_type_code("UNKNOWN") == "UNKNOWN"


def test_normalizer_empty_string_passthrough():
    assert normalize_equipment_type_code("") == ""


def test_normalizer_whitespace_only_becomes_empty():
    assert normalize_equipment_type_code("   ") == ""


# ── B. ALIAS PROJECTOR ────────────────────────────────────────────────────────

def test_alias_press_projects_has_press():
    row = {"equipment_type_code": "PRESS", "is_operating": True}
    assert project_equipment_row(row) == {"has_press": True}


def test_alias_conveyor_projects_has_conveyor():
    row = {"equipment_type_code": "CONVEYOR", "is_operating": True}
    assert project_equipment_row(row) == {"has_conveyor": True}


def test_alias_pressure_vessel_projects_has_pressure_vessel():
    row = {"equipment_type_code": "PRESSURE_VESSEL", "is_operating": True}
    assert project_equipment_row(row) == {"has_pressure_vessel": True}


def test_alias_projector_union():
    rows = [
        {"equipment_type_code": "PRESS"},
        {"equipment_type_code": "CONVEYOR"},
        {"equipment_type_code": "PRESSURE_VESSEL"},
    ]
    out = project_equipment_rows(rows)
    assert out == {"has_press": True, "has_conveyor": True, "has_pressure_vessel": True}


# ── C. CRANE SEMANTIC FIREWALL ────────────────────────────────────────────────

def test_crane_normalizes_to_021():
    assert normalize_equipment_type_code("CRANE") == "021"


def test_crane_row_projects_empty():
    row = {"equipment_type_code": "CRANE", "is_operating": True}
    assert project_equipment_row(row) == {}


def test_crane_has_crane_not_emitted():
    row = {"equipment_type_code": "CRANE", "is_operating": True}
    out = project_equipment_row(row)
    assert "has_crane" not in out


def test_021_numeric_also_projects_empty():
    row = {"equipment_type_code": "021", "is_operating": True}
    assert project_equipment_row(row) == {}
    assert "has_crane" not in project_equipment_row(row)


# ── D. LOWERCASE FIREWALL ─────────────────────────────────────────────────────

def test_lowercase_press_not_normalized():
    assert normalize_equipment_type_code("press") == "press"


def test_lowercase_boiler_not_normalized():
    assert normalize_equipment_type_code("boiler") == "boiler"


def test_lowercase_crane_not_normalized():
    assert normalize_equipment_type_code("crane") == "crane"


def test_lowercase_forklift_not_normalized():
    assert normalize_equipment_type_code("forklift") == "forklift"


def test_lowercase_press_invalid_via_validator():
    with pytest.raises(EquipmentSourceValidationError):
        validate_equipment_source_row({"equipment_type_code": "press"})


def test_lowercase_boiler_invalid_via_validator():
    with pytest.raises(EquipmentSourceValidationError):
        validate_equipment_source_row({"equipment_type_code": "boiler"})


def test_lowercase_crane_invalid_via_validator():
    with pytest.raises(EquipmentSourceValidationError):
        validate_equipment_source_row({"equipment_type_code": "crane"})


def test_lowercase_forklift_invalid_via_validator():
    with pytest.raises(EquipmentSourceValidationError):
        validate_equipment_source_row({"equipment_type_code": "forklift"})


# ── E. NUMERIC PARITY ─────────────────────────────────────────────────────────

def test_numeric_parity_010():
    row = validate_equipment_source_row({"equipment_type_code": "010", "is_operating": True})
    assert project_equipment_row(row) == {"has_emergency_gen": True}


def test_numeric_parity_014():
    row = validate_equipment_source_row({"equipment_type_code": "014", "is_operating": True})
    assert project_equipment_row(row) == {"has_boiler": True}


def test_numeric_parity_023():
    row = validate_equipment_source_row({"equipment_type_code": "023", "is_operating": True})
    assert project_equipment_row(row) == {"has_press": True}


def test_numeric_parity_024():
    row = validate_equipment_source_row({"equipment_type_code": "024", "is_operating": True})
    assert project_equipment_row(row) == {"has_conveyor": True}


def test_numeric_parity_038():
    row = validate_equipment_source_row({"equipment_type_code": "038", "is_operating": True})
    assert project_equipment_row(row) == {"has_pressure_vessel": True}


def test_numeric_parity_all_5_union():
    rows = [{"equipment_type_code": c, "is_operating": True} for c in ("010", "014", "023", "024", "038")]
    out = project_equipment_rows(rows)
    assert out == {
        "has_emergency_gen": True,
        "has_boiler": True,
        "has_press": True,
        "has_conveyor": True,
        "has_pressure_vessel": True,
    }


# ── F. VALIDATOR NORMALIZATION — alias → numeric (validator layer only) ───────
# These tests verify that validate_equipment_source_row() returns the normalized
# numeric code in the payload. This is the mechanism the router relies on, but
# these tests do NOT call create_asset() or update_asset() — see
# test_equipment_router_contract.py for actual route-level DB payload assertions.

def test_validator_press_normalizes_to_023():
    validated = validate_equipment_source_row({"equipment_type_code": "PRESS"})
    assert validated["equipment_type_code"] == "023"


def test_validator_conveyor_normalizes_to_024():
    validated = validate_equipment_source_row({"equipment_type_code": "CONVEYOR"})
    assert validated["equipment_type_code"] == "024"


def test_validator_crane_normalizes_to_021():
    validated = validate_equipment_source_row({"equipment_type_code": "CRANE"})
    assert validated["equipment_type_code"] == "021"


def test_validator_pressure_vessel_normalizes_to_038():
    validated = validate_equipment_source_row({"equipment_type_code": "PRESSURE_VESSEL"})
    assert validated["equipment_type_code"] == "038"


def test_validator_numeric_code_passthrough():
    validated = validate_equipment_source_row({"equipment_type_code": "023"})
    assert validated["equipment_type_code"] == "023"


# ── G. ROUTER COMPAT — absent / None code accepted ────────────────────────────

def test_router_create_no_code_accepted():
    body = EquipmentAssetCreate(factory_id="f1", asset_name="설비")
    assert body.equipment_type_code is None


def test_router_create_none_code_accepted():
    body = EquipmentAssetCreate(factory_id="f1", asset_name="설비", equipment_type_code=None)
    assert body.equipment_type_code is None


def test_router_update_no_code_accepted():
    body = EquipmentAssetUpdate(asset_name="수정설비")
    assert body.equipment_type_code is None


# ── H. ROUTER INVALID — unknown / lowercase / out-of-range → 422 ──────────────

def test_router_invalid_lowercase_press():
    with pytest.raises(EquipmentSourceValidationError):
        validate_equipment_source_row({"equipment_type_code": "press"})


def test_router_invalid_unknown_string():
    with pytest.raises(EquipmentSourceValidationError):
        validate_equipment_source_row({"equipment_type_code": "UNKNOWN"})


def test_router_invalid_out_of_range():
    with pytest.raises(EquipmentSourceValidationError):
        validate_equipment_source_row({"equipment_type_code": "999"})


def test_router_invalid_forklift():
    with pytest.raises(EquipmentSourceValidationError):
        validate_equipment_source_row({"equipment_type_code": "forklift"})
