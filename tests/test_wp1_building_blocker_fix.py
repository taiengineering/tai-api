"""WP-1 BLOCKER-FIX — BUILDING default overwrite 제거 검증 (B1/B2/B3/B5)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from clients.leg_runtime_client import build_facility


class _Body:
    def __init__(self, sector="BUILDING", input=None, **kw):
        self.sector = sector
        self.input = input or {}
        for k, v in kw.items():
            setattr(self, k, v)
    def __getattr__(self, name):
        return None


def test_B1_building_use_type_from_input_not_default():
    fac = build_facility(_Body(input={"building_use_type": "오피스텔"}))
    assert fac.get("building_use_type") == "오피스텔"

def test_B2_floor_count_from_input_not_default():
    fac = build_facility(_Body(input={"floor_count": 30}))
    assert fac.get("floor_count") == 30

def test_B3_total_floor_area_from_input_not_default():
    fac = build_facility(_Body(input={"total_floor_area": 300.0}))
    assert fac.get("total_floor_area") == 300.0

def test_no_default_invention_when_absent():
    fac = build_facility(_Body(input={"worker_count": 10}))
    assert "building_use_type" not in fac
    assert "floor_count" not in fac
    assert "total_floor_area" not in fac

def test_B5_elevator_derivation():
    fac = build_facility(_Body(input={}, elevator_count=3))
    assert fac.get("has_building_elevator") is True

def test_B5_elevator_zero_no_derivation():
    fac = build_facility(_Body(input={}, elevator_count=0))
    assert "has_building_elevator" not in fac

def test_false_zero_preserved():
    fac = build_facility(_Body(input={"has_flat_plate_structure": False, "column_span_m": 0}))
    assert fac.get("has_flat_plate_structure") is False
    assert fac.get("column_span_m") == 0

def test_n1_user_value_reaches_facility():
    fac = build_facility(_Body(input={"building_height_m": 250.0, "is_collapse_risk_land": True}))
    assert fac.get("building_height_m") == 250.0
    assert fac.get("is_collapse_risk_land") is True
