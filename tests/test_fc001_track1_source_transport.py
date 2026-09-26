"""WO-A5-FC001-TRACK1-SOURCE-TRANSPORT-IMPLEMENT-001 — FC-001 TRACK-1 tests.

T1: closed-set validation rejects unknown handling_mode_codes
T2: closed-set validation accepts valid modes and null
T3: false-composite prevention — managed-null row + unclassified-mode row
T4: positive — managed row with MANUFACTURE_OR_USE → APPLICABLE
T5: tri-state null → UNKNOWN (omit)
T6: tri-state empty → False (explicit exclusion)
T7: multi-row — one managed+mode confirms → True
T8: STORAGE_TRANSPORT independent of MANUFACTURE_OR_USE
T9: permit + MANUFACTURE_OR_USE synthesis
T10: fc001_any_manufacture_or_use removed (CORRECTION-001) — field never produced
T11: broad hazardous material firewall — unclassified row does not yield permit fields
"""
import pytest

from services.material_source.store import (
    MaterialSourceValidationError,
    validate_factory_payload,
)
from services.material_source.canonical_adapter import project_material_fc001_facts

KEY_MANAGED = "ISHL-RULE-APP12-G1-I001"  # MANAGED_HAZARDOUS_SUBSTANCE


# ---------------------------------------------------------------------------
# T1: closed-set validation
# ---------------------------------------------------------------------------

def test_t1_invalid_mode_rejected():
    with pytest.raises(MaterialSourceValidationError, match="invalid values"):
        validate_factory_payload({"material_name": "X", "handling_mode_codes": ["INVALID"]})


def test_t1_partial_invalid_rejected():
    with pytest.raises(MaterialSourceValidationError, match="invalid values"):
        validate_factory_payload({
            "material_name": "X",
            "handling_mode_codes": ["MANUFACTURE_OR_USE", "BAD_MODE"],
        })


# ---------------------------------------------------------------------------
# T2: valid modes accepted
# ---------------------------------------------------------------------------

def test_t2_all_valid_modes_accepted():
    for mode in ["INDOOR_HANDLING", "MANUFACTURE_OR_USE", "STORAGE_TRANSPORT", "TANK_EQUIPMENT_WORK"]:
        r = validate_factory_payload({"material_name": "X", "handling_mode_codes": [mode]})
        assert r["handling_mode_codes"] == [mode]


def test_t2_null_accepted():
    r = validate_factory_payload({"material_name": "X", "handling_mode_codes": None})
    assert r["handling_mode_codes"] is None


def test_t2_empty_accepted():
    r = validate_factory_payload({"material_name": "X", "handling_mode_codes": []})
    assert r["handling_mode_codes"] == []


def test_t2_multi_valid_accepted():
    modes = ["MANUFACTURE_OR_USE", "INDOOR_HANDLING"]
    r = validate_factory_payload({"material_name": "X", "handling_mode_codes": modes})
    assert r["handling_mode_codes"] == modes


# ---------------------------------------------------------------------------
# T3: false-composite prevention
# ---------------------------------------------------------------------------

def test_t3_false_composite_guard():
    """Row A: managed substance, NULL handling_mode.
    Row B: unclassified (no key), MANUFACTURE_OR_USE.
    fc001_managed_manufacture_or_use must be OMITTED (UNKNOWN), not True.
    """
    rows = [
        {"is_active": True, "material_master_key": KEY_MANAGED, "handling_mode_codes": None},
        {"is_active": True, "material_master_key": None, "handling_mode_codes": ["MANUFACTURE_OR_USE"]},
    ]
    result = project_material_fc001_facts(rows)
    assert "fc001_managed_manufacture_or_use" not in result, (
        "False composite: managed row has NULL mode — must not confirm managed+manufacture"
    )


# ---------------------------------------------------------------------------
# T4: positive — managed + MANUFACTURE_OR_USE → APPLICABLE
# ---------------------------------------------------------------------------

def test_t4_managed_manufacture_or_use_positive():
    rows = [
        {"is_active": True, "material_master_key": KEY_MANAGED,
         "handling_mode_codes": ["MANUFACTURE_OR_USE"]},
    ]
    result = project_material_fc001_facts(rows)
    assert result["fc001_managed_manufacture_or_use"] is True
    assert result["fc001_managed_indoor_handling"] is False
    assert result["fc001_managed_storage_transport"] is False
    assert result["fc001_managed_tank_equipment_work"] is False


# ---------------------------------------------------------------------------
# T5: tri-state null → UNKNOWN (omit)
# ---------------------------------------------------------------------------

