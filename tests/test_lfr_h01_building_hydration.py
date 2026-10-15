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
        "mgm_bldrgst_pk": "FACTORY-PK-001",
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
        "mgm_bldrgst_pk": "FACTORY-PK-001",
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

    monkeypatch.setattr(_hyd_mod, "fetch_h01_title_for_bdmgtsn", lambda bdmgtsn, existing_pk=None: [
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


# ── 보정 WO 공용 인프라 ─────────────────────────────────────────────────────────

_PK_A = "11680-10100-0-0719-0000-001"
_PK_B = "11680-10100-0-0719-0000-002"
_BDMGTSN_0001 = "1168010100107190001"  # ji="0001" (대체 지번 테스트용)


class _TrackingQ:
    def __init__(self, rows):
        self._rows = rows
        self.update_patches = []

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self

    def update(self, patch):
        self.update_patches.append(dict(patch))
        return self

    def execute(self): return _Res(self._rows)


class _TrackingSB:
    def __init__(self, row):
        self._q = _TrackingQ([row] if row else [])

    def table(self, n): return self._q

    @property
    def update_patches(self): return self._q.update_patches


def _make_response(total, items, page_ok=True):
    """kr_get 가짜 응답 생성 헬퍼."""
    import json as _j
    if not page_ok:
        return 500, ""
    body = {"totalCount": total}
    if items is not None:
        body["items"] = {"item": items}
    return 200, _j.dumps({"response": {"body": body}})


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
        "mgm_bldrgst_pk": "FACTORY-PK-001",
    }
    out = run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())
    assert called["n"] == 0
    assert cap["step1"].input.get("floor_count") == 0
    assert "floor_count" not in out["unresolved_fields"]


# ── H22: 복수 주건축물 + 기존 PK 일치 → 정확한 건물 선택 ──────────────────────

def test_H22_multiple_main_existing_pk_selects_correct():
    """Fix A: 복수 주건축물 중 기존 PK 일치하는 1개만 선택한다."""
    items = [
        {"mainAtchGbCdNm": "주건축물", "mgmBldrgstPk": _PK_A, "heit": "45.0", "grndFlrCnt": "12"},
        {"mainAtchGbCdNm": "주건축물", "mgmBldrgstPk": _PK_B, "heit": "20.0", "grndFlrCnt": "5"},
    ]
    out = extract_h01_fields(items, existing_pk=_PK_A)
    assert out.get("building_height") == 45.0
    assert out.get("floor_count") == 12
    assert out.get("mgm_bldrgst_pk") == _PK_A


# ── H23: 복수 주건축물 + 기존 PK 없음 → unresolved ──────────────────────────────

def test_H23_multiple_main_no_existing_pk_unresolved():
    """Fix A: 기존 PK 없는데 복수 주건축물 → SOURCE_IDENTITY_UNRESOLVED."""
    items = [
        {"mainAtchGbCdNm": "주건축물", "mgmBldrgstPk": _PK_A, "heit": "45.0"},
        {"mainAtchGbCdNm": "주건축물", "mgmBldrgstPk": _PK_B, "heit": "20.0"},
    ]
    out = extract_h01_fields(items)
    assert out == {}


# ── H24: 기존 PK와 API 후보 모두 불일치 → unresolved ────────────────────────────

def test_H24_existing_pk_no_api_match_unresolved():
    """Fix A: 기존 PK가 API 어느 후보와도 일치하지 않음 → SOURCE_IDENTITY_UNRESOLVED."""
    items = [
        {"mainAtchGbCdNm": "주건축물", "mgmBldrgstPk": _PK_B, "heit": "20.0"},
    ]
    out = extract_h01_fields(items, existing_pk=_PK_A)
    assert out == {}


# ── H25: API 응답에 PK 없음 → 동일성 확인 불가 → DB 쓰기 금지 ──────────────────

