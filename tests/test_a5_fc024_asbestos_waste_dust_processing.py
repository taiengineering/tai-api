"""A5 FC-024 ASBESTOS_WASTE_DUST_GENERATING_WORK tests.

산업안전보건기준에 관한 규칙 제497조:
석면을 1% 이상 함유한 폐기물을 처리하는 작업으로서
석면분진이 발생할 우려가 있는 작업.

exact work_type: ASBESTOS_WASTE_DUST_PROCESSING
canonical fact:  has_asbestos_waste_dust_processing_work

Generic alias firewall:
  has_asbestos / has_asbestos_demo / ASBESTOS_DEMOLITION / ASBESTOS_WASTE
  → must NOT activate has_asbestos_waste_dust_processing_work.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from clients.leg_runtime_client import _LEG_INPUT_FIELDS
from services.work_source.registry import WORK_TYPES
from services.work_source.projector import project_work_row

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row(work_type, attrs=None, active=True):
    return {
        "work_type": work_type,
        "work_subtype": None,
        "active": active,
        "attributes": attrs or {},
    }


# ---------------------------------------------------------------------------
# T1 — exact work_type → canonical true
# ---------------------------------------------------------------------------

def test_T1_asbestos_waste_dust_processing_emits_exact_fact():
    result = project_work_row(_row("ASBESTOS_WASTE_DUST_PROCESSING"))
    assert result.get("has_asbestos_waste_dust_processing_work") is True


# ---------------------------------------------------------------------------
# T2 — ASBESTOS_DEMOLITION must not emit FC-024 fact
# ---------------------------------------------------------------------------

def test_T2_asbestos_demolition_does_not_emit_fc024():
    result = project_work_row(_row("ASBESTOS_DEMOLITION"))
    assert "has_asbestos_waste_dust_processing_work" not in result


# ---------------------------------------------------------------------------
# T3 — ASBESTOS_WASTE must not emit FC-024 fact
# ---------------------------------------------------------------------------

def test_T3_asbestos_waste_does_not_emit_fc024():
    result = project_work_row(_row("ASBESTOS_WASTE"))
    assert "has_asbestos_waste_dust_processing_work" not in result


# ---------------------------------------------------------------------------
# T4 — generic asbestos attribute on unrelated work_type must not emit FC-024
# ---------------------------------------------------------------------------

def test_T4_generic_asbestos_attribute_does_not_emit_fc024():
    result = project_work_row(_row("FORKLIFT", attrs={"has_asbestos": True}))
    assert "has_asbestos_waste_dust_processing_work" not in result


# ---------------------------------------------------------------------------
# T5 — unrelated work_type does not emit FC-024 fact
# ---------------------------------------------------------------------------

def test_T5_unrelated_work_type_absent():
    result = project_work_row(_row("ELECTRICAL"))
    assert "has_asbestos_waste_dust_processing_work" not in result


# ---------------------------------------------------------------------------
# T6 — registry: exact work_type present, attributes == {}
# ---------------------------------------------------------------------------

def test_T6_registry_has_exact_work_type():
    assert "ASBESTOS_WASTE_DUST_PROCESSING" in WORK_TYPES


def test_T6_registry_attributes_empty():
    assert WORK_TYPES["ASBESTOS_WASTE_DUST_PROCESSING"]["attributes"] == {}


# ---------------------------------------------------------------------------
# T7 — transport: exact canonical field present exactly once
# ---------------------------------------------------------------------------

def test_T7_transport_field_present():
    assert "has_asbestos_waste_dust_processing_work" in _LEG_INPUT_FIELDS


def test_T7_transport_field_no_duplicate():
    fields = list(_LEG_INPUT_FIELDS)
    count = fields.count("has_asbestos_waste_dust_processing_work")
    assert count == 1


# ---------------------------------------------------------------------------
# T8/T9 — transport count 242 → 243
# ---------------------------------------------------------------------------

def test_T8_leg_input_field_count_is_243():
    # A5 FC-024: 242 → 243. WO-A5-FC001-TRACK1: 243 → 249 (+6 FC-001 per-row synthesis).
    assert len(_LEG_INPUT_FIELDS) == 249


def test_T9_leg_input_field_unique_count_is_243():
    assert len(set(_LEG_INPUT_FIELDS)) == 249


# ---------------------------------------------------------------------------
# LEG dispatcher — identity guard
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../leg/development/engine/rtm_engine"))

from rtm.applicable import (
    ConditionExtractor, Leaf, Composite,
    iter_leaf_fields, _WAVE1_CLAUSE,
)
from rtm.repository import RepositoryRule

FC024_ATOM_ID  = "6b214890-f9a0-5aed-83f8-ff5b4da478e0"
FC024_CLAUSE   = "cd643912-2f7d-4b95-9059-e94de6252089"
_WRONG_CLAUSE  = "00000000-0000-0000-0000-000000000000"
_WRONG_ATOM    = "00000000-0000-0000-0000-000000000001"


def _rule(atom_id, clause):
    return RepositoryRule(
        atom_id=atom_id, mapped_field="",
        semantic_clause_id=clause,
        law_name="", law_article="", evidence="",
    )


def _tree(atom_id, clause):
    return ConditionExtractor.extract(_rule(atom_id, clause))


# L1 — exact atom + exact clause → Composite(AND) with exact fact
def test_L1_exact_pair_activates():
    t = _tree(FC024_ATOM_ID, FC024_CLAUSE)
    assert isinstance(t, Composite) and t.kind == "AND"
    assert "has_asbestos_waste_dust_processing_work" in iter_leaf_fields(t)


# L2 — exact atom + wrong clause → fail-closed Leaf(threshold=None)
def test_L2_wrong_clause_fail_closed():
    t = _tree(FC024_ATOM_ID, _WRONG_CLAUSE)
    assert isinstance(t, Leaf) and t.threshold is None
    assert iter_leaf_fields(t) == set()


# L3 — wrong atom + exact clause → fail-closed (no FC-024 rule)
def test_L3_wrong_atom_fail_closed():
    t = _tree(_WRONG_ATOM, FC024_CLAUSE)
    assert isinstance(t, Leaf) and t.threshold is None
    assert "has_asbestos_waste_dust_processing_work" not in iter_leaf_fields(t)


# L4 — exact pair present in _WAVE1_CLAUSE identity map
def test_L4_exact_pair_in_wave1_clause():
    assert FC024_ATOM_ID in _WAVE1_CLAUSE
    assert _WAVE1_CLAUSE[FC024_ATOM_ID] == FC024_CLAUSE


# L5 — generic has_asbestos_demo field alone does not activate FC-024 exact fact
def test_L5_generic_has_asbestos_demo_not_in_fc024_tree():
    t = _tree(FC024_ATOM_ID, FC024_CLAUSE)
    fields = iter_leaf_fields(t)
    assert "has_asbestos_demo" not in fields
    assert "has_asbestos_waste_dust_processing_work" in fields
