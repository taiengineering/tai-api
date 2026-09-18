"""WO-E2E-OBJ01-HIGH-PRESSURE-COMMON-COVERAGE-INTEGRATED-IMPLEMENT-001 (tai-api side).

Verifies:
  - 4 newly consumer-wired HP-common fields (3 pre-existing on transport
    allowlist + 1 new has_caisson_work) reach the consumer schema and
    merge tuple.
  - has_caisson_work is the ONLY new LEG transport field (215 → 216).
  - SEM-003 override count reduces 9 → 8 (has_pressure_adjustment_chamber
    removed and moved to HP-common).
  - HP-common override count = exact 5.
  - SAFE_CST_OVERRIDE_FIELDS unique count = 33 (20 + 8 + 5).
  - RUNTIME_INPUT_FIELDS(20) unchanged.
  - Missing != false invariants; no parent-alias.
  - has_pressure_adjustment_chamber remains usable when has_diving=false.
  - No factory-list persistence.
"""
from __future__ import annotations

import pytest

from clients.leg_runtime_client import _LEG_INPUT_FIELDS
from schemas.legal_engine import SafeConstructionConsumerInput
from services.safe_construction_leg_runtime import (
    SAFE_CST_OVERRIDE_FIELDS,
    SEM003_DIVING_OVERRIDE_FIELDS,
    HIGH_PRESSURE_COMMON_OVERRIDE_FIELDS,
)
from services.safe_construction_canonical_assembler import (
    RUNTIME_INPUT_FIELDS,
    TARGET_FIELDS,
)


HP_COMMON_EXACT_5 = (
    "has_high_pressure_work",
    "has_pressure_adjustment_chamber",
    "has_air_compressor",
    "supplies_air_to_high_pressure_workroom_or_airlock",
    "has_caisson_work",
)
SEM003_EXACT_8_AFTER_REGROUP = (
    "has_scuba_diving",
    "has_surface_supplied_diving",
    "supplies_air_to_diver_from_air_compressor",
    "supplies_breathing_gas_to_diver_from_cylinder",
    "breathing_gas_cylinder_pressure_kgf_cm2",
    "diving_depth_m",
    "diving_surface_ascent_restricted",
    "diving_decompression_stop_required",
)
NEW_CONSUMER_WIRED_4 = (
    "has_high_pressure_work",
    "has_air_compressor",
    "supplies_air_to_high_pressure_workroom_or_airlock",
    "has_caisson_work",
)


# ==========================================================================
# A1 — Consumer schema accepts the 4 newly wired HP-common fields
# ==========================================================================
def test_A1_consumer_accepts_new_hp_common_fields():
    body = SafeConstructionConsumerInput(
        has_high_pressure_work=True,
        has_air_compressor=True,
        supplies_air_to_high_pressure_workroom_or_airlock=True,
        has_caisson_work=True,
    )
    for f in NEW_CONSUMER_WIRED_4:
        assert getattr(body, f) is True, f


# ==========================================================================
# A2 — has_caisson_work registered in _LEG_INPUT_FIELDS (exactly once)
# ==========================================================================
def test_A2_has_caisson_work_in_allowlist():
    assert "has_caisson_work" in _LEG_INPUT_FIELDS
    assert _LEG_INPUT_FIELDS.count("has_caisson_work") == 1


# ==========================================================================
# A3 — _LEG_INPUT_FIELDS exact 216 (215 → 216 via +has_caisson_work only)
# ==========================================================================
def test_A3_leg_input_fields_216():
    assert len(_LEG_INPUT_FIELDS) == 216
    assert len(set(_LEG_INPUT_FIELDS)) == 216
    # The 3 shared HP fields already existed pre-WO; must not be duplicated.
    for f in ("has_high_pressure_work",
              "has_air_compressor",
              "supplies_air_to_high_pressure_workroom_or_airlock",
              "has_pressure_adjustment_chamber"):
        assert _LEG_INPUT_FIELDS.count(f) == 1, f


# ==========================================================================
# A4 — SEM003_DIVING_OVERRIDE_FIELDS = exact 8 (chamber removed)
# ==========================================================================
def test_A4_sem003_regrouped_to_exact_8():
    assert len(SEM003_DIVING_OVERRIDE_FIELDS) == 8
    assert "has_pressure_adjustment_chamber" not in SEM003_DIVING_OVERRIDE_FIELDS
    assert set(SEM003_DIVING_OVERRIDE_FIELDS) == set(SEM003_EXACT_8_AFTER_REGROUP)


# ==========================================================================
# A5 — HIGH_PRESSURE_COMMON_OVERRIDE_FIELDS = exact 5
# ==========================================================================
def test_A5_hp_common_exact_5():
    assert len(HIGH_PRESSURE_COMMON_OVERRIDE_FIELDS) == 5
    assert set(HIGH_PRESSURE_COMMON_OVERRIDE_FIELDS) == set(HP_COMMON_EXACT_5)
    assert "has_pressure_adjustment_chamber" in HIGH_PRESSURE_COMMON_OVERRIDE_FIELDS