def test_H25_pk_absent_in_api_no_db_write(monkeypatch):
    """Fix A: API가 PK 없이 반환 → h01_identity_unresolved → DB UPDATE 0회."""
    monkeypatch.setattr(_hyd_mod, "fetch_h01_title_for_bdmgtsn", lambda bdmgtsn, existing_pk=None: [
        {"mainAtchGbCdNm": "주건축물", "heit": "30.0", "grndFlrCnt": "10"},
    ])

    fac = {"bdmgtsn": "1168010100107190000", "mgm_bldrgst_pk": None}
    sb = _TrackingSB(fac)
    from services.building_register_hydration import hydrate_factory_h01
    result = hydrate_factory_h01(sb, "F1")
    assert result.get("updated") is False
    assert len(sb.update_patches) == 0


# ── H26: totalCount 존재 + 중간 빈 페이지 → 즉시 종료 ──────────────────────────

def test_H26_empty_page_with_expected_remaining_fails(monkeypatch):
    """Fix B: totalCount=2, 두 번째 페이지 items 없음 → None (부분 결과 거부)."""
    item1 = {"mainAtchGbCdNm": "주건축물", "heit": "45.0"}

    def fake_kr_get(url, params, timeout):
        page = params.get("pageNo", 1)
        if page == 1:
            return _make_response(2, [item1])
        return _make_response(2, None)  # items key 없음

    monkeypatch.setattr(_hyd_mod, "kr_get", fake_kr_get)
    result = _hyd_mod.fetch_h01_title_for_bdmgtsn("1168010100107190000")
    assert result is None


# ── H27: totalCount 누락·변동·음수 → 실패 ────────────────────────────────────

def test_H27_total_count_invalid_variants_fail(monkeypatch):
    """Fix B: totalCount 누락/변동/음수 모두 None 반환."""
    import json as _j

    # H27a: totalCount 누락
    def no_total(url, params, timeout):
        return 200, _j.dumps({"response": {"body": {}}})  # no totalCount

    monkeypatch.setattr(_hyd_mod, "kr_get", no_total)
    assert _hyd_mod.fetch_h01_title_for_bdmgtsn("1168010100107190000") is None

    # H27b: 페이지 간 totalCount 변동
    item = {"mainAtchGbCdNm": "주건축물"}
    page_calls = [0]

    def changing_total(url, params, timeout):
        page_calls[0] += 1
        tc = 4 if page_calls[0] == 1 else 3
        return _make_response(tc, [item, item])

    monkeypatch.setattr(_hyd_mod, "kr_get", changing_total)
    page_calls[0] = 0
    assert _hyd_mod.fetch_h01_title_for_bdmgtsn("1168010100107190000") is None

    # H27c: 음수 totalCount
    def neg_total(url, params, timeout):
        return _make_response(-1, [item])

    monkeypatch.setattr(_hyd_mod, "kr_get", neg_total)
    assert _hyd_mod.fetch_h01_title_for_bdmgtsn("1168010100107190000") is None


# ── H28: ji 대체 검색 — existing_pk 제공 시 fallback 허용, PK 불일치 차단 ─────

def test_H28_ji_fallback_with_pk_mismatch_blocked(monkeypatch):
    """PATCH A+: existing_pk 있으면 ji=0000 fallback 허용하되
    API 반환 건물 PK가 기존 PK와 불일치하면 extract_h01_fields 가 {} 반환."""
    item_wrong = {
        "mainAtchGbCdNm": "주건축물", "mgmBldrgstPk": "DIFFERENT-PK",
        "heit": "30.0", "grndFlrCnt": "10",
    }

    def fake_kr_get(url, params, timeout):
        ji = params.get("ji", "")
        if ji == "0001":
            return _make_response(0, None)  # totalCount=0 at original ji
        return _make_response(1, [item_wrong])  # ji=0000 has wrong-PK building

    monkeypatch.setattr(_hyd_mod, "kr_get", fake_kr_get)
    # existing_pk provided → fallback permitted → returns wrong-PK item
    items = _hyd_mod.fetch_h01_title_for_bdmgtsn(_BDMGTSN_0001, existing_pk="CORRECT-PK")
    assert items is not None and len(items) == 1

    # extract with existing_pk="CORRECT-PK" → DIFFERENT-PK 불일치 → {}
    out = extract_h01_fields(items, existing_pk="CORRECT-PK")
    assert out == {}


