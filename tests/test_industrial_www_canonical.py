"""WO-DUAL-IND-STEP2 GATE-2 Path A — WWW INDUSTRIAL Canonical adapter + Runtime input + W1/W2 tests."""
import pytest
from services.canonical.industrial_www import (
    build_industrial_www_canonical, build_industrial_www_step1, SECTOR,
)
from services.safe_industrial_canonical_assembler import TARGET_FIELDS
from schemas.legal_engine import DiagnoseStep1Body
from clients import leg_runtime_client as leg


class _Body:
    """run_diagnosis body 대역(form_data + factory_id 만 사용)."""
    def __init__(self, form_data=None, factory_id=None):
        self.form_data = form_data
        self.factory_id = factory_id


# ---- Canonical adapter ----
def test_canonical_denominator_29():
    c = build_industrial_www_canonical({})
    assert list(c.keys()) == TARGET_FIELDS and len(c) == 29

def test_canonical_absent_is_none():
    c = build_industrial_www_canonical({"worker_count": 5})
    assert c["worker_count"] == 5
    assert c["total_floor_area"] is None and c["has_chemical_substance"] is None

def test_canonical_present_verbatim():
    c = build_industrial_www_canonical({"total_floor_area": 5000, "ksic_major": "C25"})
    assert c["total_floor_area"] == 5000 and c["ksic_major"] == "C25"

def test_canonical_false_zero_empty_preserved():
    c = build_industrial_www_canonical({"has_boiler": False, "work_height_m": 0,
                                        "manual_handling_weight_kg": 0.0, "business_activity_types": []})
    assert c["has_boiler"] is False and c["work_height_m"] == 0
    assert c["manual_handling_weight_kg"] == 0.0 and c["business_activity_types"] == []

def test_canonical_no_default_400_or_fabrication():
    c = build_industrial_www_canonical({})
    assert c["total_floor_area"] is None and c["has_boiler"] is None and c["business_activity_types"] is None

def test_canonical_no_extra_keys():
    c = build_industrial_www_canonical({"garbage": 1, "worker_count": 3})
    assert set(c.keys()) == set(TARGET_FIELDS) and "garbage" not in c

def test_canonical_no_safe_assembler_call():
    import services.canonical.industrial_www as mod
    src = open(mod.__file__).read()
    assert "assemble_industrial_marketing_contract" not in src


# ---- P2-02 official runtime input ----
def test_P2_02_official_step1_type_and_sector():
    s = build_industrial_www_step1(_Body(form_data={"worker_count": 7}))
    assert isinstance(s, DiagnoseStep1Body)
    assert s.sector == "INDUSTRIAL" == SECTOR


# ---- P2-03 no top-level shadow (W1) ----
def test_P2_03_no_top_level_shadow_total_floor_area():
    s = build_industrial_www_step1(_Body(form_data={"total_floor_area": 5000}))
    assert s.total_floor_area is None
    assert s.input["total_floor_area"] == 5000
    fac = leg.build_facility(s)
    assert fac["total_floor_area"] == 5000 and fac["total_floor_area"] != 400


# ---- P2-04 chemical (W2) ----
def test_P2_04_chemical_alias():
    s = build_industrial_www_step1(_Body(form_data={"has_chemical_substance": True}))
    assert s.has_chemical_substance is None
    assert s.input["has_chemical_substance"] is True
    fac = leg.build_facility(s)
    assert fac.get("has_chemical") is True
    assert "has_chemical_substance" not in fac


# ---- 14 LEG-EXPECTED exact-value at facility + transport-only excluded ----
def test_leg_expected_14_exact_value():
    fd = {
        "ksic_major": "C25", "worker_count": 7, "total_floor_area": 5000, "building_use_type": "\uacf5\uc7a5",
        "has_safety_manager": True, "has_boiler": False, "has_chemical_substance": True,
        "has_high_pressure_gas": True, "gas_capacity_kg": 120, "work_height_m": 3.5,
        "has_truck_loading_unloading": True, "truck_loading_height_m": 2.0,
        "has_manual_heavy_handling": True, "manual_handling_weight_kg": 25,
        "address": "\uc11c\uc6b8", "floor_count": 3, "process_list": [{"process_name": "x"}],
    }
    fac = leg.build_facility(build_industrial_www_step1(_Body(form_data=fd)))
    assert fac["total_floor_area"] == 5000 and fac["worker_count"] == 7 and fac["ksic_major"] == "C25"
    assert fac["has_safety_manager"] is True and fac["has_boiler"] is False and fac.get("has_chemical") is True
    assert fac["has_high_pressure_gas"] is True and fac["gas_capacity_kg"] == 120
    assert fac["work_height_m"] == 3.5 and fac["has_truck_loading_unloading"] is True
    assert fac["truck_loading_height_m"] == 2.0 and fac["has_manual_heavy_handling"] is True
    assert fac["manual_handling_weight_kg"] == 25
    for k in ("address", "floor_count", "process_list"):
        assert k not in fac
