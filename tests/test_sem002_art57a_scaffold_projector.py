"""WO-E2E-OBJ01-SEM002-ART57A-CONSUMER-INPUT-WIRING-001.

P1-P8 + transport-integration tests for the SCAFFOLD family in the
Common Work Source projector, wiring the LEG-canonical existential
fact:

  performs_scaffold_assembly_dismantle_or_modification_on_dalbi_or_ge5m_scaffold

Legal source (LEG Art.57 first sentence):
  APPLICABLE iff EXISTS scaffold S such that
    (S.type = DALBI OR S.height_m >= 5) AND
    activity_on(S) IN {ASSEMBLY, DISMANTLE, MODIFICATION}

Same-entity binding is preserved by evaluating each row (= one specific
scaffold + one activity) independently; project_work_rows unions across
rows without cross-combining attributes.
"""
from __future__ import annotations

from types import SimpleNamespace

from clients.leg_runtime_client import _LEG_INPUT_FIELDS, build_facility
from services.canonical.leg_input_contract import build_unified_leg_input
from services.work_source.merge import merge_or_raise
from services.work_source.projector import project_work_row, project_work_rows
from services.work_source.registry import ALLOWED_WORK_TYPES, WORK_TYPES


CANON_FIELD = (
    "performs_scaffold_assembly_dismantle_or_modification_on_dalbi_or_ge5m_scaffold"
)


# =========================================================================
# Registry sanity
# =========================================================================
def test_registry_declares_scaffold_family():
    assert "SCAFFOLD" in ALLOWED_WORK_TYPES
    spec = WORK_TYPES["SCAFFOLD"]
    # WO-E2E-OBJ03-L3-55-SEMANTIC-INPUT-INTEGRATION-001 PATCH-1: USE_WITH_WORKERS added
    assert {"ASSEMBLY", "DISMANTLE", "MODIFICATION"} <= set(spec["subtypes"].keys())
    assert "USE_WITH_WORKERS" in spec["subtypes"]
    attrs = spec["attributes"]
    assert attrs["is_dalbi"]["type"] == "boolean"
    assert attrs["height_m"]["type"] == "number"


def test_leg_input_fields_contains_canonical_fact_exactly_once():
    assert CANON_FIELD in _LEG_INPUT_FIELDS
    assert _LEG_INPUT_FIELDS.count(CANON_FIELD) == 1


def _row(**kwargs):
    base = {
        "work_type": "SCAFFOLD",
        "work_subtype": None,
        "attributes": {},
        "active": True,
    }
    base.update(kwargs)
    return base


# =========================================================================
# P1 — dalbi + assembly (height=3, dalbi arm carries it)
# =========================================================================
def test_P1_dalbi_assembly_true():
    row = _row(
        work_subtype="ASSEMBLY",
        attributes={"is_dalbi": True, "height_m": 3},
    )
    assert project_work_row(row) == {CANON_FIELD: True}


# =========================================================================
# P2 — dalbi + dismantle, height missing (dalbi alone carries it)
# =========================================================================
def test_P2_dalbi_dismantle_height_missing_true():
    row = _row(
        work_subtype="DISMANTLE",
        attributes={"is_dalbi": True},
    )
    assert project_work_row(row) == {CANON_FIELD: True}


# =========================================================================
# P3 — non-dalbi 5m + modification (height arm carries it)
# =========================================================================
def test_P3_generic_5m_modification_true():
    row = _row(
        work_subtype="MODIFICATION",
        attributes={"is_dalbi": False, "height_m": 5},
    )
    assert project_work_row(row) == {CANON_FIELD: True}


# =========================================================================
# P4 — non-dalbi 4.999m + assembly → ABSENT (below threshold)
# =========================================================================
def test_P4_below_threshold_absent():
    row = _row(
        work_subtype="ASSEMBLY",
        attributes={"is_dalbi": False, "height_m": 4.999},
    )
    assert project_work_row(row) == {}


# =========================================================================
# P5 — 6m scaffold with NO subtype → ABSENT (activity gate must be present)
# =========================================================================
def test_P5_height_alone_without_subtype_absent():
    for subtype in (None, ""):
        row = _row(
            work_subtype=subtype,
            attributes={"is_dalbi": False, "height_m": 6},
        )
        assert project_work_row(row) == {}, f"subtype={subtype!r} must not fire"


# =========================================================================
# P6 — same-entity trap: dalbi row without activity + non-dalbi 3m + assembly
#      → ABSENT (no single row satisfies)
# =========================================================================
def test_P6_same_entity_trap_no_cross_row_combination():
    row_a = _row(
        work_subtype=None,  # no activity
        attributes={"is_dalbi": True},
        equipment_ref="scaffold-A",
    )
    row_b = _row(
        work_subtype="ASSEMBLY",
        attributes={"is_dalbi": False, "height_m": 3},
        equipment_ref="scaffold-B",
    )
    # Each row alone
    assert project_work_row(row_a) == {}
    assert project_work_row(row_b) == {}
    # Union of both rows still absent (same-entity binding preserved)
    assert project_work_rows([row_a, row_b]) == {}