# ── H29: 부분 수화(높이만) → floor_count=None PATCH, 기존 admin 값 인증 차단 ───

def test_H29_partial_hydration_clears_unauthenticated_floor_count(monkeypatch):
    """Fix C: API가 높이만 반환 → PATCH에 floor_count=None 포함 → false-auth 방지."""
    import services.time as _time_svc
    monkeypatch.setattr(_time_svc, "now_kst", lambda: "2026-10-15")
    monkeypatch.setattr(_time_svc, "serialize_business_datetime", lambda x: "TS-MOCK")

    monkeypatch.setattr(_hyd_mod, "fetch_h01_title_for_bdmgtsn", lambda bdmgtsn, existing_pk=None: [
        {"mainAtchGbCdNm": "주건축물", "mgmBldrgstPk": _PK_A, "heit": "30.0"},
    ])

    fac = {"bdmgtsn": "1168010100107190000", "mgm_bldrgst_pk": None}
    sb = _TrackingSB(fac)
    from services.building_register_hydration import hydrate_factory_h01
    result = hydrate_factory_h01(sb, "F1")

    assert result.get("updated") is True
    assert len(sb.update_patches) == 1
    p = sb.update_patches[0]
    assert p.get("building_height") == 30.0
    assert "floor_count" in p and p["floor_count"] is None  # 명시적 클리어
    assert p.get("mgm_bldrgst_pk") == _PK_A


# ── H30: H01+H03 수치 → C3 build_facility 보존 확인 ─────────────────────────────

def test_H30_c3_build_facility_preserves_h01_h03_values(monkeypatch):
    """Fix D: H01(floor_count + building_height_m) + H03(floor_area_sum) → step1.input.
    실제 build_facility() 호출로 facility 계약까지 검증."""
    from clients.leg_runtime_client import build_facility
    import services.building_floor_hydration as _flr_mod
    cap = {}
    _patch_leg(monkeypatch, cap)
    _no_hydrate(monkeypatch)
    monkeypatch.setattr(_flr_mod, "resolve_floor_area_sum_11f_plus",
                        lambda bdmgtsn, pk: {"resolved": True, "value": 12500.0})
    fac = {
        "floor_count": 15, "has_boiler": False, "is_multi_use": False,
        "building_height": 55.0,
        "building_register_updated_at": "2026-01-01T00:00:00+09:00",
        "bdmgtsn": "1168010100107190000",
        "mgm_bldrgst_pk": _PK_A,
    }
    out = run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())
    inp = cap["step1"].input
    assert inp.get("floor_count") == 15
    assert inp.get("building_height_m") == 55.0
    assert inp.get("floor_area_sum_at_or_above_11f") == 12500.0
    assert out["full_result"] is not None
    # 실제 build_facility() 로 facility 계약 검증 (C3)
    facility = build_facility(cap["step1"])
    assert facility.get("floor_count") == 15
    assert facility.get("building_height_m") == 55.0
    assert facility.get("floor_area_sum_at_or_above_11f") == 12500.0


# ── H31: 본동 식별 실패 → DB UPDATE 0회, H03 수치 생성 0 ─────────────────────────

def test_H31_identity_unresolved_no_db_update(monkeypatch):
    """Fix A: 본동 식별 실패(부속만) → DB UPDATE 0회."""
    monkeypatch.setattr(_hyd_mod, "fetch_h01_title_for_bdmgtsn", lambda bdmgtsn, existing_pk=None: [
        {"mainAtchGbCdNm": "부속건축물", "mgmBldrgstPk": _PK_A, "heit": "5.0"},
    ])
    fac = {"bdmgtsn": "1168010100107190000", "mgm_bldrgst_pk": None}
    sb = _TrackingSB(fac)
    from services.building_register_hydration import hydrate_factory_h01
    result = hydrate_factory_h01(sb, "F1")
    assert result.get("updated") is False
    assert len(sb.update_patches) == 0


