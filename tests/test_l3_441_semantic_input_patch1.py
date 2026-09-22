"""WO-E2E-OBJ03-L3-55-SEMANTIC-INPUT-INTEGRATION-001 PATCH-1.

Deterministic semantic tests for:
  - FC-016 WRONG_MAPPING correction: NEAR_ENERGIZED → performs_electrical_work_near_energized_circuit
  - FC-015A DEEPEN scaffold subtype: STEEL_PIPE_SCAFFOLD → scaffold_kind_is_steel_pipe_scaffold
  - FC-015A DEEPEN scaffold subtype: SYSTEM_SCAFFOLD → scaffold_kind_is_system_scaffold
  - FC-015B USE_WITH_WORKERS subtype registration
  - Missing ≠ false invariant for new scaffold_kind_is_* fields
  - Legacy scaffold_kind codes (STEEL_PIPE/LOG) unaffected

All tests are projector-level deterministic (no DB required).
"""
from __future__ import annotations

from clients.leg_runtime_client import _LEG_INPUT_FIELDS
from services.work_source.projector import project_work_row, project_work_rows
from services.work_source.registry import WORK_TYPES


# =========================================================================
# Transport allowlist: new canonical fields registered
# =========================================================================
def test_new_scaffold_kind_fields_in_transport():
    assert "scaffold_kind_is_steel_pipe_scaffold" in _LEG_INPUT_FIELDS
    assert "scaffold_kind_is_system_scaffold" in _LEG_INPUT_FIELDS
    assert _LEG_INPUT_FIELDS.count("scaffold_kind_is_steel_pipe_scaffold") == 1
    assert _LEG_INPUT_FIELDS.count("scaffold_kind_is_system_scaffold") == 1


def test_near_energized_field_in_transport():
    assert "performs_electrical_work_near_energized_circuit" in _LEG_INPUT_FIELDS
    assert _LEG_INPUT_FIELDS.count("performs_electrical_work_near_energized_circuit") == 1


# =========================================================================
# FC-016 WRONG_MAPPING correction: NEAR_ENERGIZED subtype
# =========================================================================
def _elec_row(subtype):
    return {"work_type": "ELECTRICAL", "work_subtype": subtype, "attributes": {}, "active": True}


def test_near_energized_emits_correct_canonical_fact():
    row = _elec_row("NEAR_ENERGIZED")
    assert project_work_row(row) == {"performs_electrical_work_near_energized_circuit": True}


def test_near_deenergized_unchanged():
    row = _elec_row("NEAR_DEENERGIZED")
    assert project_work_row(row) == {"performs_electrical_work_near_deenergized_circuit": True}


def test_near_energized_not_same_as_near_deenergized():
    near_e = project_work_row(_elec_row("NEAR_ENERGIZED"))
    near_de = project_work_row(_elec_row("NEAR_DEENERGIZED"))
    assert near_e != near_de
    assert "performs_electrical_work_near_energized_circuit" in near_e
    assert "performs_electrical_work_near_energized_circuit" not in near_de


def test_near_energized_registered_in_electrical_subtypes():
    subtypes = WORK_TYPES["ELECTRICAL"]["subtypes"]
    assert "NEAR_ENERGIZED" in subtypes


# =========================================================================
# FC-015A DEEPEN: STEEL_PIPE_SCAFFOLD → scaffold_kind_is_steel_pipe_scaffold
# =========================================================================
def _scaffold_row(subtype=None, kind=None, is_dalbi=None, height_m=None):
    attrs = {}
    if kind is not None:
        attrs["scaffold_kind"] = kind
    if is_dalbi is not None:
        attrs["is_dalbi"] = is_dalbi
    if height_m is not None:
        attrs["height_m"] = height_m
    return {
        "work_type": "SCAFFOLD",
        "work_subtype": subtype,
        "attributes": attrs,
        "active": True,
    }


def test_steel_pipe_scaffold_emits_kind_fact_no_subtype():
    row = _scaffold_row(subtype=None, kind="STEEL_PIPE_SCAFFOLD")
    result = project_work_row(row)
    assert result == {"scaffold_kind_is_steel_pipe_scaffold": True}


def test_steel_pipe_scaffold_kind_fact_with_assembly():
    row = _scaffold_row(subtype="ASSEMBLY", kind="STEEL_PIPE_SCAFFOLD")
    result = project_work_row(row)
    assert "scaffold_kind_is_steel_pipe_scaffold" in result
    # Also fires Art.57-B since STEEL_PIPE_SCAFFOLD qualifies
    assert "performs_steel_pipe_or_log_scaffold_assembly" in result


def test_steel_pipe_scaffold_kind_fact_with_dismantle():
    row = _scaffold_row(subtype="DISMANTLE", kind="STEEL_PIPE_SCAFFOLD")
    result = project_work_row(row)
    assert "scaffold_kind_is_steel_pipe_scaffold" in result
    # Art.57-B does NOT fire for DISMANTLE (only ASSEMBLY)
    assert "performs_steel_pipe_or_log_scaffold_assembly" not in result


