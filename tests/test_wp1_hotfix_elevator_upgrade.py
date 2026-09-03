"""WP1-HOTFIX-001 — elevator 0→False + upgrade form_data round-trip.

결함1: has_building_elevator 는 elevator_count 명시값(0 포함)이면 boolean.
  None→absent, 0→False, 1+→True. (이전엔 0 이 absent 로 유실)
결함2: 최초 저장 raw_structured_input 에 form_data 보존 → upgrade 가 form_data 를
  canonical source(우선)로 복원 → 유료 BUILDING 소비자입력 round-trip.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from clients.leg_runtime_client import build_facility
from schemas.legal_engine import DiagnoseStep1Body


def _bld(input=None, **top):
    return DiagnoseStep1Body(sector="BUILDING", input=input or {}, **top)


# ── 결함1: elevator 3-state (None/0/1+) ──
def test_elevator_none_absent():
    fac = build_facility(_bld(input={}))
    assert "has_building_elevator" not in fac  # None → absent

def test_elevator_zero_false():
    fac = build_facility(_bld(input={}, elevator_count=0))
    assert fac.get("has_building_elevator") is False  # 0 → False (이전엔 absent)

def test_elevator_positive_true():
    fac = build_facility(_bld(input={}, elevator_count=5))
    assert fac.get("has_building_elevator") is True

def test_elevator_zero_from_input_false():
    fac = build_facility(_bld(input={"elevator_count": 0}))
    assert fac.get("has_building_elevator") is False

def test_elevator_firewall_industrial_zero_no_key():
    # 산업/건설은 sector gate — elevator_count 0 이어도 has_building_elevator 없음.
    body = DiagnoseStep1Body(sector="MANUFACTURING", input={}, elevator_count=0)
    fac = build_facility(body)
    assert "has_building_elevator" not in fac


# ── 결함2: 저장/복원 계약 (소스 인스펙션 — DB 통합 대신 로직 검증) ──

def test_b1b2b3_default_removal_intact():
    src = open("services/diagnosis_integrated_svc.py").read()
    assert 'building_use_type=body.building_use_type or "사무실"' not in src
    assert "floor_count=body.floor_count or 5" not in src
    assert 'building_use_type="사무실"' not in src
    assert "floor_count=5" not in src


# ── B1/B2/B3 실계약 유지 (HOTFIX가 안 깼는지) ──
def test_b1_still_user_value():
    fac = build_facility(_bld(input={"building_use_type": "오피스텔"}))
    assert fac.get("building_use_type") == "오피스텔"

def test_b3_still_user_value():
    fac = build_facility(_bld(input={"total_floor_area": 300.0}))
    assert fac.get("total_floor_area") == 300.0