# ── H32: bool·소수 층수·NaN float·Infinity float → 거부 ──────────────────────

def test_H32_invalid_numeric_types_all_rejected():
    """Fix C: bool/소수/NaN float/Infinity float → 수치 추출 거부."""
    # bool 층수 거부
    out = extract_h01_fields([{"mainAtchGbCdNm": "주건축물", "grndFlrCnt": True, "heit": "10.0"}])
    assert "floor_count" not in out

    # 소수 층수(3.5) 거부
    out = extract_h01_fields([{"mainAtchGbCdNm": "주건축물", "grndFlrCnt": 3.5, "heit": "10.0"}])
    assert "floor_count" not in out

    # 정수형 float(3.0) → 허용 (3으로 변환)
    out = extract_h01_fields([{"mainAtchGbCdNm": "주건축물", "grndFlrCnt": 3.0, "heit": "10.0"}])
    assert out.get("floor_count") == 3

    # NaN float 높이 거부
    out = extract_h01_fields([{"mainAtchGbCdNm": "주건축물", "grndFlrCnt": "10", "heit": float("nan")}])
    assert "building_height" not in out

    # Infinity float 높이 거부
    out = extract_h01_fields([{"mainAtchGbCdNm": "주건축물", "grndFlrCnt": "10", "heit": float("inf")}])
    assert "building_height" not in out

    # bool 높이 거부
    out = extract_h01_fields([{"mainAtchGbCdNm": "주건축물", "grndFlrCnt": "5", "heit": True}])
    assert "building_height" not in out


# ── H33: ji 빈값 + existing_pk 있음 → ji=0000 fallback 성공 ─────────────────────

def test_H33_ji_fallback_permitted_with_existing_pk(monkeypatch):
    """PATCH A: existing_pk 제공 시 원본 ji 빈값이면 ji=0000 fallback 허용."""
    item_correct = {
        "mainAtchGbCdNm": "주건축물", "mgmBldrgstPk": "CORRECT-PK",
        "heit": "30.0", "grndFlrCnt": "10",
    }

    def fake_kr_get(url, params, timeout):
        ji = params.get("ji", "")
        if ji == "0001":
            return _make_response(0, None)  # 원본 ji 빈값
        return _make_response(1, [item_correct])  # ji=0000 에 유효 데이터

    monkeypatch.setattr(_hyd_mod, "kr_get", fake_kr_get)
    items = _hyd_mod.fetch_h01_title_for_bdmgtsn(_BDMGTSN_0001, existing_pk="CORRECT-PK")
    assert items is not None and len(items) == 1
    assert items[0]["mgmBldrgstPk"] == "CORRECT-PK"


# ── H34: ji 빈값 + existing_pk 없음 → fallback 금지 → None ──────────────────────

def test_H34_ji_fallback_blocked_without_existing_pk(monkeypatch):
    """PATCH A: existing_pk 없으면 원본 ji 빈값 시 fallback 금지 → None."""
    item = {
        "mainAtchGbCdNm": "주건축물", "mgmBldrgstPk": "SOME-PK",
        "heit": "30.0", "grndFlrCnt": "10",
    }

    def fake_kr_get(url, params, timeout):
        ji = params.get("ji", "")
        if ji == "0001":
            return _make_response(0, None)  # 원본 ji 빈값
        return _make_response(1, [item])

    monkeypatch.setattr(_hyd_mod, "kr_get", fake_kr_get)
    # existing_pk 미제공 → fallback 금지
    result = _hyd_mod.fetch_h01_title_for_bdmgtsn(_BDMGTSN_0001)
    assert result is None


