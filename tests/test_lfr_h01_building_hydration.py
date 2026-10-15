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


# ── H11: H01 provenance leak regression — ts absent, hydration fail → floor_count absent ─

def test_H11_fc_no_timestamp_hydration_fail_floor_count_absent(monkeypatch):
    """H01 provenance correction: floor_count=35 + ts=None + hydration failure
    → floor_count must NOT appear in LEG input."""
    cap = {}
    _patch_leg(monkeypatch, cap)
    monkeypatch.setattr(_hyd_mod, "hydrate_factory_h01", lambda sb, fid: {
        "updated": False, "reason": "bdmgtsn_missing_or_invalid",
    })
    fac = {
        "floor_count": 35, "has_boiler": False, "is_multi_use": False,
        "building_height": None,
        "building_register_updated_at": None,
    }
    out = run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())
    assert "floor_count" not in cap["step1"].input
    assert "floor_count" in out["unresolved_fields"]


# ── H12: ts present + fc present → floor_count authoritative ─────────────────

def test_H12_ts_present_fc_authoritative(monkeypatch):
    """ts non-null + floor_count=35 → floor_count=35 in LEG input."""
    cap = {}
    _patch_leg(monkeypatch, cap)
    called = _no_hydrate(monkeypatch)
    fac = {
        "floor_count": 35, "has_boiler": False, "is_multi_use": False,
        "building_height": 80.0,
        "building_register_updated_at": "2026-01-01T00:00:00+09:00",
    }
    out = run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())
    assert cap["step1"].input.get("floor_count") == 35
    assert "floor_count" not in out["unresolved_fields"]


# ── H13: extract_h01_fields — 부속 전용 리스트 → {} (SOURCE_IDENTITY_UNRESOLVED) ──

def test_H13_no_main_building_returns_empty():
    """Fix A: 주건축물 없는 리스트 → first-row fallback 없이 {} 반환."""
    items = [
        {"mainAtchGbCdNm": "부속건축물", "heit": "3.0", "grndFlrCnt": "1"},
        {"mainAtchGbCdNm": "부속건축물", "heit": "2.5", "grndFlrCnt": "1"},
    ]
    out = extract_h01_fields(items)
    assert out == {}


# ── H14: extract_h01_fields — 음수 grndFlrCnt → floor_count 없음 ───────────────

def test_H14_negative_floor_count_rejected():
    """Fix C: grndFlrCnt="-3" → floor_count 키 없음."""
    items = [{"mainAtchGbCdNm": "주건축물", "grndFlrCnt": "-3", "heit": "15.0"}]
    out = extract_h01_fields(items)
    assert "floor_count" not in out
    assert out.get("building_height") == 15.0


# ── H15: extract_h01_fields — heit="inf" → building_height 없음 ─────────────────

def test_H15_inf_height_rejected():
    """Fix C: heit="inf" → building_height 키 없음."""
    items = [{"mainAtchGbCdNm": "주건축물", "heit": "inf", "grndFlrCnt": "10"}]
    out = extract_h01_fields(items)
    assert "building_height" not in out
    assert out.get("floor_count") == 10


# ── H16: extract_h01_fields — 음수 heit → building_height 없음 ──────────────────

def test_H16_negative_height_rejected():
    """Fix C: heit="-5.0" → building_height 키 없음."""
    items = [{"mainAtchGbCdNm": "주건축물", "heit": "-5.0", "grndFlrCnt": "3"}]
    out = extract_h01_fields(items)
    assert "building_height" not in out
    assert out.get("floor_count") == 3


# ── H17: fetch_h01_title_for_bdmgtsn — totalCount 기반 2-page 페치 ────────────

def test_H17_fetch_pagination_fetches_all_pages(monkeypatch):
    """Fix B: totalCount=2, 첫 페이지 1개 → 두 번째 페이지 추가 호출해 전체 반환."""
    import json as _j
    item1 = {"mainAtchGbCdNm": "주건축물", "heit": "45.0", "grndFlrCnt": "12"}
    item2 = {"mainAtchGbCdNm": "부속건축물", "heit": "3.0", "grndFlrCnt": "1"}
    calls = []

    def fake_kr_get(url, params, timeout):
        page = params.get("pageNo", 1)
        calls.append(page)
        if page == 1:
            body = {"totalCount": 2, "items": {"item": [item1]}}
        else:
            body = {"totalCount": 2, "items": {"item": [item2]}}
        return 200, _j.dumps({"response": {"body": body}})

    monkeypatch.setattr(_hyd_mod, "kr_get", fake_kr_get)
    result = _hyd_mod.fetch_h01_title_for_bdmgtsn("1168010100107190000")
    assert result is not None
    assert len(result) == 2
    assert calls == [1, 2]


