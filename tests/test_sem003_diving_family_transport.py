"""WO-E2E-OBJ01-SEM003-DIVING-FAMILY-FASTLANE-IMPLEMENT-001 (tai-api side).

Verifies the 5 new stable diving fields land in the LEG transport allowlist,
the CONSTRUCTION consumer schema, the factory persistence schema, and the
consumer-override merge tuple — with the missing-not-false and no-parent-alias
invariants the WO requires.

Companion to the LEG PR that partitions 27 diving atoms into 5 subtype
classes. LEG runtime side is out of scope for this file.
"""
from __future__ import annotations

from clients.leg_runtime_client import _LEG_INPUT_FIELDS
from schemas.legal_engine import SafeConstructionConsumerInput
from routers.factories import FactoryCreate, FactoryUpdate
from services.safe_construction_leg_runtime import (
    SAFE_CST_OVERRIDE_FIELDS,
    SEM003_DIVING_OVERRIDE_FIELDS,
)
from services.safe_construction_canonical_assembler import (
    RUNTIME_INPUT_FIELDS,
    TARGET_FIELDS,
)


DIVING5 = (
    "has_scuba_diving",
    "has_surface_supplied_diving",
    "has_pressure_adjustment_chamber",
    "supplies_air_to_diver_from_air_compressor",
    "supplies_breathing_gas_to_diver_from_cylinder",
)


# ==========================================================================
# A1 — Exact 5 fields land in _LEG_INPUT_FIELDS (transport allowlist)
# ==========================================================================
def test_A1_diving_five_fields_in_transport_allowlist():
    for field in DIVING5:
        assert field in _LEG_INPUT_FIELDS, field
    # No duplicates
    assert len(_LEG_INPUT_FIELDS) == len(set(_LEG_INPUT_FIELDS))


def test_A1_each_field_registered_exactly_once():
    for field in DIVING5:
        assert _LEG_INPUT_FIELDS.count(field) == 1, field


# ==========================================================================
# A2 — Missing (None) omitted from consumer schema serialization
# ==========================================================================
def test_A2_missing_omitted_in_model_dump():
    body = SafeConstructionConsumerInput()
    dumped = body.model_dump(exclude_none=True)
    for field in DIVING5:
        assert field not in dumped, f"{field} must be omitted when unset"


# ==========================================================================
# A3 — Explicit false preserved in model_dump
# ==========================================================================
def test_A3_false_preserved_in_model_dump():
    payload = {f: False for f in DIVING5}
    body = SafeConstructionConsumerInput(**payload)
    dumped = body.model_dump(exclude_none=True)
    for field in DIVING5:
        assert dumped[field] is False, field


# ==========================================================================
# A4 — Explicit true preserved in model_dump
# ==========================================================================
def test_A4_true_preserved_in_model_dump():
    payload = {f: True for f in DIVING5}
    body = SafeConstructionConsumerInput(**payload)
    dumped = body.model_dump(exclude_none=True)
    for field in DIVING5:
        assert dumped[field] is True, field


# ==========================================================================
# A5 — Cylinder pressure remains numeric (unchanged existing field)
# ==========================================================================
def test_A5_cylinder_pressure_field_unchanged_in_transport():
    # WO §21: reuse existing numeric — do not add new numeric input
    assert "breathing_gas_cylinder_pressure_kgf_cm2" in _LEG_INPUT_FIELDS


# ==========================================================================
# A6 — No alias from has_diving → subtype
# ==========================================================================
def test_A6_no_parent_to_subtype_alias():
    """Setting has_diving=true on the consumer input must NOT auto-populate
    any of the 5 new subtype fields."""
    body = SafeConstructionConsumerInput(has_diving=True)
    dumped = body.model_dump(exclude_none=True)
    assert dumped.get("has_diving") is True
    for field in DIVING5:
        assert field not in dumped, f"{field} must not be auto-set by has_diving"


# ==========================================================================
# A7 — No alias from has_air_compressor → diver-supply fields
# ==========================================================================
def test_A7_no_air_compressor_to_diver_supply_alias():
    # has_air_compressor is not on SafeConstructionConsumerInput anyway;
    # verify none of the 5 new supply booleans appear when it's absent.
    body = SafeConstructionConsumerInput()
    dumped = body.model_dump(exclude_none=True)
    assert "supplies_air_to_diver_from_air_compressor" not in dumped
    assert "supplies_breathing_gas_to_diver_from_cylinder" not in dumped


# ==========================================================================
# A8 — No alias from has_high_pressure_work → pressure chamber
# ==========================================================================
def test_A8_no_hpw_to_pressure_chamber_alias():
    # If consumer sets has_high_pressure_gas true, has_pressure_adjustment_chamber
    # must remain absent (they are semantically distinct axes).
    body = SafeConstructionConsumerInput(has_high_pressure_gas=True)
    dumped = body.model_dump(exclude_none=True)
    assert dumped.get("has_high_pressure_gas") is True
    assert "has_pressure_adjustment_chamber" not in dumped


# ==========================================================================
# Factory persistence — 5 fields accepted by Create + Update
# ==========================================================================
def test_factory_create_accepts_five_diving_fields():
    payload = {f: True for f in DIVING5}
    row = FactoryCreate(company_id="c1", name="test", **payload)
    for field in DIVING5:
        assert getattr(row, field) is True, field


def test_factory_update_accepts_five_diving_fields():
    payload = {f: False for f in DIVING5}
    row = FactoryUpdate(**payload)
    for field in DIVING5:
        assert getattr(row, field) is False, field


def test_factory_create_default_none_for_all_five():
    row = FactoryCreate(company_id="c1", name="test")
    for field in DIVING5:
        assert getattr(row, field) is None, field


# ==========================================================================
# Consumer-override merge tuple — 5 fields extended, RUNTIME20 frozen
# ==========================================================================
def test_sem003_override_tuple_is_exact_5():
    assert set(SEM003_DIVING_OVERRIDE_FIELDS) == set(DIVING5)
    assert len(SEM003_DIVING_OVERRIDE_FIELDS) == 5


def test_safe_cst_override_extends_runtime20_with_diving5():
    # RUNTIME_INPUT_FIELDS stays at 20 (audit-frozen); SAFE_CST_OVERRIDE_FIELDS
    # now contains 25 = 20 + 5.
    assert len(RUNTIME_INPUT_FIELDS) == 20
    assert set(SAFE_CST_OVERRIDE_FIELDS) == set(RUNTIME_INPUT_FIELDS) | set(DIVING5)
    for field in DIVING5:
        assert field in SAFE_CST_OVERRIDE_FIELDS
    # Assembler contract remains 27 unchanged (5 new fields are consumer-side
    # additions, not canonical assembler output).
    assert len(TARGET_FIELDS) == 27
    for field in DIVING5:
        assert field not in TARGET_FIELDS  # NOT part of the frozen 27


# ==========================================================================
# Guard: 5 fields do not appear as unexpected in existing tuples
# ==========================================================================
def test_diving5_not_in_runtime20():
    for field in DIVING5:
        assert field not in RUNTIME_INPUT_FIELDS, (
            f"{field} must NOT be added to RUNTIME_INPUT_FIELDS (audit-frozen 20)"
        )


def test_diving5_not_in_target27():
    for field in DIVING5:
        assert field not in TARGET_FIELDS, (
            f"{field} must NOT be added to TARGET_FIELDS (audit-frozen 27)"
        )