# ── H35: 과수집 (rows > expected_total) → None ──────────────────────────────────

def test_H35_over_collection_rejected(monkeypatch):
    """PATCH D: 페이지에서 totalCount보다 많은 행 수집 → 정합성 실패 → None."""
    item = {"mainAtchGbCdNm": "주건축물", "heit": "10.0"}

    def fake_kr_get(url, params, timeout):
        # totalCount=1 이지만 페이지당 3개 반환 → 과수집
        return _make_response(1, [item, item, item])

    monkeypatch.setattr(_hyd_mod, "kr_get", fake_kr_get)
    result = _hyd_mod.fetch_h01_title_for_bdmgtsn("1168010100107190000")
    assert result is None


# ── H36: hydrate_factory_h01 — existing_mgm_pk → fetch 에 전달 확인 ──────────────

def test_H36_hydrate_passes_existing_pk_to_fetch(monkeypatch):
    """PATCH A: hydrate_factory_h01 이 factory의 mgm_bldrgst_pk 를 fetch 에 전달."""
    import services.time as _time_svc
    monkeypatch.setattr(_time_svc, "now_kst", lambda: "2026-10-15")
    monkeypatch.setattr(_time_svc, "serialize_business_datetime", lambda x: "TS-MOCK")

    captured_pk = {}

    def fake_fetch(bdmgtsn, existing_pk=None):
        captured_pk["pk"] = existing_pk
        return [{"mainAtchGbCdNm": "주건축물", "mgmBldrgstPk": _PK_A, "heit": "20.0", "grndFlrCnt": "5"}]

    monkeypatch.setattr(_hyd_mod, "fetch_h01_title_for_bdmgtsn", fake_fetch)

    fac = {"bdmgtsn": "1168010100107190000", "mgm_bldrgst_pk": _PK_A}
    sb = _TrackingSB(fac)
    from services.building_register_hydration import hydrate_factory_h01
    result = hydrate_factory_h01(sb, "F1")
    assert result.get("updated") is True
    assert captured_pk["pk"] == _PK_A


# ── H37: C3 build_facility() — H01 수치가 LEG facility 에 실제 도달 확인 ─────────

def test_H37_c3_build_facility_h01_fields_delivered(monkeypatch):
    """PATCH C: run_safe_building_leg 이 생성한 step1 에 build_facility() 를 실제 호출해
    floor_count + building_height_m 가 LEG facility 에 포함됨을 검증."""
    from clients.leg_runtime_client import build_facility
    import services.building_floor_hydration as _flr_mod

    cap = {}
    _patch_leg(monkeypatch, cap)
    _no_hydrate(monkeypatch)
    monkeypatch.setattr(_flr_mod, "resolve_floor_area_sum_11f_plus",
                        lambda bdmgtsn, pk: {"resolved": False})

    fac = {
        "floor_count": 15, "has_boiler": False, "is_multi_use": False,
        "building_height": 55.0,
        "building_register_updated_at": "2026-01-01T00:00:00+09:00",
        "bdmgtsn": "1168010100107190000",
        "mgm_bldrgst_pk": _PK_A,
    }
    run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())

    facility = build_facility(cap["step1"])
    assert facility.get("floor_count") == 15
    assert facility.get("building_height_m") == 55.0


# ── H38: PATCH B — ts+values 있지만 mgm_bldrgst_pk 없음 → 수화 트리거 ───────────

