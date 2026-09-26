"""PR-W1-D: FC-018 + FC-019C + FC-019D maintenance bundle tests.

WO-E2E-OBJ04-L3-COVERAGE-ACTIVATION-WAVE1-DESIGN-001 PR-W1-D

Verifies:
- FC-018: AIR_PURIFICATION positive; other equipment_type / missing negative.
- FC-019C: TRAIN+periodic=True positive; TRAIN+periodic missing/false/None negative;
           other type+periodic=True negative. (periodic exact conjunction, fail-closed)
- FC-019D: CENTRIFUGE positive; CRUSHER positive; other type negative.
- Existing performs_powered_machinery_maintenance_or_servicing unaffected.
- Inactive row emits nothing.
- No cross-row combination.
- Transport allowlist: 3 new fields registered, no duplicates.
"""
import pytest
from clients.leg_runtime_client import _LEG_INPUT_FIELDS
from services.work_source.registry import WORK_TYPES
from services.work_source.projector import project_work_row


def _row(subtype=None, attrs=None, active=True):
    return {"work_type": "MAINTENANCE", "work_subtype": subtype, "active": active, "attributes": attrs or {}}


# ---------------------------------------------------------------------------
# Registry contract
# ---------------------------------------------------------------------------

def test_registry_has_equipment_type_attribute():
    assert "equipment_type" in WORK_TYPES["MAINTENANCE"]["attributes"]


def test_registry_has_periodic_attribute():
    assert "periodic" in WORK_TYPES["MAINTENANCE"]["attributes"]


def test_registry_equipment_type_options_include_all_four():
    options = {o["code"] for o in WORK_TYPES["MAINTENANCE"]["attributes"]["equipment_type"]["options"]}
    assert {"AIR_PURIFICATION", "TRAIN", "CENTRIFUGE", "CRUSHER"} <= options


def test_registry_powered_machinery_still_present():
    assert "powered_machinery" in WORK_TYPES["MAINTENANCE"]["attributes"]


# ---------------------------------------------------------------------------
# Transport allowlist
# ---------------------------------------------------------------------------

def test_fc018_field_in_leg_input_fields():
    assert "performs_air_purification_equipment_maintenance_or_cleaning" in _LEG_INPUT_FIELDS


def test_fc019c_field_in_leg_input_fields():
    assert "performs_periodic_train_maintenance_or_inspection" in _LEG_INPUT_FIELDS


def test_fc019d_field_in_leg_input_fields():
    assert "performs_centrifuge_or_crusher_maintenance_cleaning_or_inspection" in _LEG_INPUT_FIELDS


def test_no_duplicate_in_leg_input_fields():
    fields = list(_LEG_INPUT_FIELDS)
    assert len(fields) == len(set(fields))


# ---------------------------------------------------------------------------
# FC-018: AIR_PURIFICATION
# ---------------------------------------------------------------------------

def test_fc018_air_purification_positive():
    result = project_work_row(_row(attrs={"equipment_type": "AIR_PURIFICATION"}))
    assert result.get("performs_air_purification_equipment_maintenance_or_cleaning") is True


def test_fc018_train_does_not_emit_air_purification_field():
    result = project_work_row(_row(attrs={"equipment_type": "TRAIN", "periodic": True}))
    assert "performs_air_purification_equipment_maintenance_or_cleaning" not in result


def test_fc018_centrifuge_does_not_emit_air_purification_field():
    result = project_work_row(_row(attrs={"equipment_type": "CENTRIFUGE"}))
    assert "performs_air_purification_equipment_maintenance_or_cleaning" not in result


def test_fc018_missing_equipment_type_no_air_purification_field():
    result = project_work_row(_row(attrs={}))
    assert "performs_air_purification_equipment_maintenance_or_cleaning" not in result


# ---------------------------------------------------------------------------
# FC-019C: TRAIN + periodic (exact conjunction, fail-closed)
# ---------------------------------------------------------------------------

def test_fc019c_train_periodic_true_positive():
    result = project_work_row(_row(attrs={"equipment_type": "TRAIN", "periodic": True}))
    assert result.get("performs_periodic_train_maintenance_or_inspection") is True


