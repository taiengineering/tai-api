"""FacilityProfile 변환 서비스

factories row → FacilityProfile (TriValue + Provenance)

핵심 원칙:
  UNKNOWN = state 전용. value 필드에 UNKNOWN 문자열/0/false 저장 절대 금지.
  null → UNKNOWN / 값 있음 → PRESENT
  factories 데이터 수정 금지
  Check Engine / Track A / Track B 연결 금지

확장 (WO-FACILITYPROFILE-EXPANSION-001):
  사용자 입력 계약 전체를 FacilityProfile 계약으로 정합.
  신규 그룹: facility_physical / facility_hazard / construction /
            process(일반) / equipment / construction_process / construction_work.
  규칙: 수집 → 전달만. 값 변환 금지. 판정 로직 추가 금지. 조건 추가 금지.
  일반 공정(process.*)과 건설 공정(construction_process.*)은 분리.
  일반 작업(task)과 건설 작업(construction_work.*)은 분리.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# TriValue 헬퍼
# ---------------------------------------------------------------------------

def _tri(raw_value: Any, provenance: str = "INPUT") -> Dict[str, Any]:
    """None → UNKNOWN / 값 있음 → PRESENT.

    절대 금지:
      value 필드에 'UNKNOWN' 문자열 저장
      null 값을 0 또는 false로 변환
    """
    if raw_value is None:
        return {"state": "UNKNOWN", "value": None, "provenance": provenance}
    return {"state": "PRESENT", "value": raw_value, "provenance": provenance}


def _gas_capacity(row: dict) -> Dict[str, Any]:
    """gas_capacity_m3 우선, 없으면 gas_capacity_kg."""
    m3 = row.get("gas_capacity_m3")
    kg = row.get("gas_capacity_kg")
    if m3 is not None:
        return _tri(m3)
    if kg is not None:
        return _tri(kg)
    return _tri(None)


# ---------------------------------------------------------------------------
# 주요 변환 함수
# ---------------------------------------------------------------------------

def build_facility_profile(row: dict) -> Dict[str, Any]:
    """factories row → FacilityProfile dict.

    이 함수는 factories를 수정하지 않는다.
    반환된 dict는 profile_snapshot으로 저장된다.

    수집 → 전달만 수행. 값 변환/판정/조건 추가 없음.
    """
    # ---- 섹터 결정 ----
    sector = row.get("sector")
    sector_provenance = "INPUT"
    if not sector:
        sector = "INDUSTRIAL"  # 기본값
        sector_provenance = "DEFAULT"

    # ---- [기존] 필드별 TriValue (11차원 유지) ----
    workforce = {
        "regular_workers":     _tri(row.get("employee_count")),
        "subcontract_workers": _tri(row.get("subcontractor_worker_count")),
        "total_workers":       _tri(row.get("total_worker_count_calc")),
    }
    building = {
        "use_code":    _tri(row.get("building_use_code")),
        "floor_area":  _tri(row.get("building_area")),
        "floor_count": _tri(row.get("floor_count")),
    }
    metrics = {
        "construction_amount": _tri(row.get("construction_amount")),
        "electrical_kw":       _tri(row.get("electrical_capacity_kw")),
        "gas_capacity":        _gas_capacity(row),
    }

    # ---- [신규] 시설 물리속성 ----
    facility_physical = {
        "boiler_capacity":   _tri(row.get("boiler_capacity")),
        "elevator_count":    _tri(row.get("elevator_count")),
        "annual_energy_toe": _tri(row.get("annual_energy_toe")),
        "building_grade":    _tri(row.get("building_grade")),
        "transformer_kva":   _tri(row.get("transformer_kva")),
    }

    # ---- [신규] 시설 위험속성 ----
    facility_hazard = {
        "has_hazardous_material": _tri(row.get("has_hazardous_material")),
        "has_chemical_material":  _tri(row.get("has_chemical_material")),
        "has_high_pressure_gas":  _tri(row.get("has_high_pressure_gas")),
        "has_safety_manager":     _tri(row.get("has_safety_manager")),
        "is_factory_registered":  _tri(row.get("is_factory_registered")),
        "is_public_facility":     _tri(row.get("is_public_facility")),
    }

    # ---- [신규] 건설 속성 ----
    construction = {
        "construction_type":          _tri(row.get("construction_type")),
        "subcontractor_company_count": _tri(row.get("subcontractor_company_count")),
        "has_tower_crane":            _tri(row.get("has_tower_crane")),
        "has_confined_space":         _tri(row.get("has_confined_space")),
        "has_asbestos":               _tri(row.get("has_asbestos")),
        "has_blasting":               _tri(row.get("has_blasting")),
        "has_diving_work":            _tri(row.get("has_diving_work")),
    }

    # ---- [신규] 공정 (일반) ----
    process = {
        "process_lv1": _tri(row.get("process_lv1")),
        "process_lv2": _tri(row.get("process_lv2")),
        "process_lv3": _tri(row.get("process_lv3")),
        "process_lv4": _tri(row.get("process_lv4")),
    }

    # ---- [신규] 설비 ----
    equipment = {
        "equipment_count":            _tri(row.get("equipment_count")),
        "equipment_names":            _tri(row.get("equipment_names")),
        "equipment_install_years":    _tri(row.get("equipment_install_years")),
        "equipment_locations":        _tri(row.get("equipment_locations")),
        "equipment_legal_targets":    _tri(row.get("equipment_legal_targets")),
        "equipment_operation_status": _tri(row.get("equipment_operation_status")),
    }

    # ---- [신규] 건설 공정 (일반 process와 분리, 표준코드 체계 별도) ----
    construction_process = {
        "construction_process_code":             _tri(row.get("construction_process_code")),
        "construction_process_name":             _tri(row.get("construction_process_name")),
        "construction_process_standard_version": _tri(row.get("construction_process_standard_version")),
    }

    # ---- [신규] 건설 작업 (일반 task와 분리, 표준코드 체계 별도) ----
    construction_work = {
        "construction_work_code":             _tri(row.get("construction_work_code")),
        "construction_work_name":             _tri(row.get("construction_work_name")),
        "construction_work_standard_version": _tri(row.get("construction_work_standard_version")),
        "construction_work_amount":           _tri(row.get("construction_work_amount")),
        "construction_work_duration_days":    _tri(row.get("construction_work_duration_days")),
        "construction_work_worker_count":     _tri(row.get("construction_work_worker_count")),
        "has_excavation_work":   _tri(row.get("has_excavation_work")),
        "has_high_place_work":   _tri(row.get("has_high_place_work")),
        "has_lifting_work":      _tri(row.get("has_lifting_work")),
        "has_demolition_work":   _tri(row.get("has_demolition_work")),
        "has_scaffold_work":     _tri(row.get("has_scaffold_work")),
        "has_formwork_work":     _tri(row.get("has_formwork_work")),
        "has_welding_work":      _tri(row.get("has_welding_work")),
        "has_electrical_work":   _tri(row.get("has_electrical_work")),
        "has_hot_work":          _tri(row.get("has_hot_work")),
    }

    # ---- provenance 요약 ----
    input_fields: List[str] = []
    default_fields: List[str] = []
    inferred_fields: List[str] = []

    # sector
    if sector_provenance == "INPUT":
        input_fields.append("sector")
    else:
        default_fields.append("sector")

    # ksic_code
    if row.get("ksic_code"):
        input_fields.append("ksic_code")

    all_tri_fields = {
        **{f"workforce.{k}": v for k, v in workforce.items()},
        **{f"building.{k}": v for k, v in building.items()},
        **{f"metrics.{k}": v for k, v in metrics.items()},
        **{f"facility_physical.{k}": v for k, v in facility_physical.items()},
        **{f"facility_hazard.{k}": v for k, v in facility_hazard.items()},
        **{f"construction.{k}": v for k, v in construction.items()},
        **{f"process.{k}": v for k, v in process.items()},
        **{f"equipment.{k}": v for k, v in equipment.items()},
        **{f"construction_process.{k}": v for k, v in construction_process.items()},
        **{f"construction_work.{k}": v for k, v in construction_work.items()},
    }
    for field_path, tri in all_tri_fields.items():
        if tri["state"] == "PRESENT":
            prov = tri.get("provenance", "INPUT")
            if prov == "INPUT":
                input_fields.append(field_path)
            elif prov == "INFERRED":
                inferred_fields.append(field_path)
            else:
                default_fields.append(field_path)

    profile = {
        "factory_id": str(row["id"]),
        "sector": sector,
        "sector_provenance": sector_provenance,
        "ksic_code": row.get("ksic_code"),
        "workforce": workforce,
        "building": building,
        "metrics": metrics,
        "facility_physical": facility_physical,
        "facility_hazard": facility_hazard,
        "construction": construction,
        "process": process,
        "equipment": equipment,
        "construction_process": construction_process,
        "construction_work": construction_work,
        "provenance": {
            "input_fields": input_fields,
            "inferred_fields": inferred_fields,
            "default_fields": default_fields,
        },
        "profile_version": 2,
    }
    return profile


def profile_to_db_row(profile: dict) -> dict:
    """FacilityProfile dict → facility_profiles INSERT 행.

    기존 11차원 컬럼은 그대로 유지 (하위호환).
    신규 확장 필드는 profile_snapshot(JSON 전체)에 포함되어 보존된다.
    (신규 필드를 평탄화 컬럼으로 추가하지 않음 = DB 스키마 변경 회피,
     수집→전달만 수행. 평탄화가 필요하면 별도 WO에서 컬럼 추가.)
    """

    def _state(tri): return tri["state"]
    def _value(tri): return tri["value"]
    def _prov(tri):  return tri.get("provenance", "INPUT")

    wf = profile["workforce"]
    bl = profile["building"]
    mt = profile["metrics"]
    pv = profile["provenance"]

    return {
        "factory_id":                       profile["factory_id"],
        "profile_version":                  profile["profile_version"],
        "sector":                           profile["sector"],
        "ksic_code":                        profile.get("ksic_code"),

        "regular_workers_state":            _state(wf["regular_workers"]),
        "regular_workers_value":            _value(wf["regular_workers"]),
        "regular_workers_provenance":       _prov(wf["regular_workers"]),

        "subcontract_workers_state":        _state(wf["subcontract_workers"]),
        "subcontract_workers_value":        _value(wf["subcontract_workers"]),
        "subcontract_workers_provenance":   _prov(wf["subcontract_workers"]),

        "total_workers_state":              _state(wf["total_workers"]),
        "total_workers_value":              _value(wf["total_workers"]),
        "total_workers_provenance":         _prov(wf["total_workers"]),

        "use_code_state":                   _state(bl["use_code"]),
        "use_code_value":                   _value(bl["use_code"]),
        "use_code_provenance":              _prov(bl["use_code"]),

        "floor_area_state":                 _state(bl["floor_area"]),
        "floor_area_value":                 _value(bl["floor_area"]),
        "floor_area_provenance":            _prov(bl["floor_area"]),

        "floor_count_state":                _state(bl["floor_count"]),
        "floor_count_value":                _value(bl["floor_count"]),
        "floor_count_provenance":           _prov(bl["floor_count"]),

        "construction_amount_state":        _state(mt["construction_amount"]),
        "construction_amount_value":        _value(mt["construction_amount"]),
        "construction_amount_provenance":   _prov(mt["construction_amount"]),

        "electrical_kw_state":              _state(mt["electrical_kw"]),
        "electrical_kw_value":              _value(mt["electrical_kw"]),
        "electrical_kw_provenance":         _prov(mt["electrical_kw"]),

        "gas_capacity_state":               _state(mt["gas_capacity"]),
        "gas_capacity_value":               _value(mt["gas_capacity"]),
        "gas_capacity_provenance":          _prov(mt["gas_capacity"]),

        "input_fields":                     pv["input_fields"],
        "inferred_fields":                  pv["inferred_fields"],
        "default_fields":                   pv["default_fields"],

        "profile_snapshot":                 profile,  # JSON 전체 (신규 필드 포함)
    }