def test_t5_null_mode_is_unknown():
    rows = [
        {"is_active": True, "material_master_key": KEY_MANAGED, "handling_mode_codes": None},
    ]
    result = project_material_fc001_facts(rows)
    # Managed row with NULL → all managed fields absent (UNKNOWN)
    assert "fc001_managed_manufacture_or_use" not in result
    assert "fc001_managed_indoor_handling" not in result
    assert "fc001_managed_storage_transport" not in result
    assert "fc001_managed_tank_equipment_work" not in result


# ---------------------------------------------------------------------------
# T6: tri-state empty → False (explicit exclusion)
# ---------------------------------------------------------------------------

def test_t6_empty_mode_is_false():
    rows = [
        {"is_active": True, "material_master_key": KEY_MANAGED, "handling_mode_codes": []},
    ]
    result = project_material_fc001_facts(rows)
    assert result.get("fc001_managed_manufacture_or_use") is False
    assert result.get("fc001_managed_indoor_handling") is False


# ---------------------------------------------------------------------------
# T7: multi-row — one row confirms
# ---------------------------------------------------------------------------

def test_t7_multi_row_one_confirms():
    rows = [
        {"is_active": True, "material_master_key": KEY_MANAGED, "handling_mode_codes": ["STORAGE_TRANSPORT"]},
        {"is_active": True, "material_master_key": KEY_MANAGED, "handling_mode_codes": ["MANUFACTURE_OR_USE"]},
    ]
    result = project_material_fc001_facts(rows)
    assert result["fc001_managed_manufacture_or_use"] is True
    assert result["fc001_managed_storage_transport"] is True
    assert result.get("fc001_managed_indoor_handling") is False


# ---------------------------------------------------------------------------
# T8: STORAGE_TRANSPORT independent
# ---------------------------------------------------------------------------

def test_t8_storage_transport_independent():
    rows = [
        {"is_active": True, "material_master_key": KEY_MANAGED,
         "handling_mode_codes": ["STORAGE_TRANSPORT"]},
    ]
    result = project_material_fc001_facts(rows)
    assert result["fc001_managed_storage_transport"] is True
    assert result.get("fc001_managed_manufacture_or_use") is False


# ---------------------------------------------------------------------------
# T9: permit + MANUFACTURE_OR_USE
# ---------------------------------------------------------------------------

def test_t9_permit_manufacture_or_use():
    permit_key = None  # find a permit key
    from services.material_source.store import catalog_index
    idx = catalog_index()
    for key, cls_list in idx["classifications_by_key"].items():
        codes = [c["classification_code"] for c in cls_list]
        if "PERMIT_REQUIRED_HAZARDOUS_SUBSTANCE" in codes:
            permit_key = key
            break
    if permit_key is None:
        pytest.skip("no PERMIT_REQUIRED_HAZARDOUS_SUBSTANCE in catalog")

    rows = [
        {"is_active": True, "material_master_key": permit_key,
         "handling_mode_codes": ["MANUFACTURE_OR_USE"]},
    ]
    result = project_material_fc001_facts(rows)
    assert result["fc001_permit_manufacture_or_use"] is True
    # no managed row → UNKNOWN (absent), not False
    assert "fc001_managed_manufacture_or_use" not in result


# ---------------------------------------------------------------------------
# T10: fc001_any_manufacture_or_use removed (CORRECTION-001)
# ---------------------------------------------------------------------------

def test_t10_any_field_not_produced():
    """fc001_any_manufacture_or_use was removed — must never appear in output."""
    rows = [
        {"is_active": True, "material_master_key": None, "handling_mode_codes": ["MANUFACTURE_OR_USE"]},
    ]
    result = project_material_fc001_facts(rows)
    assert "fc001_any_manufacture_or_use" not in result
    # unclassified row produces no classification-gated fields either
    assert "fc001_managed_manufacture_or_use" not in result
    assert "fc001_permit_manufacture_or_use" not in result


# ---------------------------------------------------------------------------
# T11: broad hazardous material firewall
# ---------------------------------------------------------------------------

def test_t11_broad_hazardous_firewall():
    """Unclassified row (no material_master_key) with MANUFACTURE_OR_USE must not
    produce fc001_permit_manufacture_or_use — permit class authority is the gate."""
    rows = [
        {"is_active": True, "material_master_key": None, "handling_mode_codes": ["MANUFACTURE_OR_USE"]},
    ]
    result = project_material_fc001_facts(rows)
    assert "fc001_permit_manufacture_or_use" not in result
    assert "fc001_managed_manufacture_or_use" not in result
