"""WO-E2E-OBJ01-SEM002-ART57B-FASTLANE-IMPLEMENT-001.

P1-P10 + registry/transport tests for the SCAFFOLD.scaffold_kind extension
and its Art.57-B canonical fact:

  performs_steel_pipe_or_log_scaffold_assembly

Legal source (LEG Art.57 제2항):
  APPLICABLE iff EXISTS scaffold S such that
    S.kind IN {STEEL_PIPE, LOG} AND activity_on(S) == ASSEMBLY

Same-entity binding is preserved by evaluating each row (= one specific
scaffold + one activity) independently; project_work_rows unions across
rows without cross-combining attributes.

Registry: scaffold_kind is an enum with options STEEL_PIPE / LOG / OTHER.
missing != OTHER — omitting the key is a legally-meaningful "unknown".
Art.57-A canonical fact is emitted independently on the same SCAFFOLD row
when its own condition is satisfied; a row can validly emit both facts.
"""
from __future__ import annotations

from clients.leg_runtime_client import _LEG_INPUT_FIELDS, build_facility
from services.canonical.leg_input_contract import build_unified_leg_input
from services.work_source.merge import merge_or_raise
from services.work_source.projector import project_work_row, project_work_rows
from services.work_source.registry import WORK_TYPES, registry_public


ART57B_FIELD = "performs_steel_pipe_or_log_scaffold_assembly"
ART57A_FIELD = (
    "performs_scaffold_assembly_dismantle_or_modification_on_dalbi_or_ge5m_scaffold"
)


# =========================================================================
# Registry: scaffold_kind is a declared enum with 3 options
# =========================================================================
def test_registry_declares_scaffold_kind_enum():
    attrs = WORK_TYPES["SCAFFOLD"]["attributes"]
    assert "scaffold_kind" in attrs
    assert attrs["scaffold_kind"]["type"] == "enum"
    codes = [o["code"] for o in attrs["scaffold_kind"]["options"]]
    assert codes == ["STEEL_PIPE", "LOG", "OTHER"]


def test_registry_public_carries_scaffold_kind_options():
    payload = registry_public()
    scaffold = next(w for w in payload["work_types"] if w["code"] == "SCAFFOLD")
    kind_attr = next(a for a in scaffold["attributes"] if a["code"] == "scaffold_kind")
    assert kind_attr["type"] == "enum"
    assert kind_attr["label"] == "비계 종류"
    codes = [o["code"] for o in kind_attr["options"]]
    labels = [o["label"] for o in kind_attr["options"]]
    assert codes == ["STEEL_PIPE", "LOG", "OTHER"]
    assert labels == ["강관비계", "통나무비계", "기타 비계"]


def test_registry_public_boolean_attributes_still_have_no_options_key():
    payload = registry_public()
    scaffold = next(w for w in payload["work_types"] if w["code"] == "SCAFFOLD")
    is_dalbi = next(a for a in scaffold["attributes"] if a["code"] == "is_dalbi")
    height_m = next(a for a in scaffold["attributes"] if a["code"] == "height_m")
    assert "options" not in is_dalbi
    assert "options" not in height_m


# =========================================================================
# Transport allowlist: canonical fact registered exactly once
# =========================================================================
def test_leg_input_fields_contains_art57b_field_exactly_once():
    assert ART57B_FIELD in _LEG_INPUT_FIELDS
    assert _LEG_INPUT_FIELDS.count(ART57B_FIELD) == 1


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
# P1 — STEEL_PIPE + ASSEMBLY → fires
# =========================================================================
def test_P1_steel_pipe_assembly_true():
    row = _row(
        work_subtype="ASSEMBLY",
        attributes={"scaffold_kind": "STEEL_PIPE"},
    )
    assert project_work_row(row) == {ART57B_FIELD: True}


# =========================================================================
# P2 — LOG + ASSEMBLY → fires
# =========================================================================
def test_P2_log_assembly_true():
    row = _row(
        work_subtype="ASSEMBLY",
        attributes={"scaffold_kind": "LOG"},
    )
    assert project_work_row(row) == {ART57B_FIELD: True}


# =========================================================================
# P3 — OTHER + ASSEMBLY → ABSENT (kind gate)
# =========================================================================
def test_P3_other_assembly_absent():
    row = _row(
        work_subtype="ASSEMBLY",
        attributes={"scaffold_kind": "OTHER"},
    )
    assert project_work_row(row) == {}


# =========================================================================
# P4 — STEEL_PIPE + DISMANTLE → ABSENT (activity gate stricter than Art.57-A)
# =========================================================================
def test_P4_steel_pipe_dismantle_absent_for_art57b():
    row = _row(
        work_subtype="DISMANTLE",
        attributes={"scaffold_kind": "STEEL_PIPE"},
    )
    assert project_work_row(row) == {}


# =========================================================================
# P5 — ASSEMBLY with scaffold_kind missing → ABSENT
# =========================================================================
def test_P5_kind_missing_absent():
    row = _row(work_subtype="ASSEMBLY", attributes={})
    assert project_work_row(row) == {}