# ── H18: fetch_h01_title_for_bdmgtsn — 두 번째 페이지 실패 → None ────────────────

def test_H18_fetch_second_page_failure_returns_none(monkeypatch):
    """Fix B: 두 번째 페이지 HTTP 500 → 부분 결과이므로 None 반환 (fail-closed)."""
    import json as _j
    item1 = {"mainAtchGbCdNm": "주건축물", "heit": "45.0"}

    def fake_kr_get(url, params, timeout):
        page = params.get("pageNo", 1)
        if page == 1:
            body = {"totalCount": 2, "items": {"item": [item1]}}
            return 200, _j.dumps({"response": {"body": body}})
        return 500, ""

    monkeypatch.setattr(_hyd_mod, "kr_get", fake_kr_get)
    result = _hyd_mod.fetch_h01_title_for_bdmgtsn("1168010100107190000")
    assert result is None


# ── H19: H03 — H01 수화에서 반환된 mgm_bldrgst_pk 를 H03에 전달 ─────────────────

def test_H19_h03_receives_h01_hydrated_pk(monkeypatch):
    """Fix D: H01 수화 결과의 mgm_bldrgst_pk 가 H03 호출에 그대로 전달된다."""
    import services.building_floor_hydration as _flr_mod

    cap = {}
    _patch_leg(monkeypatch, cap)
    monkeypatch.setattr(_hyd_mod, "hydrate_factory_h01", lambda sb, fid: {
        "updated": True,
        "building_height": 55.0,
        "floor_count": 15,
        "mgm_bldrgst_pk": "NEW-PK-FROM-H01",
    })

    pk_used = {}

    def fake_h03(bdmgtsn, main_pk):
        pk_used["pk"] = main_pk
        return {"resolved": True, "value": 5000.0}

    monkeypatch.setattr(_flr_mod, "resolve_floor_area_sum_11f_plus", fake_h03)

    fac = {
        "floor_count": None, "has_boiler": False, "is_multi_use": False,
        "building_height": None,
        "building_register_updated_at": None,
        "bdmgtsn": "1168010100107190000",
        "mgm_bldrgst_pk": "OLD-PK",
    }
    run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())
    assert pk_used.get("pk") == "NEW-PK-FROM-H01"


# ── H20: API 응답에 주건축물 없음 → runtime floor_count unresolved ─────────────

def test_H20_api_no_main_building_runtime_unresolved(monkeypatch):
    """Fix A: API 응답이 부속만 반환 → hydrate h01_fields_absent → floor_count unresolved."""
    cap = {}
    _patch_leg(monkeypatch, cap)

    monkeypatch.setattr(_hyd_mod, "fetch_h01_title_for_bdmgtsn", lambda bdmgtsn: [
        {"mainAtchGbCdNm": "부속건축물", "heit": "3.0", "grndFlrCnt": "1"},
    ])

    fac = {
        "floor_count": None, "has_boiler": False, "is_multi_use": False,
        "building_height": None,
        "building_register_updated_at": None,
        "bdmgtsn": "1168010100107190000",
    }
    out = run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())
    assert "floor_count" not in cap["step1"].input
    assert "floor_count" in out["unresolved_fields"]


# ── H21: floor_count=0 + ts 있음 → 0 그대로 LEG 입력, unresolved 없음 ──────────

def test_H21_zero_floor_count_authoritative_preserved(monkeypatch):
    """Fix C: floor_count=0 은 유효한 명시값. ts 있으면 authoritative → LEG 입력 0."""
    cap = {}
    _patch_leg(monkeypatch, cap)
    called = _no_hydrate(monkeypatch)
    fac = {
        "floor_count": 0, "has_boiler": False, "is_multi_use": False,
        "building_height": 5.0,
        "building_register_updated_at": "2026-01-01T00:00:00+09:00",
    }
    out = run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())
    assert called["n"] == 0
    assert cap["step1"].input.get("floor_count") == 0
    assert "floor_count" not in out["unresolved_fields"]
