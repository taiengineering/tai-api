"""WO-OBS009-CANONICAL-PSR-BATCH-001 / OPTION A canonical adapter tests.

C1–C8 per GPT decision §20:
  C1 no factory_materials rows      → all 3 facts ABSENT
  C2 free-text only (no key)        → all 3 facts ABSENT
  C3 MANAGED master                 → managed=True only
  C4 PERMIT master                  → permit=True only
  C5 SPECIAL master                 → special=True (co-classes allowed)
  C6 multiple materials             → union / presence aggregation
  C7 inactive material              → no emitted facts
  C8 read failure                   → fail-closed (propagate, do not convert)

Layer separation:
  Source contract   = classification triples
  Canonical contract = per-factory boolean presence facts
"""
from __future__ import annotations

import pytest

from services.material_source import (
    CANONICAL_FIELDS,
    CLASSIFICATION_TO_CANONICAL,
    MaterialCanonicalMergeConflict,
    MaterialSourceLoadError,
    merge_material_canonical_into_facts,
    project_material_canonical_facts,
    project_material_canonical_facts_from_rows,
)
from services.material_source.projector import project_factory_material_rows
from services.material_source.store import load_factory_material_rows_optional


MANAGED_CANON = "is_managed_hazardous_substance"
PERMIT_CANON = "is_permit_required_hazardous_substance"
SPECIAL_CANON = "is_special_management_substance"

MANAGED = "MANAGED_HAZARDOUS_SUBSTANCE"
PERMIT = "PERMIT_REQUIRED_HAZARDOUS_SUBSTANCE"
SPECIAL = "SPECIAL_MANAGEMENT_SUBSTANCE"

# Keys reused from test_obs009_common_material_source.py fixtures.
BENZENE_KEY = "ISHL-RULE-APP12-G1-I046"      # MANAGED + SPECIAL
VINYL_KEY = "ISHL-ENF-ART88-0088001-P-H7"    # PERMIT
STODDARD_KEY = "ISHL-RULE-APP12-G1-I060"     # MANAGED only


def _row(**kwargs):
    base = {
        "material_name": "x",
        "material_category_code": None,
        "handling_mode_codes": None,
        "material_master_key": None,
        "is_active": True,
    }
    base.update(kwargs)
    return base


# ── mapping invariants ────────────────────────────────────────────────────
def test_canonical_field_names_are_exactly_three():
    assert CANONICAL_FIELDS == {MANAGED_CANON, PERMIT_CANON, SPECIAL_CANON}


def test_classification_mapping_matches_registry():
    assert CLASSIFICATION_TO_CANONICAL == {
        MANAGED: MANAGED_CANON,
        PERMIT: PERMIT_CANON,
        SPECIAL: SPECIAL_CANON,
    }


# ── C1: no factory_materials rows → all 3 facts ABSENT ───────────────────
def test_C1_no_factory_material_rows_all_absent():
    facts = project_material_canonical_facts_from_rows([])
    assert facts == {}
    assert MANAGED_CANON not in facts
    assert PERMIT_CANON not in facts
    assert SPECIAL_CANON not in facts
    # explicitly reject false-injection
    assert facts.get(MANAGED_CANON) is not False
    assert facts.get(PERMIT_CANON) is not False
    assert facts.get(SPECIAL_CANON) is not False


# ── C2: free-text only (no master key) → all 3 facts ABSENT ──────────────
def test_C2_free_text_only_all_absent():
    facts = project_material_canonical_facts_from_rows(
        [_row(material_name="unknown-solvent", material_master_key=None)]
    )
    assert facts == {}


def test_C2_empty_master_key_all_absent():
    facts = project_material_canonical_facts_from_rows(
        [_row(material_name="unknown-solvent", material_master_key="")]
    )
    assert facts == {}


# ── C3: MANAGED master only ──────────────────────────────────────────────
def test_C3_managed_master_managed_only():
    facts = project_material_canonical_facts_from_rows(
        [_row(material_master_key=STODDARD_KEY)]
    )
    assert facts == {MANAGED_CANON: True}


# ── C4: PERMIT master only ───────────────────────────────────────────────
def test_C4_permit_master_permit_only():
    facts = project_material_canonical_facts_from_rows(
        [_row(material_master_key=VINYL_KEY)]
    )
    assert facts == {PERMIT_CANON: True}


# ── C5: SPECIAL master + co-classes (multi-class MANAGED+SPECIAL) ────────
def test_C5_special_with_managed_coexists():
    # BENZENE_KEY carries {MANAGED, SPECIAL} per legal catalog.
    facts = project_material_canonical_facts_from_rows(
        [_row(material_master_key=BENZENE_KEY)]
    )
    assert facts == {MANAGED_CANON: True, SPECIAL_CANON: True}
    assert PERMIT_CANON not in facts


