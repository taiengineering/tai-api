"""WO-E2E-OBJ01-DIVING-COVERAGE-BACKLOG-FASTLANE-IMPLEMENT-001 (tai-api side).

Verifies the 3 new stable diving-coverage inputs land in the LEG transport
allowlist, the CONSTRUCTION consumer schema, and the consumer-override merge
tuple — while the audit-frozen RUNTIME20/TARGET27 counts and the SEM-003
previous 6 override fields remain intact. Missing-not-false and
no-parent-alias invariants apply.

New stable inputs (exact 3):
  - diving_depth_m                        (numeric, float)
  - diving_surface_ascent_restricted      (boolean)
  - diving_decompression_stop_required    (boolean)

Semantics:
  Art.547③/⑥ machine applicability =
    AND(has_surface_supplied_diving,
        OR(diving_depth_m >= 18,
           diving_surface_ascent_restricted,
           diving_decompression_stop_required))

No new evaluator, no new comparator, no factory DB persistence, no LEG
engine code change (published canonical AST is authority).
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


COVERAGE3 = (
    "diving_depth_m",
    "diving_surface_ascent_restricted",
    "diving_decompression_stop_required",
)
BOOL2 = (
    "diving_surface_ascent_restricted",
    "diving_decompression_stop_required",
)
NUMERIC = "diving_depth_m"

# Prior SEM-003 fields (kept for regression cross-check).
SEM003_PRIOR_SIX = (
    "has_scuba_diving",
    "has_surface_supplied_diving",
    "has_pressure_adjustment_chamber",
    "supplies_air_to_diver_from_air_compressor",
    "supplies_breathing_gas_to_diver_from_cylinder",
    "breathing_gas_cylinder_pressure_kgf_cm2",
)


# ==========================================================================
# A1 — 3 new fields accepted by consumer schema
# ==========================================================================
def test_A1_three_new_fields_accepted_by_consumer():
    body = SafeConstructionConsumerInput(
        has_surface_supplied_diving=True,
        diving_depth_m=18.0,
        diving_surface_ascent_restricted=True,
        diving_decompression_stop_required=False,
    )
    assert body.diving_depth_m == 18.0
    assert body.diving_surface_ascent_restricted is True
    assert body.diving_decompression_stop_required is False


# ==========================================================================
# A2 — None omitted from model_dump (missing != false)
# ==========================================================================
def test_A2_none_omitted():
    body = SafeConstructionConsumerInput()
    dumped = body.model_dump(exclude_none=True)
    for field in COVERAGE3:
        assert field not in dumped, field


# ==========================================================================
# A3 — Explicit false preserved (booleans)
# ==========================================================================
def test_A3_false_preserved():
    body = SafeConstructionConsumerInput(
        diving_surface_ascent_restricted=False,
        diving_decompression_stop_required=False,
    )
    dumped = body.model_dump(exclude_none=True)
    assert dumped["diving_surface_ascent_restricted"] is False
    assert dumped["diving_decompression_stop_required"] is False


# ==========================================================================
# A4 — Numeric depth 0 preserved (0 m is a real reading, missing != 0)
# ==========================================================================
def test_A4_numeric_zero_preserved():
    body = SafeConstructionConsumerInput(diving_depth_m=0.0)
    dumped = body.model_dump(exclude_none=True)
    assert dumped[NUMERIC] == 0.0


# ==========================================================================
# A4b — Numeric depth boundary values preserved (17.9, 18)
# ==========================================================================
def test_A4b_depth_boundary_values_preserved():
    for depth in (17.9, 18.0, 30.0):
        body = SafeConstructionConsumerInput(diving_depth_m=depth)
        dumped = body.model_dump(exclude_none=True)
        assert dumped[NUMERIC] == depth, depth


# ==========================================================================
# A5 — SEM003 override count = 9 (5 prior bool + 1 prior numeric + 3 new)
# ==========================================================================
def test_A5_sem003_override_count_is_nine():
    assert len(SEM003_DIVING_OVERRIDE_FIELDS) == 9
    expected = set(SEM003_PRIOR_SIX) | set(COVERAGE3)
    assert set(SEM003_DIVING_OVERRIDE_FIELDS) == expected
    # Merge tuple contains the 3 new fields too.
    for field in COVERAGE3:
        assert field in SAFE_CST_OVERRIDE_FIELDS


# ==========================================================================
# A6 — RUNTIME_INPUT_FIELDS remains exact 20 (audit-frozen)
# ==========================================================================
def test_A6_runtime20_frozen():
    assert len(RUNTIME_INPUT_FIELDS) == 20
    for field in COVERAGE3:
        assert field not in RUNTIME_INPUT_FIELDS


# ==========================================================================
# A6b — TARGET_FIELDS remains exact 27 (audit-frozen)
# ==========================================================================
def test_A6b_target27_frozen():
    assert len(TARGET_FIELDS) == 27
    for field in COVERAGE3:
        assert field not in TARGET_FIELDS


# ==========================================================================
# A7 — _LEG_INPUT_FIELDS: exact +3, no duplication, global dedup
# ==========================================================================
def test_A7_leg_input_fields_plus_three_only():
    for field in COVERAGE3:
        assert field in _LEG_INPUT_FIELDS
        assert _LEG_INPUT_FIELDS.count(field) == 1
    # Prior SEM-003 fields unchanged in transport allowlist.
    for field in SEM003_PRIOR_SIX:
        assert field in _LEG_INPUT_FIELDS
        assert _LEG_INPUT_FIELDS.count(field) == 1
    # Global dedup guard.
    assert len(_LEG_INPUT_FIELDS) == len(set(_LEG_INPUT_FIELDS))


# ==========================================================================
# A8 — No factory DB persistence dependency (WO §4 / §16)
# ==========================================================================
def test_A8_no_factory_persistence_dependency():
    """3 new coverage fields must NOT be added to FactoryCreate/Update.
    Runtime input authority is the consumer override path only."""
    from routers.factories import FactoryCreate, FactoryUpdate
    create_fields = set(FactoryCreate.model_fields.keys())
    update_fields = set(FactoryUpdate.model_fields.keys())
    for field in COVERAGE3:
        assert field not in create_fields, (
            f"{field} must NOT be on FactoryCreate (WO §4 factory dependency = 0)"
        )
        assert field not in update_fields, (
            f"{field} must NOT be on FactoryUpdate (WO §4 factory dependency = 0)"
        )


# ==========================================================================
# A9 — No-parent-alias guards: has_diving / has_surface_supplied_diving do
#      NOT derive the 3 coverage fields.
# ==========================================================================
def test_A9_no_alias_from_has_diving_to_coverage_three():
    body = SafeConstructionConsumerInput(has_diving=True)
    dumped = body.model_dump(exclude_none=True)
    for field in COVERAGE3:
        assert field not in dumped


def test_A9b_no_alias_from_surface_supplied_to_coverage_three():
    body = SafeConstructionConsumerInput(has_surface_supplied_diving=True)
    dumped = body.model_dump(exclude_none=True)
    for field in COVERAGE3:
        assert field not in dumped


# ==========================================================================
# A10 — Consumer-override merge honors 3 new fields (SAFE_CST_OVERRIDE_FIELDS
#       includes them, model_dump exposes them for the run_safe_construction_leg
#       merge loop). Absent inputs still absent.
# ==========================================================================
def test_A10_merge_flow_carries_three_when_set():
    body = SafeConstructionConsumerInput(
        has_surface_supplied_diving=True,
        diving_depth_m=18.0,
        diving_surface_ascent_restricted=True,
    )
    dumped = body.model_dump(exclude_none=True)
    assert dumped["diving_depth_m"] == 18.0
    assert dumped["diving_surface_ascent_restricted"] is True
    # decompression_stop_required left absent — not in dumped.
    assert "diving_decompression_stop_required" not in dumped
    # Merge tuple carries all three regardless of whether values are set.
    for field in COVERAGE3:
        assert field in SAFE_CST_OVERRIDE_FIELDS


# ==========================================================================
# A11 — SEM-003 previous 6 override fields untouched (regression guard).
# ==========================================================================
def test_A11_prior_six_intact():
    for field in SEM003_PRIOR_SIX:
        assert field in SEM003_DIVING_OVERRIDE_FIELDS
        assert field in SAFE_CST_OVERRIDE_FIELDS
