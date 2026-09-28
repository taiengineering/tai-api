"""WO-SHARED-INPUT-WAVE-A2-PATCH1-SOURCE-CONTRACT-COMPLETION

Covers:
  VALID_AUTHORITY_UNMAPPED_CODE_ACCEPTED_MISSING — authority code outside MAP accepted; no fact
  INVALID_EQUIPMENT_CODE_REJECTED                — unknown code raises EquipmentSourceValidationError
  MISSING_CODE_LEGACY_ROW_ACCEPTED               — row without code passes through as-is
  UNKNOWN_CODE_NEVER_FALSE                       — unknown authority code never produces False
  IS_OPERATING_FALSE_BOOL_SKIP                   — is_operating=False (bool) valid; projector skips
  IS_OPERATING_STRING_FALSE_REJECT               — is_operating="false" (str) rejected
  IS_OPERATING_INT_ZERO_REJECT                   — is_operating=0 (int) rejected
  PERSISTENT_ATTRIBUTES_CREATE_TRANSPORT         — EquipmentAssetCreate carries attributes field
  PERSISTENT_ATTRIBUTES_UPDATE_TRANSPORT         — EquipmentAssetUpdate carries attributes field
  PERSISTENT_ATTRIBUTES_READ_TRANSPORT           — GET list SELECT includes attributes column
  EXISTING_5_RUNTIME_PARITY                      — all 5 authority codes validate + project correctly
  TRANSIENT_EXISTING_5_PARITY                    — transient rows (no is_operating) same output
  NUMERIC_ATTRIBUTES_NOT_PROJECTED               — numeric attributes dict generates no bool facts
  CAPACITY_VALUE_NOT_REPURPOSED                  — capacity_value not used as equipment source attr
"""
import inspect

import pytest

from services.equipment_source.store import (
    EQUIPMENT_AUTHORITY_CODES,
    EquipmentSourceValidationError,
    validate_equipment_source_row,
)
from services.equipment_source.projector import project_equipment_row, project_equipment_rows
from routers.equipment_assets import EquipmentAssetCreate, EquipmentAssetUpdate


# ── VALID_AUTHORITY_UNMAPPED_CODE_ACCEPTED_MISSING ──────────────────────────

def test_valid_authority_unmapped_code_accepted():
    """A code in authority (e.g. '001') but not in EQUIPMENT_CODE_MAP is valid; no fact emitted."""
    assert "001" in EQUIPMENT_AUTHORITY_CODES
    row = validate_equipment_source_row({"equipment_type_code": "001"})
    assert row["equipment_type_code"] == "001"
    assert project_equipment_row(row) == {}


def test_valid_authority_unmapped_code_missing_not_false():
    row = validate_equipment_source_row({"equipment_type_code": "002"})
    out = project_equipment_row(row)
    for fact in ("has_emergency_gen", "has_boiler", "has_press", "has_conveyor", "has_pressure_vessel"):
        assert fact not in out


# ── INVALID_EQUIPMENT_CODE_REJECTED ─────────────────────────────────────────

def test_invalid_code_rejected():
    with pytest.raises(EquipmentSourceValidationError):
        validate_equipment_source_row({"equipment_type_code": "999"})


def test_invalid_code_alpha_rejected():
    with pytest.raises(EquipmentSourceValidationError):
        validate_equipment_source_row({"equipment_type_code": "UNKNOWN"})


# ── MISSING_CODE_LEGACY_ROW_ACCEPTED ────────────────────────────────────────

def test_missing_code_legacy_row_accepted():
    """Legacy row with no equipment_type_code is returned as-is."""
    row = {"equipment_type": "PRESS", "asset_name": "프레스", "quantity": 1}
    result = validate_equipment_source_row(row)
    assert result is row


def test_missing_code_none_accepted():
    row = {"equipment_type_code": None, "is_operating": True}
    result = validate_equipment_source_row(row)
    assert result is row


# ── UNKNOWN_CODE_NEVER_FALSE ─────────────────────────────────────────────────

def test_unknown_code_never_false():
    """Authority code outside MAP never emits False for any canonical fact."""
    out = project_equipment_row({"equipment_type_code": "005"})
    assert out == {}
    for v in out.values():
        assert v is not False


# ── IS_OPERATING ─────────────────────────────────────────────────────────────

def test_is_operating_false_bool_valid():
    """is_operating=False (bool) passes validation; projector skips the row."""
    row = validate_equipment_source_row({"equipment_type_code": "014", "is_operating": False})
    assert row["is_operating"] is False
    assert project_equipment_row(row) == {}


def test_is_operating_string_false_rejected():
    with pytest.raises(EquipmentSourceValidationError):
        validate_equipment_source_row({"equipment_type_code": "014", "is_operating": "false"})


def test_is_operating_string_true_rejected():
    with pytest.raises(EquipmentSourceValidationError):
        validate_equipment_source_row({"equipment_type_code": "014", "is_operating": "true"})


def test_is_operating_int_zero_rejected():
    with pytest.raises(EquipmentSourceValidationError):
        validate_equipment_source_row({"equipment_type_code": "014", "is_operating": 0})


def test_is_operating_int_one_rejected():
    with pytest.raises(EquipmentSourceValidationError):
        validate_equipment_source_row({"equipment_type_code": "014", "is_operating": 1})