# =========================================================================
# P6 — same-entity trap: STEEL_PIPE row DISMANTLING + OTHER row ASSEMBLING
# =========================================================================
def test_P6_same_entity_trap_no_cross_row_combination():
    row_a = _row(
        work_subtype="DISMANTLE",
        attributes={"scaffold_kind": "STEEL_PIPE"},
        equipment_ref="scaffold-A",
    )
    row_b = _row(
        work_subtype="ASSEMBLY",
        attributes={"scaffold_kind": "OTHER"},
        equipment_ref="scaffold-B",
    )
    assert project_work_row(row_a) == {}
    assert project_work_row(row_b) == {}
    assert project_work_rows([row_a, row_b]) == {}


# =========================================================================
# P7 — dual applicability: STEEL_PIPE + ASSEMBLY + height=6
#      → both Art.57-A and Art.57-B fire on the same row (not an error)
# =========================================================================
def test_P7_dual_positive_art57a_and_art57b():
    row = _row(
        work_subtype="ASSEMBLY",
        attributes={
            "scaffold_kind": "STEEL_PIPE",
            "is_dalbi": False,
            "height_m": 6,
        },
    )
    assert project_work_row(row) == {
        ART57A_FIELD: True,
        ART57B_FIELD: True,
    }


# =========================================================================
# P8 — inactive row emits nothing regardless of full satisfying condition
# =========================================================================
def test_P8_inactive_row_emits_nothing():
    row = _row(
        work_subtype="ASSEMBLY",
        attributes={"scaffold_kind": "STEEL_PIPE"},
        active=False,
    )
    assert project_work_row(row) == {}


# =========================================================================
# P9 — transport: Art.57-B canonical fact reaches build_facility() output
# =========================================================================
def test_P9_transport_projected_fact_reaches_build_facility():
    rows = [
        _row(
            work_subtype="ASSEMBLY",
            attributes={"scaffold_kind": "LOG"},
        ),
    ]
    assert project_work_rows(rows) == {ART57B_FIELD: True}

    merged = merge_or_raise(explicit={}, work_rows=rows)
    assert merged.get(ART57B_FIELD) is True
    step1_body = build_unified_leg_input(
        sector="INDUSTRIAL", source_facts=merged, factory_id=None,
    )
    facility = build_facility(step1_body)
    assert facility.get(ART57B_FIELD) is True


def test_P9b_transport_absent_when_no_scaffold_row_qualifies():
    rows = [
        _row(work_subtype="DISMANTLE", attributes={"scaffold_kind": "STEEL_PIPE"}),
        _row(work_subtype="ASSEMBLY", attributes={"scaffold_kind": "OTHER"}),
    ]
    assert project_work_rows(rows) == {}
    merged = merge_or_raise(explicit={}, work_rows=rows)
    assert ART57B_FIELD not in merged
    step1_body = build_unified_leg_input(
        sector="INDUSTRIAL", source_facts=merged, factory_id=None,
    )
    facility = build_facility(step1_body)
    assert ART57B_FIELD not in facility


# =========================================================================
# P10 — existing Art.57-A projector semantics unchanged
# =========================================================================
def test_P10_art57a_semantics_unchanged():
    # dalbi + assembly (height=3) → Art.57-A only, Art.57-B absent
    row = _row(
        work_subtype="ASSEMBLY",
        attributes={"is_dalbi": True, "height_m": 3},
    )
    assert project_work_row(row) == {ART57A_FIELD: True}

    # non-dalbi 5m modification → Art.57-A only
    row = _row(
        work_subtype="MODIFICATION",
        attributes={"is_dalbi": False, "height_m": 5},
    )
    assert project_work_row(row) == {ART57A_FIELD: True}

    # 4.999m + assembly → both absent
    row = _row(
        work_subtype="ASSEMBLY",
        attributes={"is_dalbi": False, "height_m": 4.999},
    )
    assert project_work_row(row) == {}


# =========================================================================
# Guard: invalid scaffold_kind value never fires Art.57-B (fail-closed by
# not matching STEEL_PIPE / LOG; OTHER also falls out of the ASSEMBLY gate)
# =========================================================================
def test_invalid_scaffold_kind_does_not_fire():
    for bad in ("STEEL", "LOGS", "steel_pipe", "log", "", None, 0, False):
        row = _row(
            work_subtype="ASSEMBLY",
            attributes={"scaffold_kind": bad},
        )
        result = project_work_row(row)
        assert ART57B_FIELD not in result, (
            f"scaffold_kind={bad!r} must not fire Art.57-B; got {result}"
        )


# =========================================================================
# Existing families unaffected
# =========================================================================
def test_other_families_unaffected_by_art57b_addition():
    row = _row(work_type="FORKLIFT", work_subtype=None, attributes={})
    assert project_work_row(row) == {"uses_forklift": True}
    row = _row(work_type="HIGH_PLACE", work_subtype="ROOF", attributes={})
    assert project_work_row(row) == {"performs_work_on_roof": True}
