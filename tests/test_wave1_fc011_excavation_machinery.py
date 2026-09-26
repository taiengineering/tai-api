"""PR-W1-E: FC-011 EXCAVATION_MACHINERY_USE tests.

WO-E2E-OBJ04-L3-COVERAGE-ACTIVATION-WAVE1-DESIGN-001 PR-W1-E

Verifies:
- EXCAVATION + uses_machinery=True → excavation_machinery_in_use emitted.
- False / None / missing → not emitted (fail-closed).
- Inactive row → nothing emitted.
- has_excavation alone does NOT alias to exact fact.
- Transport allowlist: excavation_machinery_in_use registered, count 241→242.
- LEG dispatcher: exact pair (atom_id + semantic_clause_id) → Composite(AND).
- Wrong clause → fail-closed Leaf(threshold=None).
- No regression on has_excavation / W1-B/C/D dispatcher.
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

def _row(attrs=None, active=True):
    return {"work_type": "EXCAVATION", "work_subtype": None, "active": active, "attributes": attrs or {}}


# ---------------------------------------------------------------------------
# Registry contract
# ---------------------------------------------------------------------------

def test_registry_has_excavation_work_type():
    assert "EXCAVATION" in WORK_TYPES


def test_registry_excavation_has_uses_machinery_attribute():
    assert "uses_machinery" in WORK_TYPES["EXCAVATION"]["attributes"]


def test_registry_uses_machinery_is_boolean():
    assert WORK_TYPES["EXCAVATION"]["attributes"]["uses_machinery"]["type"] == "boolean"


# ---------------------------------------------------------------------------
# Projector — SOURCE invariants
# ---------------------------------------------------------------------------

def test_excavation_uses_machinery_true_positive():
    result = project_work_row(_row(attrs={"uses_machinery": True}))
    assert result.get("excavation_machinery_in_use") is True


def test_excavation_uses_machinery_false_absent():
    result = project_work_row(_row(attrs={"uses_machinery": False}))
    assert "excavation_machinery_in_use" not in result


def test_excavation_uses_machinery_none_absent():
    result = project_work_row(_row(attrs={"uses_machinery": None}))
    assert "excavation_machinery_in_use" not in result


def test_excavation_uses_machinery_missing_absent():
    result = project_work_row(_row(attrs={}))
    assert "excavation_machinery_in_use" not in result


def test_inactive_excavation_row_emits_nothing():
    result = project_work_row(_row(attrs={"uses_machinery": True}, active=False))
    assert result == {}


def test_generic_has_excavation_does_not_produce_exact_fact():
    """has_excavation=True on a non-EXCAVATION work type must not emit excavation_machinery_in_use."""
    row = {"work_type": "SCAFFOLD", "work_subtype": "ASSEMBLY", "active": True,
           "attributes": {"has_excavation": True, "scaffold_kind": "SYSTEM_SCAFFOLD"}}
    result = project_work_row(row)
    assert "excavation_machinery_in_use" not in result


def test_excavation_only_emits_exact_fact_not_has_excavation():
    result = project_work_row(_row(attrs={"uses_machinery": True}))
    assert "has_excavation" not in result


# ---------------------------------------------------------------------------
# Transport allowlist
# ---------------------------------------------------------------------------

def test_excavation_machinery_in_use_in_leg_input_fields():
    assert "excavation_machinery_in_use" in _LEG_INPUT_FIELDS


def test_field_count_is_243():
    # PR-W1-E FC-011: 241 → 242. A5 FC-024: 242 → 243. WO-A5-FC001-TRACK1: 243 → 249.
    assert len(_LEG_INPUT_FIELDS) == 249


def test_no_duplicate_in_leg_input_fields():
    fields = list(_LEG_INPUT_FIELDS)
    assert len(fields) == len(set(fields))


# ---------------------------------------------------------------------------
# LEG dispatcher — identity guard (exact pair)
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../leg/development/engine/rtm_engine"))

from rtm.applicable import (
    ConditionExtractor, Leaf, Composite,
    iter_leaf_fields, _WAVE1_CLAUSE,
)
from rtm.repository import RepositoryRule

_WRONG = "00000000-0000-0000-0000-000000000000"

FOG021_ATOM_ID = "303b02e1-e853-5912-b38a-b00ad9c117af"
FOG021_CLAUSE  = "5aae903d-d19f-40b4-b72b-e3a5af02ac2d"

FOG023_ATOM_ID = "32d4a3f4-accf-541c-9ccc-a3b683cc40e6"
FOG023_CLAUSE  = "7a3587bd-94be-4b15-90cb-1c7167cff5fd"


def _rule(atom_id, clause):
    return RepositoryRule(
        atom_id=atom_id, mapped_field="",
        semantic_clause_id=clause,
        law_name="", law_article="", evidence="",
    )


def _tree(atom_id, clause):
    return ConditionExtractor.extract(_rule(atom_id, clause))


def test_fog021_in_wave1_clause():
    assert FOG021_ATOM_ID in _WAVE1_CLAUSE
    assert _WAVE1_CLAUSE[FOG021_ATOM_ID] == FOG021_CLAUSE


def test_fog023_in_wave1_clause():
    assert FOG023_ATOM_ID in _WAVE1_CLAUSE
    assert _WAVE1_CLAUSE[FOG023_ATOM_ID] == FOG023_CLAUSE


def test_fog021_exact_pair_activates():
    t = _tree(FOG021_ATOM_ID, FOG021_CLAUSE)
    assert isinstance(t, Composite) and t.kind == "AND"
    assert "excavation_machinery_in_use" in iter_leaf_fields(t)


def test_fog023_exact_pair_activates():
    t = _tree(FOG023_ATOM_ID, FOG023_CLAUSE)
    assert isinstance(t, Composite) and t.kind == "AND"
    assert "excavation_machinery_in_use" in iter_leaf_fields(t)


def test_fog021_wrong_clause_fail_closed():
    t = _tree(FOG021_ATOM_ID, _WRONG)
    assert isinstance(t, Leaf) and t.threshold is None
    assert iter_leaf_fields(t) == set()


def test_fog023_wrong_clause_fail_closed():
    t = _tree(FOG023_ATOM_ID, _WRONG)
    assert isinstance(t, Leaf) and t.threshold is None
    assert iter_leaf_fields(t) == set()


# ---------------------------------------------------------------------------
# Regression — W1-B/C/D dispatcher not affected
# ---------------------------------------------------------------------------

W1D_FOG240A = "49f58f2b-61ba-5883-8564-de3c6851ce85"
W1D_CLAUSE  = "79c16ecd-8ae6-44a3-8c7e-84dcdd812a1e"


def test_w1d_dispatcher_regression():
    t = _tree(W1D_FOG240A, W1D_CLAUSE)
    assert isinstance(t, Composite) and t.kind == "AND"
    assert "performs_air_purification_equipment_maintenance_or_cleaning" in iter_leaf_fields(t)
