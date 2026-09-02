"""WO-DUAL-IND-STEP2 GATE-2 Path A — WWW INDUSTRIAL Canonical adapter + Runtime input + W1/W2 tests.

CORRECTION-02:
  - SAFE assembler 부재 검증을 substring → AST(import/call node) 기반으로 교체(정상 docstring 보존).
  - LEG EXPECTED 14/14 exact-value 완전 검증(building_use_type 포함, denominator len==14).
"""
import ast
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


# ---- CORRECTION-02 P1/P2: SAFE assembler 실제 import/call 부재 (AST 기반, docstring 무관) ----
def test_no_safe_assembler_import_or_call():
    import services.canonical.industrial_www as mod
    tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
    imported_names = set()
    called_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for n in node.names:
                imported_names.add(n.name)
        elif isinstance(node, ast.Import):
            for n in node.names:
                imported_names.add(n.name.split(".")[0])
        elif isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                called_names.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                called_names.add(fn.attr)
    # SAFE asset assembler 함수는 import 되지도, 호출되지도 않는다(실행 코드 기준). docstring 언급은 무관.
    assert "assemble_industrial_marketing_contract" not in imported_names
    assert "assemble_industrial_marketing_contract" not in called_names
    # frozen denominator(TARGET_FIELDS) 재사용은 허용 — import 되어 있어야 한다.
    assert "TARGET_FIELDS" in imported_names


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


# ---- CORRECTION-02 P3: LEG EXPECTED 14/14 exact-value (building_use_type 포함, denominator 명시) ----
def test_leg_expected_14_exact_value():
    fd = {
        "ksic_major": "C25", "worker_count": 7, "total_floor_area": 5000, "building_use_type": "공장",
        "has_safety_manager": True, "has_boiler": False, "has_chemical_substance": True,
        "has_high_pressure_gas": True, "gas_capacity_kg": 120, "work_height_m": 3.5,
        "has_truck_loading_unloading": True, "truck_loading_height_m": 2.0,
        "has_manual_heavy_handling": True, "manual_handling_weight_kg": 25,
        # transport-only(비LEG)도 함껸 넣어 facility 미포함 확인
        "address": "서울", "floor_count": 3, "process_list": [{"process_name": "x"}],
    }
    facility = leg.build_facility(build_industrial_www_step1(_Body(form_data=fd)))

    # LEG EXPECTED 14 — consumer has_chemical_substance 는 승인 alias 로 LEG has_chemical 로 도달.
    expected_facility = {
        "ksic_major": "C25",
        "worker_count": 7,
        "total_floor_area": 5000,
        "building_use_type": "공장",
        "has_safety_manager": True,
        "has_boiler": False,
        "has_chemical": True,
        "has_high_pressure_gas": True,
        "gas_capacity_kg": 120,
        "work_height_m": 3.5,
        "has_truck_loading_unloading": True,
        "truck_loading_height_m": 2.0,
        "has_manual_heavy_handling": True,
        "manual_handling_weight_kg": 25,
    }
    assert len(expected_facility) == 14
    for key, value in expected_facility.items():
        assert facility[key] == value, f"{key}: expected {value!r}, got {facility.get(key)!r}"

    # consumer 원명(has_chemical_substance) 및 transport-only 는 facility 미포함
    for k in ("has_chemical_substance", "address", "floor_count", "process_list"):
        assert k not in facility
