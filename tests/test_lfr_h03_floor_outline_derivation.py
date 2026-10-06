"""WO-LFR-OBJ-H03-FAST-01 — 11층 이상 지상층 바닥면적 합계 도출 계약.

H03-01: 11F inclusion exact
H03-02: 10F exclusion
H03-03: basement exclusion
H03-04: multi-row same floor additive (no dedup)
H03-05: multiple upper floors
H03-06: area excluded (areaExctYn=1)
H03-07: zero area preserved
H03-08: wrong building excluded (different mgmBldrgstPk)
H03-09: malformed ground flrNo → fail-closed
H03-10: malformed qualifying area → fail-closed
H03-11: unknown areaExctYn → fail-closed
H03-12: no qualifying row with authoritative floor_count>=11 → unresolved (not 0)
H03-13: partial pagination → unresolved
H03-14: complete multipage → derive from all pages
H03-15: floor_count<11 short circuit → no H03 API call
H03-16: direct user override prohibited → ValidationError
H03-17: runtime binding → floor_area_sum_at_or_above_11f in step1
H03-18: hydration failure → fact absent, LEG still runs
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import services.building_floor_hydration as _flr_mod
import services.safe_building_leg_runtime as bld_rt
from services.safe_building_leg_runtime import run_safe_building_leg
from services.building_floor_hydration import resolve_floor_area_sum_11f_plus
import services.building_register_hydration as _hyd_mod
from schemas.legal_engine import SafeBuildingConsumerInput


# ── Shared mock infrastructure ───────────────────────────────────────────────

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

def _no_h01(monkeypatch):
    monkeypatch.setattr(_hyd_mod, "hydrate_factory_h01",
                        lambda sb, fid: {"updated": False, "reason": "mock"})

_BDMGTSN = "1168010100107190000"  # valid 19-char
_MAIN_PK  = "11680-10100-0-0719-0000-001"

def _row(pk=_MAIN_PK, flrGbCd="20", flrGbCdNm="지상",
         flrNo=11, area="500", areaExctYn="0"):
    return {
        "mgmBldrgstPk": pk,
        "flrGbCd": flrGbCd,
        "flrGbCdNm": flrGbCdNm,
        "flrNo": flrNo,
        "area": area,
        "areaExctYn": areaExctYn,
    }

def _mock_fetch(monkeypatch, rows, ok=True, reason=None):
    result = {"ok": ok, "rows": rows, "page_count": 1} if ok else {"ok": False, "reason": reason}
    monkeypatch.setattr(_flr_mod, "_fetch_all_floor_rows", lambda bdmgtsn: result)


# ── H03-01: 11F exact inclusion ───────────────────────────────────────────────

def test_H03_01_11f_inclusion_exact(monkeypatch):
    _mock_fetch(monkeypatch, [_row(flrNo=11, area="500")])
    r = resolve_floor_area_sum_11f_plus(_BDMGTSN, _MAIN_PK)
    assert r["resolved"] is True
    assert r["value"] == 500.0


# ── H03-02: 10F excluded ──────────────────────────────────────────────────────

def test_H03_02_10f_excluded(monkeypatch):
    _mock_fetch(monkeypatch, [
        _row(flrNo=10, area="1000"),
        _row(flrNo=11, area="500"),
    ])
    r = resolve_floor_area_sum_11f_plus(_BDMGTSN, _MAIN_PK)
    assert r["resolved"] is True
    assert r["value"] == 500.0


# ── H03-03: basement excluded ─────────────────────────────────────────────────

def test_H03_03_basement_excluded(monkeypatch):
    _mock_fetch(monkeypatch, [
        _row(flrGbCd="30", flrGbCdNm="지하", flrNo=11, area="900"),
        _row(flrNo=11, area="500"),
    ])
    r = resolve_floor_area_sum_11f_plus(_BDMGTSN, _MAIN_PK)
    assert r["resolved"] is True
    assert r["value"] == 500.0


# ── H03-04: multi-row same floor additive ────────────────────────────────────

def test_H03_04_same_floor_additive(monkeypatch):
    _mock_fetch(monkeypatch, [
        _row(flrNo=11, area="500"),
        _row(flrNo=11, area="300"),
    ])
    r = resolve_floor_area_sum_11f_plus(_BDMGTSN, _MAIN_PK)
    assert r["resolved"] is True
    assert r["value"] == 800.0
    assert r["qualifying_row_count"] == 2


# ── H03-05: multiple upper floors ────────────────────────────────────────────

def test_H03_05_multiple_upper_floors(monkeypatch):
    _mock_fetch(monkeypatch, [
        _row(flrNo=11, area="500"),
        _row(flrNo=12, area="600"),
        _row(flrNo=20, area="700"),
    ])
    r = resolve_floor_area_sum_11f_plus(_BDMGTSN, _MAIN_PK)
    assert r["resolved"] is True
    assert r["value"] == 1800.0


# ── H03-06: area excluded by areaExctYn=1 ───────────────────────────────────

def test_H03_06_area_excluded_flag(monkeypatch):
    _mock_fetch(monkeypatch, [
        _row(flrNo=11, area="500", areaExctYn="1"),
        _row(flrNo=11, area="300", areaExctYn="0"),
    ])
    r = resolve_floor_area_sum_11f_plus(_BDMGTSN, _MAIN_PK)
    assert r["resolved"] is True
    assert r["value"] == 300.0


# ── H03-07: zero area preserved ──────────────────────────────────────────────

def test_H03_07_zero_area_preserved(monkeypatch):
    _mock_fetch(monkeypatch, [_row(flrNo=11, area="0")])
    r = resolve_floor_area_sum_11f_plus(_BDMGTSN, _MAIN_PK)
    assert r["resolved"] is True
    assert r["value"] == 0.0
    assert r["qualifying_row_count"] == 1


# ── H03-08: wrong building excluded ──────────────────────────────────────────

def test_H03_08_wrong_building_excluded(monkeypatch):
    _mock_fetch(monkeypatch, [
        _row(pk=_MAIN_PK, flrNo=11, area="500"),
        _row(pk="OTHER-PK", flrNo=11, area="900"),
    ])
    r = resolve_floor_area_sum_11f_plus(_BDMGTSN, _MAIN_PK)
    assert r["resolved"] is True
    assert r["value"] == 500.0


# ── H03-09: malformed ground floor number → fail-closed ─────────────────────

def test_H03_09_malformed_floor_no_fail_closed(monkeypatch):
    _mock_fetch(monkeypatch, [_row(flrNo="invalid", area="500")])
    r = resolve_floor_area_sum_11f_plus(_BDMGTSN, _MAIN_PK)
    assert r["resolved"] is False
    assert r["reason"] == "invalid_floor_no"


# ── H03-10: malformed qualifying area → fail-closed ─────────────────────────

def test_H03_10_malformed_area_fail_closed(monkeypatch):
    _mock_fetch(monkeypatch, [_row(flrNo=11, area="notanumber")])
    r = resolve_floor_area_sum_11f_plus(_BDMGTSN, _MAIN_PK)
    assert r["resolved"] is False
    assert r["reason"] == "invalid_area"


# ── H03-11: unknown areaExctYn → fail-closed ─────────────────────────────────

def test_H03_11_unknown_area_exclusion_flag(monkeypatch):
    _mock_fetch(monkeypatch, [_row(flrNo=11, area="500", areaExctYn="?")])
    r = resolve_floor_area_sum_11f_plus(_BDMGTSN, _MAIN_PK)
    assert r["resolved"] is False
    assert r["reason"] == "invalid_area_exclusion_flag"


# ── H03-12: no qualifying row with authoritative floor_count >= 11 ───────────

def test_H03_12_no_qualifying_row_unresolved(monkeypatch):
    """Complete source, no 11F+ rows → unresolved (NOT 0)."""
    _mock_fetch(monkeypatch, [_row(flrNo=5, area="1000")])
    r = resolve_floor_area_sum_11f_plus(_BDMGTSN, _MAIN_PK)
    assert r["resolved"] is False
    assert r["reason"] == "no_qualifying_rows"


# ── H03-13: partial pagination → unresolved ──────────────────────────────────

def test_H03_13_partial_pagination_unresolved(monkeypatch):
    _mock_fetch(monkeypatch, rows=[], ok=False, reason="api_partial_result")
    r = resolve_floor_area_sum_11f_plus(_BDMGTSN, _MAIN_PK)
    assert r["resolved"] is False
    assert r["reason"] == "api_partial_result"


# ── H03-14: complete multipage → derive from all pages ───────────────────────

def test_H03_14_complete_multipage(monkeypatch):
    page1 = [_row(flrNo=11, area="500"), _row(flrNo=12, area="600")]
    page2 = [_row(flrNo=13, area="700")]
    all_rows = page1 + page2
    monkeypatch.setattr(_flr_mod, "_fetch_all_floor_rows",
                        lambda bdmgtsn: {"ok": True, "rows": all_rows, "page_count": 2})
    r = resolve_floor_area_sum_11f_plus(_BDMGTSN, _MAIN_PK)
    assert r["resolved"] is True
    assert r["value"] == 1800.0
    assert r["page_count"] == 2
    assert r["qualifying_row_count"] == 3


# ── H03-15: floor_count < 11 short circuit → no H03 API call ─────────────────

def test_H03_15_floor_count_below_11_no_api_call(monkeypatch):
    cap = {}
    _patch_leg(monkeypatch, cap)
    _no_h01(monkeypatch)
    h03_called = {"n": 0}

    def fake_resolve(bdmgtsn, pk):
        h03_called["n"] += 1
        return {"resolved": True, "value": 9999.0}

    monkeypatch.setattr(_flr_mod, "resolve_floor_area_sum_11f_plus", fake_resolve)

    fac = {
        "floor_count": 10, "has_boiler": False, "is_multi_use": False,
        "building_height": 30.0,
        "building_register_updated_at": "2026-01-01T00:00:00+09:00",
        "bdmgtsn": _BDMGTSN, "mgm_bldrgst_pk": _MAIN_PK,
    }
    run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())
    assert h03_called["n"] == 0
    assert "floor_area_sum_at_or_above_11f" not in cap["step1"].input


# ── H03-16: direct user override prohibited ───────────────────────────────────

def test_H03_16_direct_user_override_prohibited():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        SafeBuildingConsumerInput(**{"floor_area_sum_at_or_above_11f": 10000})


# ── H03-17: runtime binding ───────────────────────────────────────────────────

def test_H03_17_runtime_binding(monkeypatch):
    cap = {}
    _patch_leg(monkeypatch, cap)
    _no_h01(monkeypatch)
    monkeypatch.setattr(_flr_mod, "resolve_floor_area_sum_11f_plus",
                        lambda bdmgtsn, pk: {"resolved": True, "value": 10500.0,
                                              "qualifying_row_count": 5, "page_count": 1})
    fac = {
        "floor_count": 15, "has_boiler": False, "is_multi_use": False,
        "building_height": 55.0,
        "building_register_updated_at": "2026-01-01T00:00:00+09:00",
        "bdmgtsn": _BDMGTSN, "mgm_bldrgst_pk": _MAIN_PK,
    }
    run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())
    assert cap["step1"].input.get("floor_area_sum_at_or_above_11f") == 10500.0


# ── H03-18: hydration failure → fact absent, LEG still runs ──────────────────

def test_H03_18_hydration_failure_leg_still_runs(monkeypatch):
    cap = {}
    _patch_leg(monkeypatch, cap)
    _no_h01(monkeypatch)
    monkeypatch.setattr(_flr_mod, "resolve_floor_area_sum_11f_plus",
                        lambda bdmgtsn, pk: {"resolved": False, "reason": "api_no_result"})
    fac = {
        "floor_count": 15, "has_boiler": False, "is_multi_use": False,
        "building_height": 55.0,
        "building_register_updated_at": "2026-01-01T00:00:00+09:00",
        "bdmgtsn": _BDMGTSN, "mgm_bldrgst_pk": _MAIN_PK,
    }
    out = run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())
    assert "floor_area_sum_at_or_above_11f" not in cap["step1"].input
    assert out["full_result"] is not None