# ── PERSISTENT TRANSPORT (model-level) ───────────────────────────────────────

def test_persistent_attributes_create_transport():
    """EquipmentAssetCreate accepts attributes dict."""
    body = EquipmentAssetCreate(
        factory_id="f1",
        asset_name="보일러",
        equipment_type_code="014",
        attributes={"weight_ton": 5.0},
    )
    d = body.model_dump()
    assert d["attributes"] == {"weight_ton": 5.0}


def test_persistent_attributes_create_none_allowed():
    body = EquipmentAssetCreate(factory_id="f1", asset_name="보일러")
    assert body.attributes is None


def test_persistent_attributes_update_transport():
    """EquipmentAssetUpdate accepts attributes dict."""
    body = EquipmentAssetUpdate(attributes={"weight_ton": 10.0})
    d = body.model_dump()
    assert d["attributes"] == {"weight_ton": 10.0}


def test_persistent_attributes_read_transport():
    """GET list SELECT string includes 'attributes' column."""
    import routers.equipment_assets as _ea
    src = inspect.getsource(_ea.get_assets)
    assert "attributes" in src


# ── EXISTING 5 RUNTIME PARITY ────────────────────────────────────────────────

def test_existing_5_runtime_parity():
    """All 5 existing codes validate without error and project to the correct fact."""
    expected = {
        "010": "has_emergency_gen",
        "014": "has_boiler",
        "023": "has_press",
        "024": "has_conveyor",
        "038": "has_pressure_vessel",
    }
    for code, fact in expected.items():
        row = validate_equipment_source_row({"equipment_type_code": code, "is_operating": True})
        out = project_equipment_row(row)
        assert out == {fact: True}, f"code={code}: expected {{{fact!r}: True}}, got {out!r}"


def test_transient_existing_5_parity():
    """Transient rows (no is_operating) produce same output as persistent rows."""
    codes = ["010", "014", "023", "024", "038"]
    persistent = [{"equipment_type_code": c, "is_operating": True} for c in codes]
    transient = [{"equipment_type_code": c} for c in codes]
    p_validated = [validate_equipment_source_row(r) for r in persistent]
    t_validated = [validate_equipment_source_row(r) for r in transient]
    assert project_equipment_rows(p_validated) == project_equipment_rows(t_validated)


# ── NUMERIC_ATTRIBUTES_NOT_PROJECTED ─────────────────────────────────────────

def test_numeric_attributes_not_projected():
    """attributes dict with numeric values passes validation but generates no extra facts."""
    row = validate_equipment_source_row({
        "equipment_type_code": "014",
        "is_operating": True,
        "attributes": {"weight_ton": 5.0, "pressure_mpa": 1.2},
    })
    out = project_equipment_row(row)
    assert "weight_ton" not in out
    assert "pressure_mpa" not in out
    assert out == {"has_boiler": True}


# ── CAPACITY_VALUE_NOT_REPURPOSED ─────────────────────────────────────────────

def test_capacity_value_not_repurposed():
    """capacity_value (old schema field) is not repurposed as an equipment source attribute."""
    row = {
        "equipment_type_code": "014",
        "capacity_value": 100.0,
        "capacity_unit": "kW",
    }
    validated = validate_equipment_source_row(row)
    out = project_equipment_row(validated)
    assert "capacity_value" not in out
    assert out == {"has_boiler": True}


# ── PATCH2: EMPTY_CODE / WHITESPACE_CODE gate ────────────────────────────────

def test_empty_string_code_422():
    """equipment_type_code="" (key present, empty string) must reach validator → error."""
    with pytest.raises(EquipmentSourceValidationError):
        validate_equipment_source_row({"equipment_type_code": ""})


def test_whitespace_code_422():
    """equipment_type_code="  " (key present, whitespace) must reach validator → error."""
    with pytest.raises(EquipmentSourceValidationError):
        validate_equipment_source_row({"equipment_type_code": "   "})


def test_none_code_legacy_no_projection():
    """equipment_type_code=None (key present but None) is legacy row; passes validation, no projection."""
    row = {"equipment_type_code": None, "is_operating": True}
    result = validate_equipment_source_row(row)
    assert result is row
    assert project_equipment_row(result) == {}


def test_absent_code_legacy_no_projection():
    """Row without equipment_type_code key is legacy; passes validation, no projection."""
    row = {"equipment_type": "PRESS", "asset_name": "프레스"}
    result = validate_equipment_source_row(row)
    assert result is row
    assert project_equipment_row(result) == {}


# ── PATCH2: resolver parity (014 / 023 / 024 MATCH confirmed) ────────────────

def test_014_resolver_parity():
    """code_condition_resolver "014" → has_boiler matches A2 registry."""
    row = validate_equipment_source_row({"equipment_type_code": "014"})
    assert project_equipment_row(row) == {"has_boiler": True}


def test_023_resolver_parity():
    """code_condition_resolver "023" → has_press matches A2 registry."""
    row = validate_equipment_source_row({"equipment_type_code": "023"})
    assert project_equipment_row(row) == {"has_press": True}


def test_024_resolver_parity():
    """code_condition_resolver "024" → has_conveyor matches A2 registry."""
    row = validate_equipment_source_row({"equipment_type_code": "024"})
    assert project_equipment_row(row) == {"has_conveyor": True}
