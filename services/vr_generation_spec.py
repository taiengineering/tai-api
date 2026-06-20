"""VR generation_spec — 가상 사업장 입력 생성기

WO-VR-GENERATION-SPEC-EXPANSION-001-REBASE

목적:
  FacilityProfile v2(57차원)와 1:1 정합되는 가상 사업장 입력 dict 생성.
  build_virtual_facility_profile(spec) → factories row 형태 dict
  (이 dict를 facility_profile_service.build_facility_profile에 그대로 투입 가능)

엄격 원칙:
  실제 판정을 추론하지 않는다. 법령 조건을 반영하지 않는다.
  현실적 값 범위만 사용. UNKNOWN(None) 허용. False는 False 유지.
  0을 UNKNOWN으로 바꾸지 않는다.
  생성만 한다 — 판정 실행/V4/condition/FacilityProfile/UI 수정 없음.

  일반 공정(process_lv*)과 건설 공정(construction_process_*)은 분리한다.
  일반 작업과 건설 작업(construction_work_*)은 분리한다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import uuid


# ---------------------------------------------------------------------------
# FacilityProfile v2 전체 입력 키 (factories row 키 기준)
# build_facility_profile가 row.get(...)로 읽는 원본 키와 1:1 대응
# ---------------------------------------------------------------------------

ALL_PROFILE_INPUT_KEYS: List[str] = [
    # 1. 기본 사업장
    "sector", "ksic_code",
    "employee_count", "subcontractor_worker_count", "total_worker_count_calc",
    # 2. 건축물
    "building_use_code", "building_area", "floor_count", "building_grade",
    # 3. 시설 에너지
    "electrical_capacity_kw", "gas_capacity_m3", "gas_capacity_kg",
    "annual_energy_toe", "transformer_kva",
    # 4. 시설 설비
    "boiler_capacity", "elevator_count",
    # 5. 위험속성
    "has_hazardous_material", "has_chemical_material", "has_high_pressure_gas",
    "has_safety_manager", "is_factory_registered", "is_public_facility",
    # 6. 건설
    "construction_amount", "construction_type", "subcontractor_company_count",
    "has_tower_crane", "has_confined_space", "has_asbestos",
    "has_blasting", "has_diving_work",
    # 7. 일반 공정
    "process_lv1", "process_lv2", "process_lv3", "process_lv4",
    # 8. 설비
    "equipment_count", "equipment_names", "equipment_install_years",
    "equipment_locations", "equipment_legal_targets", "equipment_operation_status",
    # 9. 건설 공정
    "construction_process_code", "construction_process_name",
    "construction_process_standard_version",
    # 10. 건설 작업
    "construction_work_code", "construction_work_name",
    "construction_work_standard_version", "construction_work_amount",
    "construction_work_duration_days", "construction_work_worker_count",
    "has_excavation_work", "has_high_place_work", "has_lifting_work",
    "has_demolition_work", "has_scaffold_work", "has_formwork_work",
    "has_welding_work", "has_electrical_work", "has_hot_work",
]


def _empty_row() -> Dict[str, Any]:
    """모든 입력 키를 None(UNKNOWN)으로 초기화한 row.

    None = UNKNOWN. 생성기가 채우지 않은 키는 UNKNOWN으로 남는다.
    """
    return {k: None for k in ALL_PROFILE_INPUT_KEYS}


# ---------------------------------------------------------------------------
# 프로파일별 생성 함수 (현실적 값 범위만. 판정 추론 없음)
# ---------------------------------------------------------------------------

def _profile_manufacturing_standard(row: Dict[str, Any], spec: dict) -> None:
    """제조업 표준 사업장.

    공정/설비/전기/가스/보일러 일부 포함.
    건설 필드는 UNKNOWN(None) 유지.
    """
    row["sector"] = spec.get("sector", "INDUSTRIAL")
    row["ksic_code"] = spec.get("ksic_code", "C28")
    # 인력
    row["employee_count"] = 280
    row["subcontractor_worker_count"] = 40
    row["total_worker_count_calc"] = 320
    # 건축물
    row["building_use_code"] = "공장"
    row["building_area"] = 5000
    row["floor_count"] = 3
    row["building_grade"] = "일반"
    # 시설 에너지
    row["electrical_capacity_kw"] = 1500
    row["gas_capacity_m3"] = 200
    row["annual_energy_toe"] = 1800
    row["transformer_kva"] = 1000
    # 시설 설비
    row["boiler_capacity"] = 10
    row["elevator_count"] = 2
    # 위험속성 (False는 False 유지)
    row["has_hazardous_material"] = True
    row["has_chemical_material"] = True
    row["has_high_pressure_gas"] = False
    row["has_safety_manager"] = True
    row["is_factory_registered"] = True
    row["is_public_facility"] = False
    # 일반 공정 (건설 공정과 분리)
    row["process_lv1"] = "금속가공"
    row["process_lv2"] = "용접"
    row["process_lv3"] = "아크용접"
    row["process_lv4"] = None  # UNKNOWN 허용
    # 설비
    row["equipment_count"] = 12
    row["equipment_names"] = ["프레스", "컨베이어", "용접기"]
    row["equipment_install_years"] = [2018, 2020, 2021]
    row["equipment_locations"] = ["1층 가공동", "1층 가공동", "2층 조립동"]
    row["equipment_legal_targets"] = [True, False, True]
    row["equipment_operation_status"] = ["ACTIVE", "ACTIVE", "ACTIVE"]
    # 건설 필드는 건드리지 않음 → None(UNKNOWN) 유지


def _profile_construction_standard(row: Dict[str, Any], spec: dict) -> None:
    """건설업 표준 사업장.

    construction_process / construction_work 포함.
    일반 process와 혼합 금지 (process_lv*는 None 유지).
    """
    row["sector"] = spec.get("sector", "CONSTRUCTION")
    row["ksic_code"] = spec.get("ksic_code", "F41")
    # 인력
    row["employee_count"] = 150
    row["subcontractor_worker_count"] = 200
    row["total_worker_count_calc"] = 350
    # 건축물 (건설 현장도 일부 보유)
    row["building_use_code"] = None
    row["building_area"] = None
    row["floor_count"] = None
    row["building_grade"] = None
    # 건설
    row["construction_amount"] = 50_000_000_000  # 500억
    row["construction_type"] = "건축"
    row["subcontractor_company_count"] = 5
    row["has_tower_crane"] = True
    row["has_confined_space"] = True
    row["has_asbestos"] = False
    row["has_blasting"] = False
    row["has_diving_work"] = False
    # 위험속성 일부
    row["has_safety_manager"] = True
    row["is_factory_registered"] = False
    row["is_public_facility"] = False
    # 일반 공정은 혼합 금지 → None(UNKNOWN) 유지 (명시적으로 비움)
    row["process_lv1"] = None
    row["process_lv2"] = None
    row["process_lv3"] = None
    row["process_lv4"] = None
    # 건설 공정 (일반 process와 분리)
    row["construction_process_code"] = "CP-100"
    row["construction_process_name"] = "토공사"
    row["construction_process_standard_version"] = "v2.1"
    # 건설 작업
    row["construction_work_code"] = "CW-210"
    row["construction_work_name"] = "굴착작업"
    row["construction_work_standard_version"] = "v2.1"
    row["construction_work_amount"] = 5_000_000_000
    row["construction_work_duration_days"] = 120
    row["construction_work_worker_count"] = 30
    row["has_excavation_work"] = True
    row["has_high_place_work"] = True
    row["has_lifting_work"] = True
    row["has_demolition_work"] = False
    row["has_scaffold_work"] = True
    row["has_formwork_work"] = True
    row["has_welding_work"] = True
    row["has_electrical_work"] = True
    row["has_hot_work"] = False
    # 설비 (건설 장비)
    row["equipment_count"] = 6
    row["equipment_names"] = ["타워크레인", "굴착기", "콘크리트펌프"]
    row["equipment_install_years"] = [2022, 2021, 2023]
    row["equipment_locations"] = ["현장A", "현장A", "현장B"]
    row["equipment_legal_targets"] = [True, True, False]
    row["equipment_operation_status"] = ["ACTIVE", "ACTIVE", "INACTIVE"]


def _profile_low_risk_office(row: Dict[str, Any], spec: dict) -> None:
    """저위험 사무형 사업장.

    설비/위험속성 최소. 대부분 UNKNOWN 또는 최소값.
    """
    row["sector"] = spec.get("sector", "INDUSTRIAL")
    row["ksic_code"] = spec.get("ksic_code", "J58")
    # 인력
    row["employee_count"] = 30
    row["subcontractor_worker_count"] = 0
    row["total_worker_count_calc"] = 30
    # 건축물 (사무용)
    row["building_use_code"] = "업무시설"
    row["building_area"] = 800
    row["floor_count"] = 5
    row["building_grade"] = "일반"
    # 시설 에너지 (최소, 일부만)
    row["electrical_capacity_kw"] = 50
    row["annual_energy_toe"] = 30
    # 시설 설비
    row["elevator_count"] = 1
    # 위험속성 (전부 False 또는 최소 — 0/False 유지)
    row["has_hazardous_material"] = False
    row["has_chemical_material"] = False
    row["has_high_pressure_gas"] = False
    row["has_safety_manager"] = False
    row["is_factory_registered"] = False
    row["is_public_facility"] = False
    # 공정/설비/건설 = 대부분 UNKNOWN 유지 (사무형이라 최소)
    row["equipment_count"] = 0  # 0은 0으로 유지 (UNKNOWN 변환 금지)
    # 나머지 None(UNKNOWN) 유지


_PROFILE_BUILDERS = {
    "manufacturing_standard": _profile_manufacturing_standard,
    "construction_standard":  _profile_construction_standard,
    "low_risk_office":        _profile_low_risk_office,
}


# ---------------------------------------------------------------------------
# 메인 생성 함수
# ---------------------------------------------------------------------------

def build_virtual_facility_profile(spec: dict) -> Dict[str, Any]:
    """가상 사업장 입력 dict 생성.

    입력 spec 예:
      {
        "sector": "INDUSTRIAL",
        "ksic_code": "C28",
        "profile_type": "manufacturing_standard",
        "variant": "baseline",
      }

    출력:
      factories row 형태 dict (FacilityProfile v2 build_facility_profile에
      그대로 투입 가능). 57개 입력 키 전부 존재 (미사용은 None=UNKNOWN).

    판정 실행/추론 없음. 생성만.
    """
    profile_type = spec.get("profile_type", "manufacturing_standard")
    if profile_type not in _PROFILE_BUILDERS:
        raise ValueError(
            f"unknown profile_type: {profile_type}. "
            f"available: {list(_PROFILE_BUILDERS.keys())}"
        )

    # 모든 키 None(UNKNOWN)으로 초기화 → 57차원 키 전부 존재 보장
    row = _empty_row()

    # id (build_facility_profile가 row["id"] 요구)
    row["id"] = spec.get("factory_id") or f"vr-{uuid.uuid4()}"

    # 프로파일별 값 채움
    _PROFILE_BUILDERS[profile_type](row, spec)

    # variant 후처리 훅 (현재는 baseline만, 값 보정 없음)
    # variant별 분기가 필요하면 여기에 추가 (판정 추론 금지)

    return row


def list_profile_types() -> List[str]:
    """사용 가능한 프로파일 타입 목록."""
    return list(_PROFILE_BUILDERS.keys())


def list_all_input_keys() -> List[str]:
    """FacilityProfile v2 입력 키 전체 (57차원 원본 키)."""
    return list(ALL_PROFILE_INPUT_KEYS)
