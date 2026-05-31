"""
services/input_completeness.py — Input Completeness v1.0.0

역할:
- 입력값 completeness 계산
- mandatory / recommended 누락 필드 식별
"""
from __future__ import annotations
from typing import Any, Dict, List

# condition_code 사용건수 기준 분류
# MANDATORY: 사용 22건 이상 + 수치 입력 가능한 핵심 필드
# RECOMMENDED: 사용 5건 이상 또는 주요 boolean 플래그
# OPTIONAL: 나머지

MANDATORY_FIELDS = [
    "employee_count",        # 119건 — 가장 중요
    "building_area",         # 127건 (= floor_area alias)
    "worker_count",          # 22건
]

RECOMMENDED_FIELDS = [
    "electrical_capacity_kw",  # 49건 (38+11)
    "elevator_count",          # 59건
    "floor_count",             # 27건
    "gas_capacity_kg",         # 112건
    "is_hazardous_material",   # 340건
    "has_high_pressure_gas",   # 70건
    "has_chemical_substance",  # 64건
    "is_factory_registered",   # 53건
    "is_multi_use",            # 43건
    "contract_amount",         # 65건
    "construction_amount",     # 35건
    "annual_energy_toe",       # 24건
]


def calculate_completeness(normalized_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    정규화된 입력값의 completeness 계산.
    판단 없음. 사실 기록만.
    """
    present = set(normalized_input.keys())

    mandatory_missing = [f for f in MANDATORY_FIELDS if f not in present]
    recommended_missing = [f for f in RECOMMENDED_FIELDS if f not in present]

    mandatory_score = len([f for f in MANDATORY_FIELDS if f in present])
    recommended_score = len([f for f in RECOMMENDED_FIELDS if f in present])

    # mandatory 100% + recommended 비율 가중
    if MANDATORY_FIELDS:
        m_pct = mandatory_score / len(MANDATORY_FIELDS) * 60
    else:
        m_pct = 60
    if RECOMMENDED_FIELDS:
        r_pct = recommended_score / len(RECOMMENDED_FIELDS) * 40
    else:
        r_pct = 40

    completeness = round(m_pct + r_pct)

    return {
        "completeness": completeness,
        "mandatory_present": mandatory_score,
        "mandatory_total": len(MANDATORY_FIELDS),
        "recommended_present": recommended_score,
        "recommended_total": len(RECOMMENDED_FIELDS),
        "mandatory_missing": mandatory_missing,
        "recommended_missing": recommended_missing,
        "has_all_mandatory": len(mandatory_missing) == 0,
    }
