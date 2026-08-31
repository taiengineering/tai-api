from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from services.time import now_kst, serialize_external_utc

APPOINTMENT_TARGET_NORMALIZE = {
    "소방안전관리자": "fire_safety_manager",
    "승강기 안전관리자": "elevator_safety_manager",
    "위험물안전관리자": "hazardous_material_manager",
    "위험물안전관리자 대리자": "hazardous_material_manager",
    "위험물운반자": "hazardous_material_manager",
    "안전관리자": "safety_manager",
}

# 산업 sector 표준 이중성 메모:
#   - 입력/저장/가격 API 표준 = INDUSTRIAL (constants/sectors.py, 2026-05-07 canonical)
#   - 엔진/룰데이터 표준      = MANUFACTURING (rule sector 값, SECTOR_RULE_GROUPS 키)
#   INDUSTRIAL은 MANUFACTURING과 동일 룰그룹을 쓰도록 별칭 등록한다(경계 변환).
#   판정 로직·룰데이터·입력 표준은 변경하지 않는다.
SECTOR_RULE_GROUPS: Dict[str, List[str]] = {
    "BUILDING": ["COMMON", "BUILDING", "BUILDING_MANUFACTURING", "BUILDING_CONSTRUCTION"],
    "MANUFACTURING": ["COMMON", "MANUFACTURING", "CONSTRUCTION_MANUFACTURING", "BUILDING_MANUFACTURING"],
    "INDUSTRIAL": ["COMMON", "MANUFACTURING", "CONSTRUCTION_MANUFACTURING", "BUILDING_MANUFACTURING"],
    "CONSTRUCTION": ["COMMON", "CONSTRUCTION", "CONSTRUCTION_MANUFACTURING", "BUILDING_CONSTRUCTION"],
    "SPECIAL_FACILITY": ["COMMON", "SPECIAL_FACILITY", "BUILDING", "BUILDING_MANUFACTURING"],
    "SPECIAL": ["COMMON", "SPECIAL_FACILITY", "BUILDING", "BUILDING_MANUFACTURING"],
}

_CONSTRUCTION_AMOUNT_THRESHOLDS: Dict[str, int] = {
    "건축": 15_000_000_000,
    "토목": 12_000_000_000,
    "공통": 12_000_000_000,
    "기타": 12_000_000_000,
}


def _to_float(*vals) -> float:
    for v in vals:
        if v is None or v == "":
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return 0.0


def _to_int(*vals) -> int:
    for v in vals:
        if v is None or v == "":
            continue
        try:
            return int(float(v))
        except (TypeError, ValueError):
            continue
    return 0


def _now_iso() -> str:
    return serialize_external_utc(now_kst())


def _parse_survey_data(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def _normalize_target_code(code: str) -> str:
    if not code:
        return code
    return APPOINTMENT_TARGET_NORMALIZE.get(code, code)


def get_sector_groups(sector: str) -> List[str]:
    return SECTOR_RULE_GROUPS.get(sector.strip().upper(), [sector.strip().upper()])


def get_effective_worker_count(factory: dict) -> int:
    sec = str(factory.get("sector") or factory.get("site_type") or "").upper()
    base = int(factory.get("employee_count") or factory.get("worker_count") or 0)
    if sec == "CONSTRUCTION":
        sub = int(factory.get("subcontractor_worker_count") or 0)
        return base + sub
    return base


def get_construction_amount_threshold(factory: dict) -> int:
    return _CONSTRUCTION_AMOUNT_THRESHOLDS.get(factory.get("construction_type") or "건축", 15_000_000_000)
