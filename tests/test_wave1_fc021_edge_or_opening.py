"""PR-W1-C: FC-021 work platform / path edge or opening fall risk tests.

WO-E2E-OBJ04-L3-COVERAGE-ACTIVATION-WAVE1-DESIGN-001 PR-W1-C

Verifies:
- Registry: edge_or_opening_fall_risk attribute present in HIGH_PLACE.
- Projector positive: HIGH_PLACE + edge_or_opening_fall_risk=True → field emitted.
- Projector negative: fall_risk / roof / no attrs → field absent.
- False / missing → field absent (fail-closed).
- Non-target coexistence: SCAFFOLD work unaffected.
- Transport allowlist: field registered, no duplicate.
"""
import pytest
from clients.leg_runtime_client import _LEG_INPUT_FIELDS
from services.work_source.registry import WORK_TYPES as WORK_TYPE_REGISTRY
from services.work_source.projector import project_work_row


# ---------------------------------------------------------------------------
# Registry contract
# ---------------------------------------------------------------------------

def test_registry_has_edge_or_opening_fall_risk_attribute():
    attrs = WORK_TYPE_REGISTRY["HIGH_PLACE"]["attributes"]
    assert "edge_or_opening_fall_risk" in attrs


def test_registry_edge_or_opening_fall_risk_type_boolean():
    attr = WORK_TYPE_REGISTRY["HIGH_PLACE"]["attributes"]["edge_or_opening_fall_risk"]
    assert attr["type"] == "boolean"


def test_registry_fall_risk_still_present():
    attrs = WORK_TYPE_REGISTRY["HIGH_PLACE"]["attributes"]
    assert "fall_risk" in attrs


def test_registry_roof_still_present():
    attrs = WORK_TYPE_REGISTRY["HIGH_PLACE"]["attributes"]
    assert "roof" in attrs


# ---------------------------------------------------------------------------
# Transport allowlist
# ---------------------------------------------------------------------------

def test_field_in_leg_input_fields():
    assert "has_work_platform_or_path_edge_or_opening_fall_risk" in _LEG_INPUT_FIELDS


def test_no_duplicate_in_leg_input_fields():
    fields = list(_LEG_INPUT_FIELDS)
    assert len(fields) == len(set(fields))


# ---------------------------------------------------------------------------
# Projector: positive emission
# ---------------------------------------------------------------------------

def _row(work_type, subtype=None, attrs=None):
    return {"work_type": work_type, "work_subtype": subtype, "active": True, "attributes": attrs or {}}


def test_edge_or_opening_true_emits_field():
    result = project_work_row(_row("HIGH_PLACE", attrs={"edge_or_opening_fall_risk": True}))
    assert result.get("has_work_platform_or_path_edge_or_opening_fall_risk") is True


def test_edge_or_opening_true_with_subtype_emits_field():
    result = project_work_row(_row("HIGH_PLACE", subtype="ROOF", attrs={"edge_or_opening_fall_risk": True}))
    assert result.get("has_work_platform_or_path_edge_or_opening_fall_risk") is True


# ---------------------------------------------------------------------------
# Projector: negative / absent
# ---------------------------------------------------------------------------

def test_edge_or_opening_false_field_absent():
    result = project_work_row(_row("HIGH_PLACE", attrs={"edge_or_opening_fall_risk": False}))
    assert "has_work_platform_or_path_edge_or_opening_fall_risk" not in result


def test_edge_or_opening_missing_field_absent():
    result = project_work_row(_row("HIGH_PLACE", attrs={}))
    assert "has_work_platform_or_path_edge_or_opening_fall_risk" not in result


def test_edge_or_opening_none_field_absent():
    result = project_work_row(_row("HIGH_PLACE", attrs={"edge_or_opening_fall_risk": None}))
    assert "has_work_platform_or_path_edge_or_opening_fall_risk" not in result


# ---------------------------------------------------------------------------
# Pre-existing HIGH_PLACE facts unaffected
# ---------------------------------------------------------------------------

def test_fall_risk_still_emits_performs_work_with_fall_risk():
    result = project_work_row(_row("HIGH_PLACE", attrs={"fall_risk": True}))
    assert result.get("performs_work_with_fall_risk") is True
    assert "has_work_platform_or_path_edge_or_opening_fall_risk" not in result


def test_roof_subtype_still_emits_performs_work_on_roof():
    result = project_work_row(_row("HIGH_PLACE", subtype="ROOF"))
    assert result.get("performs_work_on_roof") is True
    assert "has_work_platform_or_path_edge_or_opening_fall_risk" not in result


def test_both_fall_risk_and_edge_or_opening():
    result = project_work_row(_row("HIGH_PLACE", attrs={"fall_risk": True, "edge_or_opening_fall_risk": True}))
    assert result.get("performs_work_with_fall_risk") is True
    assert result.get("has_work_platform_or_path_edge_or_opening_fall_risk") is True


# ---------------------------------------------------------------------------
# Non-target: SCAFFOLD unaffected
# ---------------------------------------------------------------------------

def test_scaffold_work_does_not_emit_edge_or_opening_field():
    result = project_work_row(_row("SCAFFOLD", subtype="ASSEMBLY", attrs={"scaffold_kind": "SYSTEM_SCAFFOLD"}))
    assert "has_work_platform_or_path_edge_or_opening_fall_risk" not in result
