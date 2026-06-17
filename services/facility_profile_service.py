"""FacilityProfile 변환 서비스

factories row → FacilityProfile (TriValue + Provenance)

핵심 원칙:
  UNKNOWN = state 전용. value 필드에 UNKNOWN 문자열/0/false 저장 절대 금지.
  null → UNKNOWN / 값 있음 → PRESENT
  factories 데이터 수정 금지
  Check Engine / Track A / Track B 연결 금지
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
    """
    # ---- 섹터 결정 ----
    sector = row.get("sector")
    sector_provenance = "INPUT"
    if not sector:
        sector = "INDUSTRIAL"  # 기본값
        sector_provenance = "DEFAULT"

    # ---- 필드별 TriValue ----
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
        "provenance": {
            "input_fields": input_fields,
            "inferred_fields": inferred_fields,
            "default_fields": default_fields,
        },
        "profile_version": 1,
    }
    return profile


def profile_to_db_row(profile: dict) -> dict:
    """FacilityProfile dict → facility_profiles INSERT 행."""

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

        "profile_snapshot":                 profile,  # JSON 전체
    }