# =========================================================================
# FC-015A DEEPEN: SYSTEM_SCAFFOLD → scaffold_kind_is_system_scaffold
# =========================================================================
def test_system_scaffold_emits_kind_fact_no_subtype():
    row = _scaffold_row(subtype=None, kind="SYSTEM_SCAFFOLD")
    result = project_work_row(row)
    assert result == {"scaffold_kind_is_system_scaffold": True}


def test_system_scaffold_kind_fact_with_assembly():
    row = _scaffold_row(subtype="ASSEMBLY", kind="SYSTEM_SCAFFOLD")
    result = project_work_row(row)
    assert "scaffold_kind_is_system_scaffold" in result


# =========================================================================
# Missing ≠ false: absent scaffold_kind → kind facts absent, NOT false
# (PATCH-1 Equivalence Principle 7: Missing ≠ false)
# =========================================================================
def test_missing_scaffold_kind_emits_no_kind_facts():
    row = _scaffold_row(subtype="ASSEMBLY", kind=None)
    result = project_work_row(row)
    assert "scaffold_kind_is_steel_pipe_scaffold" not in result
    assert "scaffold_kind_is_system_scaffold" not in result


def test_other_scaffold_kind_emits_no_kind_facts():
    row = _scaffold_row(subtype=None, kind="OTHER")
    result = project_work_row(row)
    assert "scaffold_kind_is_steel_pipe_scaffold" not in result
    assert "scaffold_kind_is_system_scaffold" not in result
    assert result == {}


# =========================================================================
# Legacy STEEL_PIPE code: unaffected (no new kind fact emitted)
# PATCH-1 Negative Test 5: STEEL_PIPE DISMANTLE → kind facts absent
# =========================================================================
def test_legacy_steel_pipe_no_scaffold_kind_is_fact():
    row = _scaffold_row(subtype="DISMANTLE", kind="STEEL_PIPE")
    result = project_work_row(row)
    assert "scaffold_kind_is_steel_pipe_scaffold" not in result
    assert "scaffold_kind_is_system_scaffold" not in result


def test_legacy_steel_pipe_assembly_art57b_unchanged():
    row = _scaffold_row(subtype="ASSEMBLY", kind="STEEL_PIPE")
    result = project_work_row(row)
    assert result == {"performs_steel_pipe_or_log_scaffold_assembly": True}
    assert "scaffold_kind_is_steel_pipe_scaffold" not in result


# =========================================================================
# Same-entity binding: two rows do not cross-combine
# PATCH-1 Negative Test 5 variant: STEEL_PIPE_SCAFFOLD no-activity row
# + height=8m OTHER-kind row → scaffold_kind_is_steel_pipe_scaffold from row1 only
# =========================================================================
def test_same_entity_binding_two_rows_no_cross_combine():
    row1 = _scaffold_row(subtype=None, kind="STEEL_PIPE_SCAFFOLD")
    row2 = _scaffold_row(subtype="ASSEMBLY", kind="OTHER", height_m=8)
    result1 = project_work_row(row1)
    result2 = project_work_row(row2)
    # row1: kind fact emitted, no activity gate so no Art.57-A/B
    assert result1 == {"scaffold_kind_is_steel_pipe_scaffold": True}
    # row2: OTHER kind, no kind fact; height=8 but ASSEMBLY+OTHER → no Art.57-B
    assert "scaffold_kind_is_steel_pipe_scaffold" not in result2
    # Union: scaffold_kind_is_steel_pipe_scaffold from row1, Art.57-A from row2
    combined = project_work_rows([row1, row2])
    assert "scaffold_kind_is_steel_pipe_scaffold" in combined
    assert "performs_steel_pipe_or_log_scaffold_assembly" not in combined


# =========================================================================
# FC-015B USE_WITH_WORKERS: registered in subtypes, handled by projector
# =========================================================================
def test_use_with_workers_registered_in_subtypes():
    subtypes = WORK_TYPES["SCAFFOLD"]["subtypes"]
    assert "USE_WITH_WORKERS" in subtypes


def test_use_with_workers_does_not_cause_error():
    row = _scaffold_row(subtype="USE_WITH_WORKERS", kind="SYSTEM_SCAFFOLD")
    result = project_work_row(row)
    # SYSTEM_SCAFFOLD kind fact emitted; no Art.57-A (USE_WITH_WORKERS not in A gate)
    assert "scaffold_kind_is_system_scaffold" in result
    assert "performs_scaffold_assembly_dismantle_or_modification_on_dalbi_or_ge5m_scaffold" not in result


def test_use_with_workers_steel_pipe_scaffold_kind_fact():
    row = _scaffold_row(subtype="USE_WITH_WORKERS", kind="STEEL_PIPE_SCAFFOLD")
    result = project_work_row(row)
    assert "scaffold_kind_is_steel_pipe_scaffold" in result


# =========================================================================
# Inactive row: emits nothing regardless
# =========================================================================
def test_inactive_row_no_scaffold_kind_facts():
    row = _scaffold_row(subtype=None, kind="STEEL_PIPE_SCAFFOLD")
    row["active"] = False
    assert project_work_row(row) == {}