# ==========================================================================
# A6 — SAFE_CST_OVERRIDE_FIELDS unique count = 33 (RUNTIME20 + SEM003(8) + HP(5))
# ==========================================================================
def test_A6_safe_cst_override_unique_33():
    assert len(set(SAFE_CST_OVERRIDE_FIELDS)) == 33
    assert set(RUNTIME_INPUT_FIELDS).issubset(set(SAFE_CST_OVERRIDE_FIELDS))
    assert set(SEM003_DIVING_OVERRIDE_FIELDS).issubset(set(SAFE_CST_OVERRIDE_FIELDS))
    assert set(HIGH_PRESSURE_COMMON_OVERRIDE_FIELDS).issubset(set(SAFE_CST_OVERRIDE_FIELDS))


# ==========================================================================
# A7 — RUNTIME_INPUT_FIELDS remains exact 20 (audit-frozen)
# ==========================================================================
def test_A7_runtime20_frozen():
    assert len(RUNTIME_INPUT_FIELDS) == 20
    assert len(TARGET_FIELDS) == 27


# ==========================================================================
# A8 — None omitted; missing != false
# ==========================================================================
def test_A8_missing_omitted():
    body = SafeConstructionConsumerInput()
    dumped = body.model_dump(exclude_none=True)
    for f in NEW_CONSUMER_WIRED_4:
        assert f not in dumped, f
    # Also chamber (existing) must be absent when unset
    assert "has_pressure_adjustment_chamber" not in dumped


# ==========================================================================
# A9 — Explicit false preserved
# ==========================================================================
def test_A9_false_preserved():
    payload = {f: False for f in NEW_CONSUMER_WIRED_4}
    body = SafeConstructionConsumerInput(**payload)
    dumped = body.model_dump(exclude_none=True)
    for f in NEW_CONSUMER_WIRED_4:
        assert dumped[f] is False, f


# ==========================================================================
# A10 — has_pressure_adjustment_chamber remains a first-class override even
#        when has_diving=false (chamber = 고압작업자 OR 잠수작업자 공통 설비).
#        This is the correction: chamber is in HP-common, not SEM-003 Diving.
# ==========================================================================
def test_A10_chamber_independent_of_has_diving():
    body = SafeConstructionConsumerInput(
        has_diving=False,
        has_pressure_adjustment_chamber=True,
    )
    dumped = body.model_dump(exclude_none=True)
    assert dumped["has_diving"] is False
    assert dumped["has_pressure_adjustment_chamber"] is True
    # Merge tuple still carries chamber (it's in HP-common).
    assert "has_pressure_adjustment_chamber" in SAFE_CST_OVERRIDE_FIELDS
    # Chamber must NOT be in SEM-003 tuple after regroup.
    assert "has_pressure_adjustment_chamber" not in SEM003_DIVING_OVERRIDE_FIELDS


# ==========================================================================
# A11 — No factory-list persistence for any of the 4 newly wired fields
#        (WO §9 factory DB dependency = 0; §11 no DB migration).
# ==========================================================================
def test_A11_no_factory_persistence():
    from routers.factories import FactoryCreate, FactoryUpdate
    create_fields = set(FactoryCreate.model_fields.keys())
    update_fields = set(FactoryUpdate.model_fields.keys())
    for f in NEW_CONSUMER_WIRED_4:
        assert f not in create_fields, f
        assert f not in update_fields, f


# ==========================================================================
# A12 — No alias: has_high_pressure_work=true does NOT infer has_caisson_work
# ==========================================================================
def test_A12_no_alias_hp_to_caisson():
    body = SafeConstructionConsumerInput(has_high_pressure_work=True)
    dumped = body.model_dump(exclude_none=True)
    assert dumped["has_high_pressure_work"] is True
    assert "has_caisson_work" not in dumped
    assert "supplies_air_to_high_pressure_workroom_or_airlock" not in dumped


# ==========================================================================
# A13 — No alias: has_air_compressor=true does NOT infer HP-workroom supply
# ==========================================================================
def test_A13_no_alias_compressor_to_supply_hp():
    body = SafeConstructionConsumerInput(has_air_compressor=True)
    dumped = body.model_dump(exclude_none=True)
    assert dumped["has_air_compressor"] is True
    assert "supplies_air_to_high_pressure_workroom_or_airlock" not in dumped


# ==========================================================================
# Regression: no cross-contamination between SEM-003 and HP-common tuples
# ==========================================================================
@pytest.mark.parametrize("field", (
    "has_scuba_diving", "has_surface_supplied_diving",
    "supplies_air_to_diver_from_air_compressor",
    "supplies_breathing_gas_to_diver_from_cylinder",
    "breathing_gas_cylinder_pressure_kgf_cm2",
    "diving_depth_m", "diving_surface_ascent_restricted",
    "diving_decompression_stop_required",
))
def test_sem003_fields_only_in_sem003(field):
    assert field in SEM003_DIVING_OVERRIDE_FIELDS
    assert field not in HIGH_PRESSURE_COMMON_OVERRIDE_FIELDS


@pytest.mark.parametrize("field", HP_COMMON_EXACT_5)
def test_hp_common_fields_only_in_hp_common(field):
    assert field in HIGH_PRESSURE_COMMON_OVERRIDE_FIELDS
    assert field not in SEM003_DIVING_OVERRIDE_FIELDS
