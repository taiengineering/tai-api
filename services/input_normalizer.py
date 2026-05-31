"""
services/input_normalizer.py — Input Normalizer v1.0.0

역할:
- 별칭 통합 (workers → worker_count 등)
- 타입 변환 ("10" → 10)
- 빈값 처리 ("" → None)
- 단위 문자 제거 ("500㎡" → 500)

허용: 별칭 통합, 타입 정규화, 빈값 처리
금지: 판단, 추정, 기본값 자동 생성
"""
from __future__ import annotations
import re
from typing import Any, Dict, Optional

# condition_code 기준 alias 매핑
# (API 입력 → LEG condition_code 기준 정규 필드명)
ALIAS_MAP: Dict[str, str] = {
    # worker
    "workers":                  "worker_count",
    "worker":                   "worker_count",
    "num_workers":              "worker_count",
    # employee
    "employees":                "employee_count",
    "employee":                 "employee_count",
    "num_employees":            "employee_count",
    # floor_area → building_area (condition_code 기준)
    "floor_area":               "building_area",
    "total_floor_area":         "building_area",
    "area":                     "building_area",
    "FLOOR_AREA":               "building_area",
    # electric
    "electric_capacity":        "electrical_capacity_kw",
    "electric_capacity_kw":     "electrical_capacity_kw",
    "power_capacity":           "electrical_capacity_kw",
    # contract
    "contract_amount_eok":      "contract_amount",
    "contract_amount_won":      "contract_amount",
    # gas
    "gas_capacity":             "gas_capacity_kg",
    # floor count
    "floors":                   "floor_count",
    "num_floors":               "floor_count",
    "FLOOR_COUNT":              "floor_count",
}

# 단위 제거 패턴
_UNIT_PATTERN = re.compile(r"[㎡kKwWm³톤억원명층대]+$")


def _strip_units(value: str) -> str:
    return _UNIT_PATTERN.sub("", value.strip()).strip()


def _to_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = _strip_units(value)
        if cleaned == "":
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _normalize_value(key: str, value: Any) -> Any:
    """값 정규화. 숫자 필드는 float/int로. 빈값은 None."""
    if value is None or value == "" or value == []:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, str) and value.strip() == "":
        return None
    # 숫자형으로 변환 시도
    num = _to_number(value)
    if num is not None:
        return int(num) if num == int(num) else num
    return value


def normalize_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    API payload → LEG 조건 판정용 표준 입력.

    별칭 통합 → 타입 정규화 → 빈값 None 처리.
    판단/추정/기본값 생성 없음.
    """
    result: Dict[str, Any] = {}

    for key, value in payload.items():
        normalized_key = ALIAS_MAP.get(key, key)
        normalized_value = _normalize_value(normalized_key, value)
        if normalized_value is None:
            continue  # 빈값은 포함하지 않음
        # 기존에 이미 있으면 더 큰 값 유지 (building_area 중복 입력 등)
        if normalized_key in result:
            try:
                if float(normalized_value) > float(result[normalized_key]):
                    result[normalized_key] = normalized_value
            except (TypeError, ValueError):
                pass
        else:
            result[normalized_key] = normalized_value

    # sector는 대문자 통일
    if "sector" in result and isinstance(result["sector"], str):
        result["sector"] = result["sector"].strip().upper()

    return result