def test_H38_patch_b_missing_pk_triggers_hydration(monkeypatch):
    """PATCH B: building_register_updated_at + 수치 있어도 mgm_bldrgst_pk 없으면
    authoritative 아님 → hydration 재시도. 재시도 실패 시 미인증 캐시 수치가 C3에 없음."""
    cap = {}
    _patch_leg(monkeypatch, cap)
    called = {"n": 0}

    def fake_hyd(sb, fid):
        called["n"] += 1
        return {"updated": False, "reason": "mock"}

    monkeypatch.setattr(_hyd_mod, "hydrate_factory_h01", fake_hyd)

    fac = {
        "floor_count": 10, "has_boiler": False, "is_multi_use": False,
        "building_height": 42.5,
        "building_register_updated_at": "2026-01-01T00:00:00+09:00",
        # mgm_bldrgst_pk 없음
    }
    out = run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())
    assert called["n"] == 1  # PATCH B: pk 없으면 캐시 수치도 재인증 필요
    # 미인증 캐시 수치가 C3에 주입되지 않아야 한다
    assert "building_height_m" not in cap["step1"].input
    assert "floor_count" not in cap["step1"].input
    assert "floor_count" in out["unresolved_fields"]


# ── H39: PATCH B — ts+values+mgm_bldrgst_pk 있음 → authoritative, 수화 없음 ────

def test_H39_patch_b_with_pk_no_hydration(monkeypatch):
    """PATCH B: building_register_updated_at + 수치 + mgm_bldrgst_pk 모두 있으면
    authoritative → hydration 재시도 없음."""
    cap = {}
    _patch_leg(monkeypatch, cap)
    called = _no_hydrate(monkeypatch)

    fac = {
        "floor_count": 10, "has_boiler": False, "is_multi_use": False,
        "building_height": 42.5,
        "building_register_updated_at": "2026-01-01T00:00:00+09:00",
        "mgm_bldrgst_pk": _PK_A,
    }
    out = run_safe_building_leg(_FakeSB(fac), "F1", SafeBuildingConsumerInput())
    assert called["n"] == 0
    assert cap["step1"].input.get("building_height_m") == 42.5
    assert cap["step1"].input.get("floor_count") == 10
    assert "floor_count" not in out["unresolved_fields"]


# ── H40: 다음 페이지에 동일 PK 반복 → 정합성 실패 → None ───────────────────────

def test_H40_duplicate_pk_across_pages_rejected(monkeypatch):
    """FINAL GUARD: totalCount 충족이라도 동일 mgmBldrgstPk 반복 → None."""
    item = {
        "mainAtchGbCdNm": "주건축물", "mgmBldrgstPk": _PK_A,
        "heit": "45.0", "grndFlrCnt": "12",
    }

    def fake_kr_get(url, params, timeout):
        # totalCount=2, 하지만 두 페이지 모두 동일 PK_A 행 반환
        return _make_response(2, [item])

    monkeypatch.setattr(_hyd_mod, "kr_get", fake_kr_get)
    result = _hyd_mod.fetch_h01_title_for_bdmgtsn("1168010100107190000")
    assert result is None


# ── H41: 서로 다른 PK 복수 페이지 정상 수집 → 기존 PK 기준 선택 유지 ─────────────

def test_H41_distinct_pk_multipage_normal_collection(monkeypatch):
    """FINAL GUARD 회귀: 서로 다른 mgmBldrgstPk 행은 정상 수집 후 existing_pk 선택."""
    item_a = {
        "mainAtchGbCdNm": "주건축물", "mgmBldrgstPk": _PK_A,
        "heit": "45.0", "grndFlrCnt": "12",
    }
    item_b = {
        "mainAtchGbCdNm": "주건축물", "mgmBldrgstPk": _PK_B,
        "heit": "20.0", "grndFlrCnt": "5",
    }

    def fake_kr_get(url, params, timeout):
        page = params.get("pageNo", 1)
        body_item = item_a if page == 1 else item_b
        return _make_response(2, [body_item])

    monkeypatch.setattr(_hyd_mod, "kr_get", fake_kr_get)
    items = _hyd_mod.fetch_h01_title_for_bdmgtsn("1168010100107190000")
    assert items is not None and len(items) == 2

    # existing_pk=_PK_A → item_a 선택
    out = extract_h01_fields(items, existing_pk=_PK_A)
    assert out.get("building_height") == 45.0
    assert out.get("floor_count") == 12
    assert out.get("mgm_bldrgst_pk") == _PK_A