# =========================================================================
# P7 — existential multi-row positive (one row satisfies)
# =========================================================================
def test_P7_existential_multi_row_positive():
    row_bad = _row(
        work_subtype=None,  # no activity
        attributes={"is_dalbi": False, "height_m": 6},
    )
    row_good = _row(
        work_subtype="DISMANTLE",
        attributes={"is_dalbi": False, "height_m": 6},
    )
    assert project_work_rows([row_bad, row_good]) == {CANON_FIELD: True}


# =========================================================================
# P8 — inactive row emits nothing regardless of fully-satisfying condition
# =========================================================================
def test_P8_inactive_row_emits_nothing():
    row = _row(
        work_subtype="ASSEMBLY",
        attributes={"is_dalbi": True, "height_m": 10},
        active=False,
    )
    assert project_work_row(row) == {}


# =========================================================================
# height_m fail-closed guards
# =========================================================================
def test_height_m_bool_excluded():
    # bool is a subclass of int; projector must reject it as height
    row = _row(
        work_subtype="ASSEMBLY",
        attributes={"is_dalbi": False, "height_m": True},
    )
    assert project_work_row(row) == {}


def test_height_m_negative_and_missing_rejected():
    for val in (None, "", "6", -1, -5, "5"):
        row = _row(
            work_subtype="ASSEMBLY",
            attributes={"is_dalbi": False, "height_m": val},
        )
        assert project_work_row(row) == {}, f"height_m={val!r} must not fire"


def test_dalbi_arm_survives_missing_height():
    # dalbi alone carries applicability regardless of height presence/type
    for val in (None, "", "6", -1, True):
        row = _row(
            work_subtype="ASSEMBLY",
            attributes={"is_dalbi": True, "height_m": val},
        )
        assert project_work_row(row) == {CANON_FIELD: True}, (
            f"dalbi arm must fire even with height_m={val!r}"
        )


# =========================================================================
# subtype-only membership: only 3 allowed subtypes
# =========================================================================
def test_only_three_subtypes_qualify():
    for subtype in ("USE", "INSPECTION", "MAINTENANCE", "UNKNOWN"):
        row = _row(
            work_subtype=subtype,
            attributes={"is_dalbi": True, "height_m": 10},
        )
        assert project_work_row(row) == {}, f"subtype={subtype!r} must not qualify"


# =========================================================================
# Transport integration: projected fact reaches build_facility() output
# =========================================================================
def _step1_body(**kwargs):
    facts = {}
    facts.update(kwargs)
    return SimpleNamespace(input=facts)


def test_transport_projected_fact_reaches_build_facility():
    rows = [
        _row(
            work_subtype="ASSEMBLY",
            attributes={"is_dalbi": True, "height_m": 3},
        ),
    ]
    assert project_work_rows(rows) == {CANON_FIELD: True}

    # Merge projection into source facts, then run the existing generic
    # build_unified_leg_input → build_facility loop. No alias, no special-case.
    merged = merge_or_raise(explicit={}, work_rows=rows)
    assert merged.get(CANON_FIELD) is True
    step1_body = build_unified_leg_input(
        sector="INDUSTRIAL", source_facts=merged, factory_id=None,
    )
    facility = build_facility(step1_body)
    assert facility.get(CANON_FIELD) is True


def test_transport_absent_when_no_scaffold_row_qualifies():
    rows = [
        _row(work_subtype=None, attributes={"is_dalbi": True}),
        _row(work_subtype="ASSEMBLY", attributes={"is_dalbi": False, "height_m": 3}),
    ]
    assert project_work_rows(rows) == {}
    merged = merge_or_raise(explicit={}, work_rows=rows)
    assert CANON_FIELD not in merged
    step1_body = build_unified_leg_input(
        sector="INDUSTRIAL", source_facts=merged, factory_id=None,
    )
    facility = build_facility(step1_body)
    assert CANON_FIELD not in facility


# =========================================================================
# Regression: existing families unchanged (no accidental cross-family leak)
# =========================================================================
def test_existing_families_unaffected_by_scaffold_addition():
    # Forklift baseline still projects uses_forklift
    row = _row(work_type="FORKLIFT", work_subtype=None, attributes={})
    assert project_work_row(row) == {"uses_forklift": True}

    # HIGH_PLACE roof still projects performs_work_on_roof
    row = _row(work_type="HIGH_PLACE", work_subtype="ROOF", attributes={})
    assert project_work_row(row) == {"performs_work_on_roof": True}

    # PAINTING requires all three, absent otherwise
    row = _row(
        work_type="PAINTING",
        work_subtype=None,
        attributes={"spray": True, "flammable_liquid": True, "enclosed_space": True},
    )
    assert project_work_row(row) == {
        "performs_spray_work_with_flammable_liquid_in_enclosed_space": True
    }
