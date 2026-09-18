"""WO-E2E-OBJ01-SEM003-DIVING-FAMILY-FASTLANE-IMPLEMENT-001 + PATCH-1 (tai-api side).

Verifies the 5 stable diving booleans + existing numeric cylinder pressure
land in the LEG transport allowlist, the CONSTRUCTION consumer schema, and
the consumer-override merge tuple — with the missing-not-false and
no-parent-alias invariants the WO requires.

PATCH-1: factory persistence path removed (production `factories` table has
no such columns; runtime input authority is `SafeConstructionConsumerInput`
+ `SAFE_CST_OVERRIDE_FIELDS`, not factories).
Companion to LEG PR that partitions 27 diving atoms into 5 subtype classes.
"""
from __future__ import annotations

from clients.leg_runtime_client import _LEG_INPUT_FIELDS
from schemas.legal_engine import SafeConstructionConsumerInput
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
NUMERIC = "breathing_gas_cylinder_pressure_kgf_cm2"


# ==========================================================================
# A1 — Five booleans accepted by consumer schema
# ==========================================================================
def test_A1_five_booleans_accepted_by_consumer():
    payload = {f: True for f in DIVING5}
    body = SafeConstructionConsumerInput(**payload)
    for field in DIVING5:
        assert getattr(body, field) is True, field


# ==========================================================================
# A2 — Cylinder pressure numeric accepted by consumer schema (PATCH-1)
# ==========================================================================
def test_A2_numeric_pressure_accepted_by_consumer():
    body = SafeConstructionConsumerInput(
        supplies_breathing_gas_to_diver_from_cylinder=True,
        **{NUMERIC: 12.5},
    )
    assert getattr(body, NUMERIC) == 12.5


# ==========================================================================
# A3 — Missing (None) omitted from model_dump
# ==========================================================================
def test_A3_missing_omitted():
    body = SafeConstructionConsumerInput()
    dumped = body.model_dump(exclude_none=True)
    for field in DIVING5:
        assert field not in dumped, field
    assert NUMERIC not in dumped


# ==========================================================================
# A4 — Explicit false preserved
# ==========================================================================
def test_A4_false_preserved():
    payload = {f: False for f in DIVING5}
    body = SafeConstructionConsumerInput(**payload)
    dumped = body.model_dump(exclude_none=True)
    for field in DIVING5:
        assert dumped[field] is False, field


# ==========================================================================
# A5 — Zero numeric preserved (0 is a real pressure reading)
# ==========================================================================
def test_A5_zero_numeric_preserved():
    body = SafeConstructionConsumerInput(**{NUMERIC: 0.0})
    dumped = body.model_dump(exclude_none=True)
    assert dumped[NUMERIC] == 0.0


# ==========================================================================
# A6 — SAFE_CST_OVERRIDE_FIELDS contains SEM003 prior 6 (5 bool + numeric).
#      Prior IMPLEMENT-001 baseline; the newer DIVING-COVERAGE-BACKLOG WO
#      extends SEM003 override to 9 (prior 6 + 3 new), so this now asserts
#      subset containment; exact count of 9 lives in the coverage-backlog
#      test file (test_diving_coverage_backlog_transport.py :: A5).
# ==========================================================================
def test_A6_safe_cst_override_contains_sem003_prior_six():
    prior_six = set(DIVING5) | {NUMERIC}
    assert prior_six.issubset(set(SEM003_DIVING_OVERRIDE_FIELDS))
    for field in DIVING5:
        assert field in SAFE_CST_OVERRIDE_FIELDS
    assert NUMERIC in SAFE_CST_OVERRIDE_FIELDS


# ==========================================================================
# A7 — RUNTIME_INPUT_FIELDS remains exact 20 (audit-frozen)
# ==========================================================================
def test_A7_runtime20_frozen():
    assert len(RUNTIME_INPUT_FIELDS) == 20
    for field in DIVING5:
        assert field not in RUNTIME_INPUT_FIELDS
    assert NUMERIC not in RUNTIME_INPUT_FIELDS


# ==========================================================================
# A8 — TARGET_FIELDS unchanged at exact 27 (audit-frozen)
# ==========================================================================
def test_A8_target27_unchanged():
    assert len(TARGET_FIELDS) == 27
    for field in DIVING5:
        assert field not in TARGET_FIELDS
    assert NUMERIC not in TARGET_FIELDS


# ==========================================================================
# A9 — _LEG_INPUT_FIELDS: 5 new fields registered; numeric NOT duplicated
# ==========================================================================
def test_A9_leg_input_fields_no_numeric_duplication():
    for field in DIVING5:
        assert field in _LEG_INPUT_FIELDS
        assert _LEG_INPUT_FIELDS.count(field) == 1
    # PATCH-1: cylinder pressure was already in _LEG_INPUT_FIELDS pre-PR;
    # must remain exactly once (no duplication).
    assert NUMERIC in _LEG_INPUT_FIELDS
    assert _LEG_INPUT_FIELDS.count(NUMERIC) == 1
    # Global dedup guard
    assert len(_LEG_INPUT_FIELDS) == len(set(_LEG_INPUT_FIELDS))


# ==========================================================================
# A10 — No factory DB persistence dependency (PATCH-1 revert)
# ==========================================================================
def test_A10_no_factory_persistence_dependency():
    """PATCH-1 removed 5 diving Optional[bool] fields from FactoryCreate/Update
    because production `factories` table has no such columns and the runtime
    input authority is the consumer override path, not factory persistence."""
    from routers.factories import FactoryCreate, FactoryUpdate
    # Field names must NOT appear on FactoryCreate model
    create_fields = set(FactoryCreate.model_fields.keys())
    for field in DIVING5:
        assert field not in create_fields, (
            f"{field} should NOT be on FactoryCreate (PATCH-1 removed)"
        )
    assert NUMERIC not in create_fields
    # Same for FactoryUpdate
    update_fields = set(FactoryUpdate.model_fields.keys())
    for field in DIVING5:
        assert field not in update_fields, (
            f"{field} should NOT be on FactoryUpdate (PATCH-1 removed)"
        )
    assert NUMERIC not in update_fields
    # Existing has_diving on Factory{Create,Update} unchanged
    assert "has_diving" in create_fields
    assert "has_diving" in update_fields


# ==========================================================================
# No-parent-alias guards (unchanged from IMPLEMENT-001)
# ==========================================================================
def test_no_alias_from_has_diving_to_subtypes():
    body = SafeConstructionConsumerInput(has_diving=True)
    dumped = body.model_dump(exclude_none=True)
    assert dumped.get("has_diving") is True
    for field in DIVING5:
        assert field not in dumped
    assert NUMERIC not in dumped


def test_no_alias_from_hp_gas_to_pressure_chamber():
    body = SafeConstructionConsumerInput(has_high_pressure_gas=True)
    dumped = body.model_dump(exclude_none=True)
    assert dumped.get("has_high_pressure_gas") is True
    assert "has_pressure_adjustment_chamber" not in dumped
