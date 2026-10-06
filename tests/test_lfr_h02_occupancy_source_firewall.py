"""WO-LFR-OBJ-H02-P0-SOURCE-CONTRACT-FIREWALL-01 — H02 occupancy_capacity firewall.

H02-F1: SafeBuildingConsumerInput(occupancy_capacity=5000) → ValidationError
H02-F2: SafeBuildingConsumerInput(occupancy_capacity=0)    → ValidationError
H02-F3: _LEG_INPUT_FIELDS contains occupancy_capacity      (internal transport preserved)
H02-F4: _BUILDING_N1_FIELDS contains occupancy_capacity    (internal transport preserved)
H02-F5: build_facility internal source_facts occupancy_capacity=5000 preserved
H02-F6: build_facility internal source_facts occupancy_capacity=0 preserved (0 != absent)
H02-F7: factories.occupant_capacity NOT auto-injected into LEG values
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pydantic import ValidationError

from schemas.legal_engine import SafeBuildingConsumerInput
from clients.leg_runtime_client import build_facility, _LEG_INPUT_FIELDS, _BUILDING_N1_FIELDS
from services.safe_building_leg_runtime import _FACTORY_SELECT


class _Body:
    def __init__(self, sector="BUILDING", **kw):
        self.sector = sector
        self.input = kw.get("input", {})


# ── H02-F1: consumer direct integer assertion blocked ──────────────────────────

def test_H02_F1_consumer_direct_5000_blocked():
    with pytest.raises(ValidationError):
        SafeBuildingConsumerInput(occupancy_capacity=5000)


# ── H02-F2: consumer zero also blocked ────────────────────────────────────────

def test_H02_F2_consumer_zero_blocked():
    with pytest.raises(ValidationError):
        SafeBuildingConsumerInput(occupancy_capacity=0)


# ── H02-F3: _LEG_INPUT_FIELDS preserves occupancy_capacity (internal transport) ─

def test_H02_F3_leg_input_fields_contains():
    assert "occupancy_capacity" in _LEG_INPUT_FIELDS, (
        "occupancy_capacity must remain in _LEG_INPUT_FIELDS for internal canonical transport"
    )


# ── H02-F4: _BUILDING_N1_FIELDS preserves occupancy_capacity ─────────────────

def test_H02_F4_building_n1_fields_contains():
    assert "occupancy_capacity" in _BUILDING_N1_FIELDS, (
        "occupancy_capacity must remain in _BUILDING_N1_FIELDS for internal canonical transport"
    )


# ── H02-F5: internal source_facts 5000 transported ──────────────────────────

def test_H02_F5_internal_source_5000_preserved():
    fac = build_facility(_Body(sector="BUILDING", input={"occupancy_capacity": 5000}))
    assert fac.get("occupancy_capacity") == 5000


# ── H02-F6: internal source_facts 0 preserved (0 != absent) ─────────────────

def test_H02_F6_internal_source_zero_preserved():
    fac = build_facility(_Body(sector="BUILDING", input={"occupancy_capacity": 0}))
    assert fac.get("occupancy_capacity") == 0, "0 must be preserved as explicit value, not treated as absent"


# ── H02-F7: factories.occupant_capacity NOT auto-injected ────────────────────

def test_H02_F7_legacy_occupant_capacity_not_auto_injected():
    # _FACTORY_SELECT must not include occupant_capacity → it is never read from DB
    assert "occupant_capacity" not in _FACTORY_SELECT, (
        "factories.occupant_capacity must not be in _FACTORY_SELECT; "
        "LEGACY_UNPROVENANCED column must not auto-inject into LEG values"
    )
