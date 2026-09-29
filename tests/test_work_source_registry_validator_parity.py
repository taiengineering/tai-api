"""WO-WORK-SOURCE-REGISTRY-VALIDATOR-PARITY-001 — T1~T10 contract tests.

Registry-declared source attributes (uses_*, is_*) must pass validation.
Unregistered canonical-looking attributes must be blocked.
"""
from __future__ import annotations

import pytest

from services.work_source.registry import registry_public, work_type_spec
from services.work_source.store import WorkSourceValidationError, validate_payload
from services.work_source.projector import project_work_row


# ── T1: registered uses_* PASS ───────────────────────────────────────────────
def test_T1_registered_uses_machinery_pass():
    row = validate_payload(
        {"work_type": "EXCAVATION", "attributes": {"uses_machinery": True}, "active": True}
    )
    assert row["attributes"]["uses_machinery"] is True


# ── T2: registered is_* PASS ─────────────────────────────────────────────────
def test_T2_registered_is_dalbi_pass():
    row = validate_payload(
        {"work_type": "SCAFFOLD", "attributes": {"is_dalbi": True}, "active": True}
    )
    assert row["attributes"]["is_dalbi"] is True


# ── T3: registered boolean strictness ────────────────────────────────────────
def test_T3_registered_bool_string_true_rejected():
    with pytest.raises(WorkSourceValidationError, match="expected boolean"):
        validate_payload(
            {"work_type": "EXCAVATION", "attributes": {"uses_machinery": "true"}, "active": True}
        )


def test_T3_registered_bool_string_false_rejected():
    with pytest.raises(WorkSourceValidationError, match="expected boolean"):
        validate_payload(
            {"work_type": "EXCAVATION", "attributes": {"uses_machinery": "false"}, "active": True}
        )


# ── T4: registered number strictness preserved ───────────────────────────────
def test_T4_number_bool_rejected():
    with pytest.raises(WorkSourceValidationError, match="expected number"):
        validate_payload(
            {"work_type": "SCAFFOLD", "attributes": {"height_m": True}, "active": True}
        )


def test_T4_number_nan_rejected():
    import math
    with pytest.raises(WorkSourceValidationError, match="must be finite"):
        validate_payload(
            {"work_type": "SCAFFOLD", "attributes": {"height_m": math.nan}, "active": True}
        )


def test_T4_number_negative_rejected():
    with pytest.raises(WorkSourceValidationError, match="must be >= 0"):
        validate_payload(
            {"work_type": "SCAFFOLD", "attributes": {"height_m": -1}, "active": True}
        )


# ── T5: unregistered canonical injection FAIL ────────────────────────────────
def test_T5_unregistered_has_prefix_rejected():
    with pytest.raises(WorkSourceValidationError, match="canonical LEG fields"):
        validate_payload(
            {"work_type": "EXCAVATION", "attributes": {"has_boiler": True}, "active": True}
        )


def test_T5_unregistered_has_press_rejected():
    with pytest.raises(WorkSourceValidationError, match="canonical LEG fields"):
        validate_payload(
            {"work_type": "FORKLIFT", "attributes": {"has_press": True}, "active": True}
        )


# ── T6: wrong-work-type source attribute FAIL ────────────────────────────────
def test_T6_uses_machinery_on_high_place_rejected():
    with pytest.raises(WorkSourceValidationError):
        validate_payload(
            {"work_type": "HIGH_PLACE", "attributes": {"uses_machinery": True}, "active": True}
        )


def test_T6_is_dalbi_on_excavation_rejected():
    with pytest.raises(WorkSourceValidationError):
        validate_payload(
            {"work_type": "EXCAVATION", "attributes": {"is_dalbi": True}, "active": True}
        )


# ── T7: arbitrary canonical-looking fields FAIL ──────────────────────────────
def test_T7_canonical_prefixes_unregistered_rejected():
    for prefix in ("has_fake", "performs_fake", "uses_fake", "is_fake"):
        with pytest.raises(WorkSourceValidationError, match="canonical LEG fields"):
            validate_payload(
                {"work_type": "EXCAVATION", "attributes": {prefix: True}, "active": True}
            )


