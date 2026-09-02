"""WO-BLD-MKT-CONSUMER-INPUT-WIRING-016 STEP-2: build_facility BUILDING N1 33 primitive wiring."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from clients.leg_runtime_client import build_facility, _LEG_INPUT_FIELDS, _BUILDING_N1_FIELDS

BLD33=["floor_count","building_height_m","floor_area_sum_at_or_above_11f","performance_use_floor_area_sum",
 "cantilever_projection_m","column_span_m","flat_plate_column_section_ratio","occupancy_capacity",
 "underground_connection_entrance_distance_m","connection_open_space_floor_area_m2",
 "connection_open_space_open_area_ratio","stair_or_ramp_effective_width_m",
 "building_use_type","building_activity_type","building_use_category",
 "has_performance_assembly_use","is_target_facility_in_basement","has_gas_boiler_heating_system",
 "has_centralized_gas_supply","is_collapse_risk_land","has_land_preparation","has_building_construction_activity",
 "has_wet_land","has_water_seepage_risk","has_landfill_or_similar_ground","has_flat_plate_structure",
 "authority_designated_special_structure","article32_3_alternative_confirmation_subject",
 "has_wall_between_connection_entrances","wall_between_connection_entrances_is_fire_resistant",
 "has_stair_or_ramp_in_open_space","is_connected_to_subway_or_underground_mall","has_hazardous_material_in_out_event"]

class Body:
    """DiagnoseStep1Body 최소 모형: sector + input dict (top-level 속성 없음, input 통로 검증)."""
    def __init__(self, sector="BUILDING", **kw):
        self.sector=sector; self.input=kw.get("input",{})
        for k,v in kw.items():
            if k!="input": setattr(self,k,v)

def _sample_input():
    d={}
    NUM={"floor_count":11,"building_height_m":120.0,"floor_area_sum_at_or_above_11f":10000.0,
         "performance_use_floor_area_sum":3000.0,"cantilever_projection_m":3.0,"column_span_m":20.0,
         "flat_plate_column_section_ratio":0.25,"occupancy_capacity":5000,
         "underground_connection_entrance_distance_m":10.0,"connection_open_space_floor_area_m2":180.0,
         "connection_open_space_open_area_ratio":0.5,"stair_or_ramp_effective_width_m":1.8}
    ENUM={"building_use_type":"오피스텔","building_activity_type":"건축","building_use_category":"RETAIL"}
    BOOL=["has_performance_assembly_use","is_target_facility_in_basement","has_gas_boiler_heating_system",
     "has_centralized_gas_supply","is_collapse_risk_land","has_land_preparation","has_building_construction_activity",
     "has_wet_land","has_water_seepage_risk","has_landfill_or_similar_ground","has_flat_plate_structure",
     "authority_designated_special_structure","article32_3_alternative_confirmation_subject",
     "has_wall_between_connection_entrances","wall_between_connection_entrances_is_fire_resistant",
     "has_stair_or_ramp_in_open_space","is_connected_to_subway_or_underground_mall","has_hazardous_material_in_out_event"]
    d.update(NUM); d.update(ENUM)
    for b in BOOL: d[b]=True
    return d

def test_all_33_registered():
    for c in BLD33: assert c in _LEG_INPUT_FIELDS, c

def test_build_facility_33_exact():
    fac=build_facility(Body(sector="BUILDING", input=_sample_input()))
    for c in BLD33: assert c in fac, ("missing",c)
    # BUILDING N1 33 중 누락 0, 값 그대로
    got={c:fac[c] for c in BLD33}
    assert got["building_use_type"]=="오피스텔"
    assert got["building_activity_type"]=="건축" and got["building_use_category"]=="RETAIL"
    assert got["floor_count"]==11 and got["flat_plate_column_section_ratio"]==0.25

def test_false_and_zero_preserved():
    inp={"has_flat_plate_structure":False,"occupancy_capacity":0,"connection_open_space_open_area_ratio":0.0}
    fac=build_facility(Body(sector="BUILDING", input=inp))
    assert fac.get("has_flat_plate_structure") is False   # False 보존
    assert fac.get("occupancy_capacity")==0                # 0 보존
    assert fac.get("connection_open_space_open_area_ratio")==0.0

def test_none_and_blank_omitted():
    inp={"has_wet_land":None,"building_activity_type":"","column_span_m":None}
    fac=build_facility(Body(sector="BUILDING", input=inp))
    assert "has_wet_land" not in fac and "building_activity_type" not in fac and "column_span_m" not in fac

def test_no_proxy():
    # 기존 넓은 값만 줘도 신규 specific BUILDING N1 field 생성 금지
    inp={"has_boiler":True,"has_gas":True,"has_hazmat_storage":True}
    fac=build_facility(Body(sector="BUILDING", input=inp))
    assert "has_gas_boiler_heating_system" not in fac
    assert "has_centralized_gas_supply" not in fac
    assert "has_hazardous_material_in_out_event" not in fac

def test_building_use_type_officetel_exact():
    fac=build_facility(Body(sector="BUILDING", input={"building_use_type":"오피스텔"}))
    assert fac["building_use_type"]=="오피스텔"

def test_ratio_passthrough_no_conversion():
    # ratio 0~1 그대로(퍼센트 변환 없음)
    fac=build_facility(Body(sector="BUILDING", input={"connection_open_space_open_area_ratio":0.5,"flat_plate_column_section_ratio":0.25}))
    assert fac["connection_open_space_open_area_ratio"]==0.5 and fac["flat_plate_column_section_ratio"]==0.25


# ── WO-FIX-BUILDFACILITY-SECTOR-GATE-001 / POST-MERGE TEST-LOCK ─────────────
# BUILDING N1 32축 sector-firewall regression-lock.
#   build_facility 의 gate: `code in _BUILDING_N1_FIELDS and sector != "BUILDING" -> continue`.
#   denominator 는 production frozenset(_BUILDING_N1_FIELDS) 자체 → hardcode drift 차단.
#   building_use_type 은 32축 밖(base 공용)이라 별도 보존 검증.

_N1 = sorted(_BUILDING_N1_FIELDS)


def test_lock_denominator_is_exactly_32():
    # exact 32 — 축이 늘거나 줄면 이 lock 이 즉시 실패해야 한다.
    assert len(_BUILDING_N1_FIELDS) == 32, len(_BUILDING_N1_FIELDS)
    # building_use_type 은 N1 gate 대상이 아니다(base 56 공용).
    assert "building_use_type" not in _BUILDING_N1_FIELDS


def _n1_full_input():
    """32축 전부에 non-None 값을 채운 input(값 종류 무관 — 통과 여부만 본다)."""
    d = {}
    for c in _N1:
        # bool/num/str 무관하게 truthy non-empty 값이면 build_facility 통과 대상
        d[c] = 1 if c.startswith(("floor", "building_height", "occupancy")) else True
    # enum 계열은 문자열로(빈문자 배제)
    d["building_activity_type"] = "건축"
    d["building_use_category"] = "RETAIL"
    return d


def _blocked_count(sector):
    """sector 에서 32축 중 facility 에 실린 개수(0 이어야 blocked)."""
    fac = build_facility(Body(sector=sector, input=_n1_full_input()))
    return sum(1 for c in _N1 if c in fac)


def _allowed_count(sector):
    fac = build_facility(Body(sector=sector, input=_n1_full_input()))
    return sum(1 for c in _N1 if c in fac)


def test_lock_industrial_32_blocked():
    assert _blocked_count("INDUSTRIAL") == 0


def test_lock_manufacturing_32_blocked():
    assert _blocked_count("MANUFACTURING") == 0


def test_lock_construction_32_blocked():
    assert _blocked_count("CONSTRUCTION") == 0


def test_lock_special_facility_32_blocked():
    assert _blocked_count("SPECIAL_FACILITY") == 0


def test_lock_none_sector_32_blocked():
    # sector 미지정(None)도 BUILDING 이 아니므로 전부 차단.
    fac = build_facility(Body(sector=None, input=_n1_full_input()))
    assert sum(1 for c in _N1 if c in fac) == 0


def test_lock_building_32_allowed():
    # BUILDING sector 에서는 32축 전부 통과(gate 미적용).
    assert _allowed_count("BUILDING") == 32


def test_lock_building_use_type_preserved_all_sectors():
    # building_use_type 은 32축 gate 밖 → 모든 sector 에서 보존.
    for sector in ("BUILDING", "INDUSTRIAL", "MANUFACTURING", "CONSTRUCTION",
                   "SPECIAL_FACILITY", None):
        fac = build_facility(Body(sector=sector, input={"building_use_type": "오피스텔"}))
        assert fac.get("building_use_type") == "오피스텔", sector
