"""WO-LFR-OBJ-H01-FAST-01 — H01 Building Height/Floor Count Hydration contract.

H1:  extract_h01_fields — grndFlrCnt=0 preserved (GAP-3 fix)
H2:  parse_bdmgtsn valid 19-char → correct parsed dict
H3:  parse_bdmgtsn invalid input → None
H4:  extract_h01_fields — 주건축물 row selected over non-주건축물
H5:  runtime — ts+bh+fc authoritative → NO hydration, building_height_m in LEG input
H6:  runtime — ts=None → hydration triggered
H7:  runtime — hydration returns building_height → building_height_m in LEG input
H8:  runtime — hydration returns floor_count → values promoted, unresolved cleared
H9:  runtime — hydration updated=False → building_height_m absent from LEG input
H10: runtime — consumer override building_height_m wins over hydration
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import services.safe_building_leg_runtime as bld_rt
from services.safe_building_leg_runtime import run_safe_building_leg
from services.building_register_hydration import extract_h01_fields, parse_bdmgtsn
import services.building_register_hydration as _hyd_mod
from schemas.legal_engine import SafeBuildingConsumerInput


class _Res:
    def __init__(s, d): s.data = d


class _Q:
    def __init__(s, rows): s._rows = rows
    def select(s, *a, **k): return s
    def eq(s, *a, **k): return s
    def limit(s, *a, **k): return s
    def order(s, *a, **k): return s
    def execute(s): return _Res(s._rows)


class _FakeSB:
    def __init__(s, fac): s._fac = fac
    def table(s, n): return _Q([s._fac] if (n == "factories" and s._fac) else [])


def _patch_leg(monkeypatch, cap):
    def fake(step1):
        cap["step1"] = step1
        return {"engine_family": "LEG", "sector": "BUILDING", "obligations": []}
    monkeypatch.setattr(bld_rt, "run_leg_diagnosis", fake)


def _no_hydrate(monkeypatch):
    called = {"n": 0}
    def fake(sb, fid):
        called["n"] += 1
        return {"updated": False, "reason": "mock_no_hydrate"}
    monkeypatch.setattr(_hyd_mod, "hydrate_factory_h01", fake)
    return called


# ── H1: extract_h01_fields grndFlrCnt=0 preserved ───────────────────────────

def test_H1_grnd_flr_cnt_zero_preserved():
    items = [{"mainAtchGbCdNm": "주건축물", "grndFlrCnt": "0", "heit": "12.5"}]
    out = extract_h01_fields(items)
    assert "floor_count" in out
    assert out["floor_count"] == 0


# ── H2: parse_bdmgtsn valid ──────────────────────────────────────────────────

def test_H2_parse_bdmgtsn_valid():
    bdmgtsn = "1168010100107190000"  # 19자리
    p = parse_bdmgtsn(bdmgtsn)
    assert p is not None
    assert p["sigunguCd"] == "11680"
    assert p["bjdongCd"] == "10100"
    assert p["mountain"] == "1"
    assert p["bun"] == "0719"
    assert p["ji"] == "0000"


# ── H3: parse_bdmgtsn invalid ───────────────────────────────────────────────

def test_H3_parse_bdmgtsn_invalid_returns_none():
    assert parse_bdmgtsn("") is None
    assert parse_bdmgtsn("12345") is None
    assert parse_bdmgtsn(None) is None  # type: ignore[arg-type]


# ── H4: extract_h01_fields 주건축물 selection ────────────────────────────────

def test_H4_extract_main_building_selected():
    items = [
        {"mainAtchGbCdNm": "부속건축물", "heit": "3.0", "grndFlrCnt": "1"},
        {"mainAtchGbCdNm": "주건축물",   "heit": "45.0", "grndFlrCnt": "12"},
    ]
    out = extract_h01_fields(items)
    assert out.get("building_height") == 45.0
    assert out.get("floor_count") == 12


# ── H5: runtime — ts+bh+fc authoritative → NO hydration ─────────────────────

def test_H5_authoritative_no_hydration(monkeypatch):
    cap = {}
    _patch_leg(monkeypatch, cap)
    called = _no_hydrate(monkeypatch)
    fac = {
        "floor_count": 10, "has_boiler": False, "is_multi_use": False,
        "building_height": 42.5,
        "building_register_updated_at": "2026-01-01T00:00:00+09:00",
    }
    run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())
    assert called["n"] == 0
    assert cap["step1"].input.get("building_height_m") == 42.5


# ── H6: runtime — ts=None → hydration triggered ─────────────────────────────

def test_H6_ts_none_triggers_hydration(monkeypatch):
    cap = {}
    _patch_leg(monkeypatch, cap)
    called = {"n": 0}
    def fake_hyd(sb, fid):
        called["n"] += 1
        return {"updated": False, "reason": "no_bdmgtsn"}
    monkeypatch.setattr(_hyd_mod, "hydrate_factory_h01", fake_hyd)

    fac = {
        "floor_count": 5, "has_boiler": False, "is_multi_use": False,
        "building_height": 20.0,
        "building_register_updated_at": None,
    }
    run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())
    assert called["n"] == 1


# ── H7: hydration returns building_height → building_height_m in LEG input ──

def test_H7_hydration_building_height_reaches_leg(monkeypatch):
    cap = {}
    _patch_leg(monkeypatch, cap)
    monkeypatch.setattr(_hyd_mod, "hydrate_factory_h01", lambda sb, fid: {
        "updated": True,
        "building_height": 88.0,
        "floor_count": None,
    })
    fac = {
        "floor_count": 5, "has_boiler": False, "is_multi_use": False,
        "building_height": None,
        "building_register_updated_at": None,
    }
    run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())
    assert cap["step1"].input.get("building_height_m") == 88.0


# ── H8: hydration returns floor_count → promoted, unresolved cleared ─────────

def test_H8_hydration_floor_count_promoted(monkeypatch):
    cap = {}
    _patch_leg(monkeypatch, cap)
    monkeypatch.setattr(_hyd_mod, "hydrate_factory_h01", lambda sb, fid: {
        "updated": True,
        "building_height": None,
        "floor_count": 15,
    })
    fac = {
        "floor_count": None, "has_boiler": False, "is_multi_use": False,
        "building_height": None,
        "building_register_updated_at": None,
    }
    out = run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())
    assert cap["step1"].input.get("floor_count") == 15
    assert "floor_count" not in out["unresolved_fields"]


# ── H9: hydration updated=False → building_height_m absent ──────────────────

def test_H9_hydration_failed_building_height_m_absent(monkeypatch):
    cap = {}
    _patch_leg(monkeypatch, cap)
    monkeypatch.setattr(_hyd_mod, "hydrate_factory_h01", lambda sb, fid: {
        "updated": False, "reason": "api_no_result",
    })
    fac = {
        "floor_count": 5, "has_boiler": False, "is_multi_use": False,
        "building_height": None,
        "building_register_updated_at": None,
    }
    run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())
    assert "building_height_m" not in cap["step1"].input


# ── H10: consumer override wins over hydration ───────────────────────────────

def test_H10_consumer_override_wins_over_hydration(monkeypatch):
    cap = {}
    _patch_leg(monkeypatch, cap)
    monkeypatch.setattr(_hyd_mod, "hydrate_factory_h01", lambda sb, fid: {
        "updated": True,
        "building_height": 50.0,
        "floor_count": None,
    })
    fac = {
        "floor_count": 5, "has_boiler": False, "is_multi_use": False,
        "building_height": None,
        "building_register_updated_at": None,
    }
    ci = SafeBuildingConsumerInput(building_height_m=999.0)
    run_safe_building_leg(_FakeSB(fac), "F1", ci)
    assert cap["step1"].input.get("building_height_m") == 999.0