# ── T8: ordinary unknown attribute FAIL ──────────────────────────────────────
def test_T8_unknown_attribute_rejected():
    with pytest.raises(WorkSourceValidationError, match="unknown attribute"):
        validate_payload(
            {"work_type": "EXCAVATION", "attributes": {"foo_bar": True}, "active": True}
        )


def test_T8_unknown_attribute_on_scaffold_rejected():
    with pytest.raises(WorkSourceValidationError, match="unknown attribute"):
        validate_payload(
            {"work_type": "SCAFFOLD", "attributes": {"no_such_key": True}, "active": True}
        )


# ── T9: registry_public contract unchanged ───────────────────────────────────
def test_T9_registry_public_structure():
    data = registry_public()
    assert "work_types" in data
    for item in data["work_types"]:
        assert "code" in item
        assert "label" in item
        assert "subtypes" in item
        assert "attributes" in item
        for attr in item["attributes"]:
            assert "code" in attr
            assert "label" in attr
            assert "type" in attr
            if attr.get("options"):
                for opt in attr["options"]:
                    assert "code" in opt
                    assert "label" in opt


def test_T9_excavation_uses_machinery_in_public_registry():
    data = registry_public()
    exc = next(i for i in data["work_types"] if i["code"] == "EXCAVATION")
    attr_codes = {a["code"] for a in exc["attributes"]}
    assert "uses_machinery" in attr_codes


def test_T9_scaffold_is_dalbi_in_public_registry():
    data = registry_public()
    sc = next(i for i in data["work_types"] if i["code"] == "SCAFFOLD")
    attr_codes = {a["code"] for a in sc["attributes"]}
    assert "is_dalbi" in attr_codes


# ── T10: projector regression ─────────────────────────────────────────────────
def test_T10_excavation_uses_machinery_projects_correctly():
    row = validate_payload(
        {"work_type": "EXCAVATION", "attributes": {"uses_machinery": True}, "active": True}
    )
    facts = project_work_row(row)
    assert facts == {"excavation_machinery_in_use": True}
    assert "uses_machinery" not in facts


def test_T10_excavation_uses_machinery_false_emits_nothing():
    row = validate_payload(
        {"work_type": "EXCAVATION", "attributes": {"uses_machinery": False}, "active": True}
    )
    facts = project_work_row(row)
    assert facts == {}


def test_T10_scaffold_is_dalbi_assembly_projects_correctly():
    row = validate_payload(
        {
            "work_type": "SCAFFOLD",
            "work_subtype": "ASSEMBLY",
            "attributes": {"is_dalbi": True},
            "active": True,
        }
    )
    facts = project_work_row(row)
    assert "has_scaffold" in facts
    assert "performs_scaffold_assembly_dismantle_or_modification_on_dalbi_or_ge5m_scaffold" in facts
    assert facts["performs_scaffold_assembly_dismantle_or_modification_on_dalbi_or_ge5m_scaffold"] is True


def test_T10_no_new_canonical_facts_added():
    row_exc = validate_payload(
        {"work_type": "EXCAVATION", "attributes": {"uses_machinery": True}, "active": True}
    )
    facts_exc = project_work_row(row_exc)
    assert set(facts_exc.keys()) == {"excavation_machinery_in_use"}

    row_sc = validate_payload(
        {
            "work_type": "SCAFFOLD",
            "work_subtype": "ASSEMBLY",
            "attributes": {"is_dalbi": True},
            "active": True,
        }
    )
    facts_sc = project_work_row(row_sc)
    assert "has_scaffold" in facts_sc
    assert "performs_scaffold_assembly_dismantle_or_modification_on_dalbi_or_ge5m_scaffold" in facts_sc
    assert "excavation_machinery_in_use" not in facts_sc
