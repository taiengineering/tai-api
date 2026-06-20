"""VR generation_spec — 가상 사업장 입력 생성기 (조합 변주판)

WO-VR-GENERATION-SPEC-EXPANSION-001-REBASE (생성기 신규)
WO-VR-VARIATION-GENERATOR-001 (템플릿 3종 → 조합 생성기 전환)

목적:
  FacilityProfile v2(57차원)와 1:1 정합되는 가상 사업장 입력 dict 생성.
  build_virtual_facility_profile(spec) → factories row 형태 dict.

  프로파일(제조/건설/사무) 구조는 유지하되,
  프로파일 내부 값은 고정값이 아니라 변주(랜덤 조합)로 생성한다.

엄격 원칙:
  실제 판정을 추론하지 않는다. 법령 조건을 반영하지 않는다.
  현실적 값 범위(후보 풀)에서만 선택. UNKNOWN(None) 허용. False는 False 유지.
  0을 UNKNOWN으로 바꾸지 않는다.
  생성만 한다 — 판정 실행/V4/condition/FacilityProfile/UI 수정 없음.
  일반 공정(process_lv*)과 건설 공정(construction_process_*)은 분리.
  일반 작업과 건설 작업(construction_work_*)은 분리.

변주(Variation):
  spec에 "seed"를 주면 재현 가능. 없으면 매 호출 랜덤.
  각 필드는 후보 풀 또는 범위에서 선택되며, boolean은 True/False 랜덤,
  배열/공정/작업은 부분집합 조합으로 생성.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import random
import uuid


# ---------------------------------------------------------------------------
# FacilityProfile v2 전체 입력 키 (factories row 키 기준)
# ---------------------------------------------------------------------------

ALL_PROFILE_INPUT_KEYS: List[str] = [
    "sector", "ksic_code",
    "employee_count", "subcontractor_worker_count", "total_worker_count_calc",
    "building_use_code", "building_area", "floor_count", "building_grade",
    "electrical_capacity_kw", "gas_capacity_m3", "gas_capacity_kg",
    "annual_energy_toe", "transformer_kva",
    "boiler_capacity", "elevator_count",
    "has_hazardous_material", "has_chemical_material", "has_high_pressure_gas",
    "has_safety_manager", "is_factory_registered", "is_public_facility",
    "construction_amount", "construction_type", "subcontractor_company_count",
    "has_tower_crane", "has_confined_space", "has_asbestos",
    "has_blasting", "has_diving_work",
    "process_lv1", "process_lv2", "process_lv3", "process_lv4",
    "equipment_count", "equipment_names", "equipment_install_years",
    "equipment_locations", "equipment_legal_targets", "equipment_operation_status",
    "construction_process_code", "construction_process_name",
    "construction_process_standard_version",
    "construction_work_code", "construction_work_name",
    "construction_work_standard_version", "construction_work_amount",
    "construction_work_duration_days", "construction_work_worker_count",
    "has_excavation_work", "has_high_place_work", "has_lifting_work",
    "has_demolition_work", "has_scaffold_work", "has_formwork_work",
    "has_welding_work", "has_electrical_work", "has_hot_work",
]


# ---------------------------------------------------------------------------
# 후보 풀 (현실적 값 범위. 판정 추론 없음)
# ---------------------------------------------------------------------------

BUILDING_GRADE_POOL = [None, "특급", "1급", "일반"]
CONSTRUCTION_TYPE_POOL = [None, "건축", "토목", "산업환경설비", "조경", "전문공사"]

MFG_PROCESS_LV1 = ["금속가공", "화학", "식품가공", "전자조립", "섬유", "목재가공", "플라스틱"]
MFG_PROCESS_LV2 = ["용접", "절삭", "도장", "성형", "조립", "열처리"]
MFG_PROCESS_LV3 = ["아크용접", "CO2용접", "MIG용접", "스팟용접", None]
MFG_EQUIP_POOL = ["프레스", "컨베이어", "용접기", "크레인", "지게차", "사출기",
                  "선반", "밀링", "도장부스", "건조로"]
CON_EQUIP_POOL = ["타워크레인", "굴착기", "콘크리트펌프", "덤프트럭", "로더",
                  "항타기", "고소작업대", "이동식크레인"]
OFFICE_EQUIP_POOL = ["복합기", "서버", "냉난방기", "정수기"]

CON_PROCESS = [("CP-100", "토공사"), ("CP-200", "골조공사"), ("CP-300", "마감공사"),
               ("CP-400", "철거공사"), ("CP-500", "설비공사")]
CON_WORK = [("CW-210", "굴착작업"), ("CW-220", "흙막이작업"), ("CW-310", "철근작업"),
            ("CW-320", "콘크리트타설"), ("CW-410", "도장작업"), ("CW-420", "방수작업")]
STD_VERSIONS = ["v1.0", "v2.0", "v2.1", "v3.0"]


def _rng(spec: dict) -> random.Random:
    seed = spec.get("seed")
    return random.Random(seed) if seed is not None else random.Random()


def _pick(r: random.Random, pool: list):
    return r.choice(pool)


def _coin(r: random.Random) -> bool:
    return r.random() < 0.5


def _rint(r: random.Random, lo: int, hi: int, allow_none: float = 0.0):
    """범위 정수 변주. allow_none 확률로 None(UNKNOWN)."""
    if allow_none and r.random() < allow_none:
        return None
    return r.randint(lo, hi)


def _subset(r: random.Random, pool: list, lo: int, hi: int) -> list:
    n = r.randint(lo, min(hi, len(pool)))
    return r.sample(pool, n)


# ---------------------------------------------------------------------------
# 프로파일별 변주 생성
# ---------------------------------------------------------------------------

def _empty_row() -> Dict[str, Any]:
    return {k: None for k in ALL_PROFILE_INPUT_KEYS}


def _profile_manufacturing_standard(row: Dict[str, Any], spec: dict, r: random.Random) -> None:
    """제조업: 공정/설비/전기/가스/보일러 변주. 건설 필드 UNKNOWN."""
    row["sector"] = spec.get("sector", "INDUSTRIAL")
    row["ksic_code"] = spec.get("ksic_code", "C28")
    # 인력 (범위 변주)
    reg = _rint(r, 1, 3000)
    sub = _rint(r, 0, 500)
    row["employee_count"] = reg
    row["subcontractor_worker_count"] = sub
    row["total_worker_count_calc"] = reg + sub
    # 건축물
    row["building_use_code"] = "공장"
    row["building_area"] = _rint(r, 100, 50000, allow_none=0.1)
    row["floor_count"] = _rint(r, 1, 30, allow_none=0.1)
    row["building_grade"] = _pick(r, BUILDING_GRADE_POOL)
    # 에너지
    row["electrical_capacity_kw"] = _rint(r, 20, 5000, allow_none=0.1)
    row["gas_capacity_m3"] = _rint(r, 10, 5000, allow_none=0.2)
    row["annual_energy_toe"] = _rint(r, 10, 10000, allow_none=0.1)
    row["transformer_kva"] = _rint(r, 50, 2000, allow_none=0.2)
    # 시설설비
    row["boiler_capacity"] = _rint(r, 1, 50, allow_none=0.2)
    row["elevator_count"] = _rint(r, 0, 10, allow_none=0.2)
    # 위험속성 (boolean 변주)
    row["has_hazardous_material"] = _coin(r)
    row["has_chemical_material"] = _coin(r)
    row["has_high_pressure_gas"] = _coin(r)
    row["has_safety_manager"] = _coin(r)
    row["is_factory_registered"] = _coin(r)
    row["is_public_facility"] = _coin(r)
    # 일반 공정 (조합 변주, 건설공정과 분리)
    row["process_lv1"] = _pick(r, MFG_PROCESS_LV1)
    row["process_lv2"] = _pick(r, MFG_PROCESS_LV2)
    row["process_lv3"] = _pick(r, MFG_PROCESS_LV3)
    row["process_lv4"] = None
    # 설비 (조합 변주)
    eq = _subset(r, MFG_EQUIP_POOL, 1, 6)
    row["equipment_count"] = len(eq)
    row["equipment_names"] = eq
    row["equipment_install_years"] = [_pick(r, list(range(1990, 2027))) for _ in eq]
    row["equipment_locations"] = [_pick(r, ["1층", "2층", "3층", "옥외", "지하"]) for _ in eq]
    row["equipment_legal_targets"] = [_coin(r) for _ in eq]
    row["equipment_operation_status"] = [_pick(r, ["ACTIVE", "BROKEN", "INACTIVE"]) for _ in eq]
    # 건설 필드 None 유지


def _profile_construction_standard(row: Dict[str, Any], spec: dict, r: random.Random) -> None:
    """건설업: 건설공정/작업 변주. 일반 process 혼합 금지(None)."""
    row["sector"] = spec.get("sector", "CONSTRUCTION")
    row["ksic_code"] = spec.get("ksic_code", "F41")
    # 인력
    reg = _rint(r, 1, 3000)
    sub = _rint(r, 0, 500)
    row["employee_count"] = reg
    row["subcontractor_worker_count"] = sub
    row["total_worker_count_calc"] = reg + sub
    # 건축물 None 유지 (건설 현장)
    # 건설
    row["construction_amount"] = _rint(r, 100_000_000, 1_000_000_000_000, allow_none=0.1)
    row["construction_type"] = _pick(r, CONSTRUCTION_TYPE_POOL)
    row["subcontractor_company_count"] = _rint(r, 1, 30, allow_none=0.1)
    row["has_tower_crane"] = _coin(r)
    row["has_confined_space"] = _coin(r)
    row["has_asbestos"] = _coin(r)
    row["has_blasting"] = _coin(r)
    row["has_diving_work"] = _coin(r)
    # 위험속성 일부
    row["has_safety_manager"] = _coin(r)
    row["is_factory_registered"] = False
    row["is_public_facility"] = _coin(r)
    # 일반 공정 혼합 금지 → None 유지
    # 건설 공정 (조합 변주)
    cp = _pick(r, CON_PROCESS)
    row["construction_process_code"] = cp[0]
    row["construction_process_name"] = cp[1]
    row["construction_process_standard_version"] = _pick(r, STD_VERSIONS)
    # 건설 작업 (조합 변주)
    cw = _pick(r, CON_WORK)
    row["construction_work_code"] = cw[0]
    row["construction_work_name"] = cw[1]
    row["construction_work_standard_version"] = _pick(r, STD_VERSIONS)
    row["construction_work_amount"] = _rint(r, 50_000_000, 500_000_000_000, allow_none=0.1)
    row["construction_work_duration_days"] = _rint(r, 7, 730)
    row["construction_work_worker_count"] = _rint(r, 3, 300)
    row["has_excavation_work"] = _coin(r)
    row["has_high_place_work"] = _coin(r)
    row["has_lifting_work"] = _coin(r)
    row["has_demolition_work"] = _coin(r)
    row["has_scaffold_work"] = _coin(r)
    row["has_formwork_work"] = _coin(r)
    row["has_welding_work"] = _coin(r)
    row["has_electrical_work"] = _coin(r)
    row["has_hot_work"] = _coin(r)
    # 설비 (건설 장비 조합)
    eq = _subset(r, CON_EQUIP_POOL, 1, 6)
    row["equipment_count"] = len(eq)
    row["equipment_names"] = eq
    row["equipment_install_years"] = [_pick(r, list(range(2000, 2027))) for _ in eq]
    row["equipment_locations"] = [_pick(r, ["현장A", "현장B", "현장C", "야적장"]) for _ in eq]
    row["equipment_legal_targets"] = [_coin(r) for _ in eq]
    row["equipment_operation_status"] = [_pick(r, ["ACTIVE", "BROKEN", "INACTIVE"]) for _ in eq]


def _profile_low_risk_office(row: Dict[str, Any], spec: dict, r: random.Random) -> None:
    """저위험 사무형: 설비/위험속성 최소, 단 변주는 적용."""
    row["sector"] = spec.get("sector", "INDUSTRIAL")
    row["ksic_code"] = spec.get("ksic_code", "J58")
    # 인력 (소규모 범위)
    reg = _rint(r, 1, 200)
    row["employee_count"] = reg
    row["subcontractor_worker_count"] = _rint(r, 0, 10)
    row["total_worker_count_calc"] = reg + (row["subcontractor_worker_count"] or 0)
    # 건축물 (사무용)
    row["building_use_code"] = "업무시설"
    row["building_area"] = _rint(r, 100, 3000, allow_none=0.1)
    row["floor_count"] = _rint(r, 1, 20, allow_none=0.1)
    row["building_grade"] = _pick(r, BUILDING_GRADE_POOL)
    # 에너지 (최소)
    row["electrical_capacity_kw"] = _rint(r, 10, 300, allow_none=0.1)
    row["annual_energy_toe"] = _rint(r, 5, 100, allow_none=0.2)
    row["elevator_count"] = _rint(r, 0, 3, allow_none=0.1)
    # 위험속성 (대부분 False, 가끔 True)
    row["has_hazardous_material"] = r.random() < 0.1
    row["has_chemical_material"] = r.random() < 0.1
    row["has_high_pressure_gas"] = False
    row["has_safety_manager"] = r.random() < 0.3
    row["is_factory_registered"] = False
    row["is_public_facility"] = r.random() < 0.2
    # 설비 최소 (0~2개)
    eq = _subset(r, OFFICE_EQUIP_POOL, 0, 2)
    row["equipment_count"] = len(eq)
    if eq:
        row["equipment_names"] = eq
        row["equipment_install_years"] = [_pick(r, list(range(2010, 2027))) for _ in eq]
        row["equipment_locations"] = [_pick(r, ["사무실", "서버실"]) for _ in eq]
        row["equipment_legal_targets"] = [False for _ in eq]
        row["equipment_operation_status"] = ["ACTIVE" for _ in eq]
    # 공정/건설 None 유지


_PROFILE_BUILDERS = {
    "manufacturing_standard": _profile_manufacturing_standard,
    "construction_standard":  _profile_construction_standard,
    "low_risk_office":        _profile_low_risk_office,
}


def build_virtual_facility_profile(spec: dict) -> Dict[str, Any]:
    """가상 사업장 입력 dict 생성 (조합 변주).

    spec 예: {"sector":"INDUSTRIAL","ksic_code":"C28",
              "profile_type":"manufacturing_standard",
              "variant":"baseline", "seed": 123}
    seed 지정 시 재현 가능. 없으면 매 호출 랜덤.
    출력: 57개 키 전부 존재 dict (미설정=None=UNKNOWN).
    """
    profile_type = spec.get("profile_type", "manufacturing_standard")
    if profile_type not in _PROFILE_BUILDERS:
        raise ValueError(
            f"unknown profile_type: {profile_type}. "
            f"available: {list(_PROFILE_BUILDERS.keys())}"
        )
    r = _rng(spec)
    row = _empty_row()
    row["id"] = spec.get("factory_id") or f"vr-{uuid.uuid4()}"
    _PROFILE_BUILDERS[profile_type](row, spec, r)
    return row


def list_profile_types() -> List[str]:
    return list(_PROFILE_BUILDERS.keys())


def list_all_input_keys() -> List[str]:
    return list(ALL_PROFILE_INPUT_KEYS)
