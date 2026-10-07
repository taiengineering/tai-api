"""WO-LFR-OBJ-S03: indoor_workplace INDUSTRIAL sector gate — build_facility tests.

A: sector=INDUSTRIAL, indoor_workplace=True  → facility["indoor_workplace"] is True
B: sector=INDUSTRIAL, indoor_workplace=False → facility["indoor_workplace"] is False
C: sector=INDUSTRIAL, indoor_workplace absent → key absent
D: sector=BUILDING,   indoor_workplace=True  → key absent
E: sector=CONSTRUCTION, indoor_workplace=True → key absent
"""
from __future__ import annotations

from types import SimpleNamespace

from clients.leg_runtime_client import _LEG_INPUT_FIELDS, _INDUSTRIAL_ONLY_FIELDS, build_facility


def test_A_industrial_true_passes():
    body = SimpleNamespace(sector="INDUSTRIAL", input={"indoor_workplace": True})
    assert build_facility(body).get("indoor_workplace") is True


def test_B_industrial_false_preserved():
    body = SimpleNamespace(sector="INDUSTRIAL", input={"indoor_workplace": False})
    assert build_facility(body).get("indoor_workplace") is False


def test_C_industrial_missing_omitted():
    body = SimpleNamespace(sector="INDUSTRIAL", input={})
    assert "indoor_workplace" not in build_facility(body)


def test_D_building_blocked():
    body = SimpleNamespace(sector="BUILDING", input={"indoor_workplace": True})
    assert "indoor_workplace" not in build_facility(body)


def test_E_construction_blocked():
    body = SimpleNamespace(sector="CONSTRUCTION", input={"indoor_workplace": True})
    assert "indoor_workplace" not in build_facility(body)


def test_indoor_workplace_in_allowlist():
    assert "indoor_workplace" in _LEG_INPUT_FIELDS
    assert "indoor_workplace" in _INDUSTRIAL_ONLY_FIELDS