# ── C6: multiple materials → union / presence aggregation ────────────────
def test_C6_multiple_materials_aggregate_presence():
    rows = [
        _row(material_name="stoddard", material_master_key=STODDARD_KEY),
        _row(material_name="vinyl",    material_master_key=VINYL_KEY),
        _row(material_name="benzene",  material_master_key=BENZENE_KEY),
    ]
    facts = project_material_canonical_facts_from_rows(rows)
    assert facts == {
        MANAGED_CANON: True,
        PERMIT_CANON: True,
        SPECIAL_CANON: True,
    }


def test_C6_duplicate_hits_do_not_double_count():
    rows = [
        _row(material_name="benzene-1", material_master_key=BENZENE_KEY),
        _row(material_name="benzene-2", material_master_key=BENZENE_KEY),
    ]
    facts = project_material_canonical_facts_from_rows(rows)
    assert facts == {MANAGED_CANON: True, SPECIAL_CANON: True}


# ── C7: inactive material → no emitted facts ─────────────────────────────
def test_C7_inactive_material_emits_nothing():
    facts = project_material_canonical_facts_from_rows(
        [_row(material_master_key=BENZENE_KEY, is_active=False)]
    )
    assert facts == {}


def test_C7_active_and_inactive_uses_active_only():
    rows = [
        _row(material_master_key=BENZENE_KEY, is_active=False),
        _row(material_master_key=VINYL_KEY,   is_active=True),
    ]
    facts = project_material_canonical_facts_from_rows(rows)
    assert facts == {PERMIT_CANON: True}


# ── C8: read failure → fail-closed (propagate, do not convert) ────────────
class _BoomQuery:
    def table(self, name):
        raise RuntimeError("relation factory_materials does not exist")


def test_C8_read_failure_propagates():
    """Upstream store failure must not be converted to empty/false facts."""
    with pytest.raises(MaterialSourceLoadError) as exc_info:
        load_factory_material_rows_optional(_BoomQuery(), "F1")
    assert exc_info.value.code == "MATERIAL_SOURCE_UNAVAILABLE"


def test_C8_adapter_never_emits_false_on_absence():
    facts = project_material_canonical_facts_from_rows([])
    for name in (MANAGED_CANON, PERMIT_CANON, SPECIAL_CANON):
        assert name not in facts
        # explicit false injection is forbidden
        assert facts.get(name) is not False


# ── unknown classification codes are ignored ─────────────────────────────
def test_unknown_classification_code_is_ignored():
    facts = project_material_canonical_facts(
        [
            {"material_key": "X", "classification_code": "NOT_A_REAL_CLASS", "source_ref": "z"},
            {"material_key": "X", "classification_code": MANAGED, "source_ref": "z"},
        ]
    )
    assert facts == {MANAGED_CANON: True}


def test_missing_classification_code_is_ignored():
    facts = project_material_canonical_facts(
        [
            {"material_key": "X", "source_ref": "z"},
            {"material_key": "X", "classification_code": None, "source_ref": "z"},
            {"material_key": "X", "classification_code": 42, "source_ref": "z"},
        ]
    )
    assert facts == {}


# ── merge policy mirrors work_source/merge.py ────────────────────────────
def test_merge_inserts_new_canonical_facts():
    explicit = {"has_confined_space": True}
    projected = {MANAGED_CANON: True}
    merged, conflicts = merge_material_canonical_into_facts(
        explicit, projected=projected
    )
    assert merged == {"has_confined_space": True, MANAGED_CANON: True}
    assert conflicts == []


def test_merge_keeps_same_value():
    explicit = {MANAGED_CANON: True}
    projected = {MANAGED_CANON: True}
    merged, conflicts = merge_material_canonical_into_facts(
        explicit, projected=projected
    )
    assert merged == {MANAGED_CANON: True}
    assert conflicts == []


def test_merge_records_conflict_and_keeps_explicit():
    explicit = {MANAGED_CANON: False}
    projected = {MANAGED_CANON: True}
    merged, conflicts = merge_material_canonical_into_facts(
        explicit, projected=projected
    )
    assert merged[MANAGED_CANON] is False
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict["field"] == MANAGED_CANON
    assert conflict["explicit"] is False
    assert conflict["projected"] is True
    assert "MATERIAL_CANONICAL_CONFLICT" in conflict["reason"]


def test_merge_never_injects_absent_projected_as_false():
    """A canonical fact absent from projected must NOT appear in merged."""
    explicit = {"has_confined_space": True}
    merged, conflicts = merge_material_canonical_into_facts(
        explicit, projected={}
    )
    assert MANAGED_CANON not in merged
    assert PERMIT_CANON not in merged
    assert SPECIAL_CANON not in merged
    assert conflicts == []