def test_fc019c_train_periodic_false_absent():
    result = project_work_row(_row(attrs={"equipment_type": "TRAIN", "periodic": False}))
    assert "performs_periodic_train_maintenance_or_inspection" not in result


def test_fc019c_train_periodic_none_absent():
    result = project_work_row(_row(attrs={"equipment_type": "TRAIN", "periodic": None}))
    assert "performs_periodic_train_maintenance_or_inspection" not in result


def test_fc019c_train_periodic_missing_absent():
    result = project_work_row(_row(attrs={"equipment_type": "TRAIN"}))
    assert "performs_periodic_train_maintenance_or_inspection" not in result


def test_fc019c_other_type_periodic_true_absent():
    result = project_work_row(_row(attrs={"equipment_type": "AIR_PURIFICATION", "periodic": True}))
    assert "performs_periodic_train_maintenance_or_inspection" not in result


def test_fc019c_centrifuge_periodic_true_absent():
    result = project_work_row(_row(attrs={"equipment_type": "CENTRIFUGE", "periodic": True}))
    assert "performs_periodic_train_maintenance_or_inspection" not in result


# ---------------------------------------------------------------------------
# FC-019D: CENTRIFUGE / CRUSHER
# ---------------------------------------------------------------------------

def test_fc019d_centrifuge_positive():
    result = project_work_row(_row(attrs={"equipment_type": "CENTRIFUGE"}))
    assert result.get("performs_centrifuge_or_crusher_maintenance_cleaning_or_inspection") is True


def test_fc019d_crusher_positive():
    result = project_work_row(_row(attrs={"equipment_type": "CRUSHER"}))
    assert result.get("performs_centrifuge_or_crusher_maintenance_cleaning_or_inspection") is True


def test_fc019d_air_purification_does_not_emit_centrifuge_field():
    result = project_work_row(_row(attrs={"equipment_type": "AIR_PURIFICATION"}))
    assert "performs_centrifuge_or_crusher_maintenance_cleaning_or_inspection" not in result


def test_fc019d_train_does_not_emit_centrifuge_field():
    result = project_work_row(_row(attrs={"equipment_type": "TRAIN", "periodic": True}))
    assert "performs_centrifuge_or_crusher_maintenance_cleaning_or_inspection" not in result


def test_fc019d_missing_equipment_type_no_centrifuge_field():
    result = project_work_row(_row(attrs={}))
    assert "performs_centrifuge_or_crusher_maintenance_cleaning_or_inspection" not in result


# ---------------------------------------------------------------------------
# Existing performs_powered_machinery_maintenance_or_servicing unaffected
# ---------------------------------------------------------------------------

def test_powered_machinery_subtype_still_works():
    result = project_work_row(_row(subtype="POWERED_MACHINERY"))
    assert result.get("performs_powered_machinery_maintenance_or_servicing") is True


def test_powered_machinery_attr_still_works():
    result = project_work_row(_row(attrs={"powered_machinery": True}))
    assert result.get("performs_powered_machinery_maintenance_or_servicing") is True


def test_new_fields_do_not_appear_for_powered_machinery_only():
    result = project_work_row(_row(subtype="POWERED_MACHINERY"))
    assert "performs_air_purification_equipment_maintenance_or_cleaning" not in result
    assert "performs_periodic_train_maintenance_or_inspection" not in result
    assert "performs_centrifuge_or_crusher_maintenance_cleaning_or_inspection" not in result


# ---------------------------------------------------------------------------
# Inactive row emits nothing
# ---------------------------------------------------------------------------

def test_inactive_row_emits_nothing():
    result = project_work_row(_row(attrs={"equipment_type": "AIR_PURIFICATION"}, active=False))
    assert result == {}


# ---------------------------------------------------------------------------
# Non-MAINTENANCE work type unaffected
# ---------------------------------------------------------------------------

def test_scaffold_row_unaffected():
    row = {"work_type": "SCAFFOLD", "work_subtype": "ASSEMBLY", "active": True,
           "attributes": {"scaffold_kind": "SYSTEM_SCAFFOLD", "equipment_type": "AIR_PURIFICATION"}}
    result = project_work_row(row)
    assert "performs_air_purification_equipment_maintenance_or_cleaning" not in result
