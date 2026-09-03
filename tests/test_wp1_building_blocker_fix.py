"""WP-1 BLOCKER-FIX — BUILDING default overwrite 제거 검증 (B1/B2/B3/B5).

CORRECTION-01: mock 대역(_Body) 폐기. 실제 DiagnoseStep1Body(extra=forbid, Optional 필드)로
build_facility 실계약을 검증한다. WP-1 수정은 BUILDING 분기가 building_use_type/floor_count/
total_floor_area 를 top-level 미지정(=None) → build_facility 가 input(사용자 canonical)을 사용.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from clients.leg_runtime_client import build_facility
from schemas.legal_engine import DiagnoseStep1Body


def _bld(input=None, **top):
    # WP-1 후 BUILDING 분기가 실제로 만드는 형태를 재현: 실제 DiagnoseStep1Body.
    #   building_use_type/floor_count/total_floor_area 는 top-level 미지정(default None).
    return DiagnoseStep1Body(sector="BUILDING", input=input or {}, **top)


# ── B1/B2/B3: top-level 미지정 → build_facility 가 input(사용자값) 사용 ──
def test_B1_building_use_type_from_input_not_default():
    fac = build_facility(_bld(input={"building_use_type": "오피스텔"}))
    assert fac.get("building_use_type") == "오피스텔"  # NOT '사무실'

def test_B2_floor_count_from_input_not_default():
    fac = build_facility(_bld(input={"floor_count": 30}))
    assert fac.get("floor_count") == 30  # NOT 5

def test_B3_total_floor_area_from_input_not_default():
    fac = build_facility(_bld(input={"total_floor_area": 300.0}))
    assert fac.get("total_floor_area") == 300.0  # NOT 400

def test_no_default_invention_when_absent():
    # 사용자 미입력(input 없음) + top-level 미지정 → facility 미포함(발명 금지).
    fac = build_facility(_bld(input={"worker_count": 10}))
    assert "building_use_type" not in fac
    assert "floor_count" not in fac
    assert "total_floor_area" not in fac

def test_top_level_none_does_not_override_input():
    # 실계약: DiagnoseStep1Body(building_use_type=None) + input 값 → input 이 이김.
    #   (WP-1 이전엔 top-level '사무실' 이 input 을 덮었음)
    body = DiagnoseStep1Body(sector="BUILDING", building_use_type=None,
                             floor_count=None, total_floor_area=None,
                             input={"building_use_type": "공동주택", "floor_count": 15,
                                    "total_floor_area": 250.0})
    fac = build_facility(body)
    assert fac.get("building_use_type") == "공동주택"
    assert fac.get("floor_count") == 15
    assert fac.get("total_floor_area") == 250.0


# ── B5: elevator_count>0 → has_building_elevator 파생 (BUILDING만) ──
def test_B5_elevator_derivation_building():
    fac = build_facility(_bld(input={}, elevator_count=3))
    assert fac.get("has_building_elevator") is True

def test_B5_elevator_zero_no_derivation():
    fac = build_facility(_bld(input={}, elevator_count=0))
    assert "has_building_elevator" not in fac

def test_B5_elevator_from_input():
    # elevator_count 가 input(rsi) 에 있을 때도 파생(build_facility 폴백).
    fac = build_facility(_bld(input={"elevator_count": 2}))
    assert fac.get("has_building_elevator") is True


# ── B5 FIREWALL: INDUSTRIAL/CONSTRUCTION 은 has_building_elevator 미파생 ──
def test_B5_firewall_industrial_no_building_elevator():
    body = DiagnoseStep1Body(sector="MANUFACTURING", input={"elevator_count": 5}, elevator_count=5)
    fac = build_facility(body)
    assert "has_building_elevator" not in fac  # BUILDING gate — 산업 오염 금지

def test_B5_firewall_construction_no_building_elevator():
    body = DiagnoseStep1Body(sector="CONSTRUCTION", input={"elevator_count": 5}, elevator_count=5)
    fac = build_facility(body)
    assert "has_building_elevator" not in fac


# ── false/0 보존 + N1 도달 (실계약) ──
def test_false_zero_preserved():
    fac = build_facility(_bld(input={"has_flat_plate_structure": False, "column_span_m": 0}))
    assert fac.get("has_flat_plate_structure") is False
    assert fac.get("column_span_m") == 0

def test_n1_user_value_reaches_facility():
    fac = build_facility(_bld(input={"building_height_m": 250.0, "is_collapse_risk_land": True}))
    assert fac.get("building_height_m") == 250.0
    assert fac.get("is_collapse_risk_land") is True
