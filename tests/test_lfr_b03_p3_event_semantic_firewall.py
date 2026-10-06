"""WO-LFR-OBJ-B03-P3-SEMANTIC-RESOLVE-01 — B03 event semantic firewall.

Consumer assertion surface CLOSED / internal canonical transport OPEN.

T1: SafeBuildingConsumerInput(has_hazardous_material_in_out_event=True) → ValidationError
T2: SafeBuildingConsumerInput(has_hazardous_material_in_out_event=False) → ValidationError
T3: _LEG_INPUT_FIELDS contains has_hazardous_material_in_out_event (canonical transport preserved)
T4: build_saas_leg_step1 with source_facts event=True → step1.input preserves it
T5: project_factory_material_rows does NOT emit has_hazardous_material_in_out_event
T6: static has_hazardous_material=True in source_facts does NOT produce event fact
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from clients.leg_runtime_client import _LEG_INPUT_FIELDS
from schemas.legal_engine import SafeBuildingConsumerInput
from services.canonical.saas_leg_source_adapter import build_saas_leg_step1
from services.material_source.projector import project_factory_material_rows


_EVENT_FIELD = "has_hazardous_material_in_out_event"


# ── T1: True assertion blocked ─────────────────────────────────────────────────
def test_T1_consumer_true_raises():
    with pytest.raises(ValidationError):
        SafeBuildingConsumerInput(**{_EVENT_FIELD: True})


# ── T2: False assertion blocked ────────────────────────────────────────────────
def test_T2_consumer_false_raises():
    with pytest.raises(ValidationError):
        SafeBuildingConsumerInput(**{_EVENT_FIELD: False})


# ── T3: canonical transport vocabulary intact ──────────────────────────────────
def test_T3_canonical_vocabulary_preserved():
    assert _EVENT_FIELD in _LEG_INPUT_FIELDS


# ── T4: source_facts passthrough via build_saas_leg_step1 ─────────────────────
def test_T4_source_facts_transport_preserved():
    step1 = build_saas_leg_step1(
        sector="BUILDING",
        source_facts={_EVENT_FIELD: True},
        factory_id="F-test",
    )
    inp = step1.input or {}
    assert inp.get(_EVENT_FIELD) is True


# ── T5: material projector does not emit event fact ───────────────────────────
def test_T5_material_projector_no_event_emission():
    rows = [
        {"is_active": True, "material_master_key": "SOME_HAZMAT_KEY"},
        {"is_active": True, "material_master_key": "ANOTHER_KEY"},
    ]
    result = project_factory_material_rows(rows)
    assert _EVENT_FIELD not in result


# ── T6: static has_hazardous_material in source_facts does not produce event ───
def test_T6_static_hazardous_material_no_event_derivation():
    step1 = build_saas_leg_step1(
        sector="BUILDING",
        source_facts={"has_hazardous_material": True},
        factory_id="F-test",
    )
    inp = step1.input or {}
    assert _EVENT_FIELD not in inp
