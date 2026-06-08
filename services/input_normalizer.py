"""
services/input_normalizer.py — Input Normalizer v1.2.0

역할:
- 별칭 통합 (workers → worker_count 등)
- 타입 변환 ("10" → 10)
- 빈값 처리 ("" → None)
- 단위 문자 제거 ("500㎡" → 500)
- 단위 환산 (전력→kW, 금액→원, 거리→m) — 단위 문자열이 있을 때만
- condition_code 양방향 키 보장 (electric_capacity, FLOOR_AREA 등)

허용: 별칭 통합, 타입 정규화, 빈값 처리, 명시 단위 환산
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
    # electric: API 입력은 electrical_capacity_kw로 정규화하되
    # electric_capacity condition_code (11건)를 위해 역방향도 보존
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
_UNIT_PATTERN = re.compile(r"[\u33a1kKwWm\u00b3\ud1a4\uc5b5\uc6d0\uba85\uce35\ub300]+$")

_POWER_KEYS = frozenset({
    "electrical_capacity_kw",
    "electric_capacity",
    "electric_capacity_kw",
    "power_capacity",
    "transformer_capacity_kva",
})
_AMOUNT_KEYS = frozenset({
    "contract_amount",
    "construction_amount",
    "contract_amount_won",
})
_DISTANCE_KEYS = frozenset({
    "distance_value",
    "distance",
    "distance_m",
    "TUNNEL_LENGTH",
})

_EOK = 100_000_000.0
_MANWON = 10_000.0


def _strip_units(value: str) -> str:
    return _UNIT_PATTERN.sub("", value.strip()).strip()


def _parse_numeric_prefix(value: str) -> Optional[float]:
    """문자열 앞부분 숫자만 추출 (단위 환산용)."""
    cleaned = value.strip().replace(",", "")
    match = re.match(r"^[-+]?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _convert_to_standard_unit(key: str, raw_value: Any) -> Any:
    """
    표준 단위 환산.
    - 전력 → kW (W: /1000, kVA: kW 근사 1:1)
    - 금액 → 원 (억: ×1억, 만원/만: ×1만, contract_amount_eok 키: ×1억)
    - 거리 → m (mm: /1000, cm: /100)
    - 단위 문자열이 없고 이미 숫자면 환산하지 않음 (추정 금지)
    """
    if raw_value is None:
        return raw_value

    if key == "contract_amount_eok":
        num = float(raw_value) if isinstance(raw_value, (int, float)) else _parse_numeric_prefix(str(raw_value))
        if num is not None:
            return num * _EOK
        return raw_value

    if isinstance(raw_value, (int, float)):
        return raw_value

    if not isinstance(raw_value, str):
        return raw_value

    text = raw_value.strip()
    if not text:
        return raw_value

    if key in _POWER_KEYS:
        lower = text.lower().replace(" ", "")
        num = _parse_numeric_prefix(lower)
        if num is None:
            return raw_value
        if "kva" in lower:
            return num
        if "kw" in lower:
            return num
        if lower.endswith("w") and not lower.endswith("kw"):
            return num / 1000.0
        return raw_value

    if key in _AMOUNT_KEYS:
        compact = text.replace(" ", "")
        num = _parse_numeric_prefix(compact)
        if num is None:
            return raw_value
        if "억원" in compact or "억" in compact:
            return num * _EOK
        if "만원" in compact or compact.endswith("만"):
            return num * _MANWON
        return raw_value

    if key in _DISTANCE_KEYS:
        lower = text.lower().replace(" ", "")
        num = _parse_numeric_prefix(lower)
        if num is None:
            return raw_value
        if lower.endswith("mm"):
            return num / 1000.0
        if lower.endswith("cm"):
            return num / 100.0
        if lower.endswith("m") and not lower.endswith("mm") and not lower.endswith("cm"):
            return num
        return raw_value

    return raw_value


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


def _ensure_condition_code_keys(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    엔진의 _evaluate_conditions()는 condition_code를 context 키로 직접 조회한다.
    normalizer가 alias 변환 후에도 원래 condition_code 키가 존재해야 한다.

    예:
      electric_capacity  → electrical_capacity_kw 변환 후
                           electric_capacity 키도 유지 (11건 룰 조회용)
      building_area      → floor_area 입력 시 building_area로 변환됨 (정상)
      FLOOR_AREA         → building_area와 동일 값 보장 (2건 룰)
      FLOOR_COUNT        → floor_count와 동일 값 보장 (2건 룰)
    """
    # electrical_capacity_kw 있으면 electric_capacity도 보장
    if "electrical_capacity_kw" in result and "electric_capacity" not in result:
        result["electric_capacity"] = result["electrical_capacity_kw"]

    # 대문자 condition_code 별칭 보장
    if "building_area" in result and "FLOOR_AREA" not in result:
        result["FLOOR_AREA"] = result["building_area"]
    if "floor_count" in result and "FLOOR_COUNT" not in result:
        result["FLOOR_COUNT"] = result["floor_count"]

    return result


def normalize_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    API payload → LEG 조건 판정용 표준 입력.

    별칭 통합 → 타입 정규화 → 빈값 None 처리 → condition_code 키 보장.
    판단/추정/기본값 생성 없음.
    """
    result: Dict[str, Any] = {}

    for key, value in payload.items():
        normalized_key = ALIAS_MAP.get(key, key)
        value = _convert_to_standard_unit(key, value)
        if normalized_key != key:
            value = _convert_to_standard_unit(normalized_key, value)
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

    # condition_code 양방향 키 보장
    return _ensure_condition_code_keys(result)
