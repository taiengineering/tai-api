"""Trigger Applicability Adapter (TASK-003 + TASK-004).

의무후보(semantic_clause 기반) → evaluate_draft_for_facility() 재사용
→ facility_applicability 상태(MATCH_CANDIDATE / POSSIBLE_CANDIDATE /
   NOT_MATCHED / AMBIGUOUS / MISSING_DATA) 반환.

수정 금지 함수:
  evaluate_draft_for_facility()
  evaluate_scope_check()
  evaluate_numeric_check()
구조 변경 금지: facility_applicability 스키마 변경 금지.

ISSUE-001: FIELD_MAP 확장 (has_confined_space 등 Trigger 기반 binding_field)
  기존 facility_applicability_eval.FIELD_MAP 에 has_* 등 없음.
  이 모듈에서 TRIGGER_FIELD_MAP_EXTENSION 정의 후
  evaluate_* 호출 시 facility dict에 직접 주입하는 방식으로 우회.
  (facility_applicability_eval.py 수정 금지)

ISSUE-002: part_id None 시 evaluate_draft_for_facility 반환 None.
  Trigger 기반 후보는 source_part_id 가 있으면 사용,
  없으면 source_article_id 폴백.
  글로벌 아이디 연속성 유지.

DEV-IN-007: boolean scope 계약 의미 정정 (우선 3개 건설작업 필드 한정).
  기존 _evaluate_scope_check_extended 는 non-null 이면 무조건 POSSIBLE_CANDIDATE 였음
  (true/false 를 같은 수준으로 취급). boolean scope 는 소비자 3-state 계약이므로:
    true  -> MATCH_CANDIDATE    (존재 명시 확인 → scope 충족)
    false -> NOT_MATCHED        (부재 명시 확인 → scope 불충족)
    null  -> POSSIBLE_CANDIDATE (미확인 → 판단 유보; null 을 false 로 취급하지 않음)
  numeric / business / 비대상 scope 는 기존 동작 유지.
  facility_applicability_eval.evaluate_scope_check 는 수정하지 않음.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from services.facility_applicability_eval import (
    aggregate_applicability_status,
    evaluate_numeric_check,
    evaluate_scope_check,
)

# Trigger binding_field → factories 콜럼 매핑 확장
# facility_applicability_eval.FIELD_MAP 수정 없이 어댑터 내에서 주입
TRIGGER_FIELD_MAP_EXTENSION: Dict[str, Tuple[Optional[str], str]] = {
    "has_confined_space":     ("has_confined_space",    "DIRECT"),
    "has_blasting":           ("has_blasting",           "DIRECT"),
    "has_diving":             ("has_diving",             "DIRECT"),
    "has_asbestos_demo":      ("has_asbestos_demo",      "DIRECT"),
    "has_tower_crane":        ("has_tower_crane",        "DIRECT"),
    "has_high_pressure_gas":  ("has_high_pressure_gas",  "DIRECT"),
    "has_chemical_substance": ("has_chemical_substance", "DIRECT"),
    "has_boiler":             ("has_boiler",             "DIRECT"),
    "has_welding_work":       ("has_welding_work",       "DIRECT"),
    "has_demolition_work":    ("has_demolition_work",    "DIRECT"),
    "has_excavation_work":    ("has_excavation_work",    "DIRECT"),
    "has_diving_work":        ("has_diving",             "DIRECT"),
    "has_high_place_work":    ("has_high_place_work",    "DIRECT"),
    "has_scaffold_work":      ("has_scaffold_work",      "DIRECT"),
    "has_formwork_work":      ("has_formwork_work",      "DIRECT"),
    "has_electrical_work":    ("has_electrical_work",    "DIRECT"),
    "has_hot_work":           ("has_hot_work",           "DIRECT"),
    "equipment_type_code":    (None,                     "EQUIPMENT_JOIN"),
}

# DEV-IN-007: boolean 3-state 의미를 적용할 scope 필드 (우선 3개 건설작업 한정).
# 안전성 검증 후 다른 boolean scope 로 확장 여부를 별도 결정.
_BOOLEAN_SCOPE_FIELDS: set = {
    "has_excavation_work",
    "has_welding_work",
    "has_demolition_work",
}

# Trigger Code → numeric/scope slots 변환 규칙
_TRIGGER_TO_NUMERIC_SLOTS: Dict[str, List[Dict[str, Any]]] = {
    "THRESHOLD:EMPLOYEE_20_PLUS":   [{"binding_field": "employee_count", "operator": ">=", "value": 20,  "part_id": "__threshold__"}],
    "THRESHOLD:EMPLOYEE_50_PLUS":   [{"binding_field": "employee_count", "operator": ">=", "value": 50,  "part_id": "__threshold__"}],
    "THRESHOLD:EMPLOYEE_100_PLUS":  [{"binding_field": "employee_count", "operator": ">=", "value": 100, "part_id": "__threshold__"}],
    "THRESHOLD:EMPLOYEE_300_PLUS":  [{"binding_field": "employee_count", "operator": ">=", "value": 300, "part_id": "__threshold__"}],
    "THRESHOLD:AREA_400_PLUS":      [{"binding_field": "area_size",      "operator": ">=", "value": 400, "part_id": "__threshold__"}],
    "THRESHOLD:CONSTRUCTION_20BIL": [{"binding_field": "monetary_value", "operator": ">=", "value": 20_000_000_000, "part_id": "__threshold__"}],
    "THRESHOLD:CONSTRUCTION_8BIL":  [{"binding_field": "monetary_value", "operator": ">=", "value": 8_000_000_000,  "part_id": "__threshold__"}],
}

_TRIGGER_TO_SCOPE_SLOTS: Dict[str, List[Dict[str, Any]]] = {
    "WORK:CONFINED_SPACE":    [{"binding_field": "has_confined_space",    "part_id": "__work__"}],
    "WORK:BLASTING":          [{"binding_field": "has_blasting",           "part_id": "__work__"}],
    "WORK:DIVING":            [{"binding_field": "has_diving",             "part_id": "__work__"}],
    "WORK:ASBESTOS":          [{"binding_field": "has_asbestos_demo",      "part_id": "__work__"}],
    "WORK:HIGH_PRESSURE":     [{"binding_field": "has_high_pressure_gas",  "part_id": "__work__"}],
    "WORK:HIGH_PRESSURE_GAS": [{"binding_field": "has_high_pressure_gas",  "part_id": "__work__"}],
    "WORK:TOWER_CRANE":       [{"binding_field": "has_tower_crane",        "part_id": "__work__"}],
    "WORK:WELDING":           [{"binding_field": "has_welding_work",       "part_id": "__work__"}],
    "WORK:DEMOLITION":        [{"binding_field": "has_demolition_work",    "part_id": "__work__"}],
    "WORK:EXCAVATION":        [{"binding_field": "has_excavation_work",    "part_id": "__work__"}],
    "WORK:CHEMICAL_SUBSTANCE":[{"binding_field": "has_chemical_substance", "part_id": "__work__"}],
    "EQUIPMENT:BOILER":       [{"binding_field": "has_boiler",             "part_id": "__equip__"}],
    "EQUIPMENT:TOWER_CRANE":  [{"binding_field": "has_tower_crane",        "part_id": "__equip__"}],
    "EQUIPMENT:CRANE":        [{"binding_field": "equipment_type_code",    "part_id": "__equip__"}],
    "EQUIPMENT:PRESS":        [{"binding_field": "equipment_type_code",    "part_id": "__equip__"}],
    "EQUIPMENT:CONVEYOR":     [{"binding_field": "equipment_type_code",    "part_id": "__equip__"}],
    "EQUIPMENT:ELEVATOR":     [{"binding_field": "equipment_type_code",    "part_id": "__equip__"}],
    "HAZARD_FACTOR:CHEMICAL": [{"binding_field": "has_chemical_substance", "part_id": "__hazard__"}],
}


def _build_augmented_facility(facility: Dict[str, Any]) -> Dict[str, Any]:
    """ISSUE-001 우회: TRIGGER_FIELD_MAP_EXTENSION 필드를 facility dict에 주입."""
    aug = dict(facility)
    return aug


def _get_field_map_value(binding_field: str) -> Tuple[Optional[str], str]:
    """FIELD_MAP + TRIGGER_FIELD_MAP_EXTENSION 합산 조회."""
    from services.facility_applicability_eval import FIELD_MAP
    if binding_field in FIELD_MAP:
        return FIELD_MAP[binding_field]
    if binding_field in TRIGGER_FIELD_MAP_EXTENSION:
        return TRIGGER_FIELD_MAP_EXTENSION[binding_field]
    return (None, "MISSING")


def _evaluate_scope_check_extended(
    facility: Dict[str, Any],
    binding_field: str,
):
    """TRIGGER_FIELD_MAP_EXTENSION 지원 스코프 평가.

    DEV-IN-007: boolean scope 3-state 의미 (우선 _BOOLEAN_SCOPE_FIELDS 한정).
      true -> MATCH_CANDIDATE / false -> NOT_MATCHED / null -> POSSIBLE_CANDIDATE.
    그 외 scope 는 기존 동작(non-null -> POSSIBLE, null -> MISSING_DATA) 유지.
    """
    fac_col, quality = _get_field_map_value(binding_field)
    if fac_col is None:
        return ("SCOPE_CHECK", binding_field, None, None, None, None, "MISSING_DATA", "NO_FACILITY_COLUMN")
    fac_val = facility.get(fac_col)

    # DEV-IN-007: boolean 3-state 계약 (대상 필드 한정)
    if binding_field in _BOOLEAN_SCOPE_FIELDS:
        if fac_val is True:
            return ("SCOPE_CHECK", binding_field, fac_col, None, None, fac_val, "MATCH_CANDIDATE", "BOOLEAN_TRUE")
        if fac_val is False:
            return ("SCOPE_CHECK", binding_field, fac_col, None, None, fac_val, "NOT_MATCHED", "BOOLEAN_FALSE")
        # null / missing → 미확인 → 판단 유보 (null 을 false 로 취급하지 않음)
        return ("SCOPE_CHECK", binding_field, fac_col, None, None, None, "POSSIBLE_CANDIDATE", "BOOLEAN_NULL")

    # 기존 동작 유지 (비-boolean scope)
    if fac_val is None:
        return ("SCOPE_CHECK", binding_field, fac_col, None, None, None, "MISSING_DATA", "FACILITY_VALUE_NULL")
    return ("SCOPE_CHECK", binding_field, fac_col, None, None, fac_val, "POSSIBLE_CANDIDATE", "SCOPE_FIELD_EXISTS")


def _evaluate_numeric_check_extended(
    facility: Dict[str, Any],
    binding_field: str,
    operator: str,
    draft_value: Any,
):
    """TRIGGER_FIELD_MAP_EXTENSION 지원 수치 평가."""
    fac_col, quality = _get_field_map_value(binding_field)
    if fac_col is None:
        return ("NUMERIC_CHECK", binding_field, None, operator, draft_value, None, "MISSING_DATA", "NO_FACILITY_COLUMN")
    from services.facility_applicability_eval import compare_numeric
    fac_val = facility.get(fac_col)
    if fac_val is None:
        return ("NUMERIC_CHECK", binding_field, fac_col, operator, draft_value, None, "MISSING_DATA", "FACILITY_VALUE_NULL")
    result = compare_numeric(operator, draft_value, fac_val)
    return ("NUMERIC_CHECK", binding_field, fac_col, operator, draft_value, fac_val, result, "DIRECT_COMPARE")


def evaluate_candidate(
    candidate: Dict[str, Any],
    facility: Dict[str, Any],
    trigger_codes: List[str],
) -> Dict[str, Any]:
    """semantic_clause 후보 1건 → facility_applicability 상태 판단."""
    trigger_code = candidate.get("trigger_code") or ""
    confidence = candidate.get("confidence") or "MEDIUM"
    clause_id = candidate.get("clause_id") or ""
    source_article_id = candidate.get("source_article_id") or ""

    if trigger_code == "BUSINESS:REGISTERED":
        return {
            "semantic_clause_id": clause_id,
            "source_article_id": source_article_id,
            "applicability_status": "MATCH_CANDIDATE",
            "trigger_code": trigger_code,
            "confidence": confidence,
            "match_details": {"checks": 0, "reason": "BUSINESS_ALWAYS_MATCH"},
        }

    numeric_slots: List[Dict[str, Any]] = []
    scope_slots: List[Dict[str, Any]] = []

    for tc in trigger_codes:
        for ns in _TRIGGER_TO_NUMERIC_SLOTS.get(tc, []):
            numeric_slots.append(ns)
        for ss in _TRIGGER_TO_SCOPE_SLOTS.get(tc, []):
            scope_slots.append(ss)

    if not numeric_slots and not scope_slots:
        return {
            "semantic_clause_id": clause_id,
            "source_article_id": source_article_id,
            "applicability_status": "POSSIBLE_CANDIDATE",
            "trigger_code": trigger_code,
            "confidence": confidence,
            "match_details": {"checks": 0, "reason": "NO_SLOTS"},
        }

    check_results = []
    for ns in numeric_slots:
        check_results.append(
            _evaluate_numeric_check_extended(
                facility,
                binding_field=ns["binding_field"],
                operator=ns.get("operator") or ">=",
                draft_value=ns.get("value"),
            )
        )
    for ss in scope_slots:
        check_results.append(
            _evaluate_scope_check_extended(facility, binding_field=ss["binding_field"])
        )

    results_set = {r[6] for r in check_results}
    overall = aggregate_applicability_status(results_set)

    return {
        "semantic_clause_id": clause_id,
        "source_article_id": source_article_id,
        "applicability_status": overall,
        "trigger_code": trigger_code,
        "confidence": confidence,
        "match_details": {"checks": len(check_results), "results": list(results_set)},
    }


def evaluate_candidates_batch(
    candidates: List[Dict[str, Any]],
    facility: Dict[str, Any],
    trigger_codes: List[str],
) -> List[Dict[str, Any]]:
    """TASK-003+004: 의무후보 배치 평가."""
    return [evaluate_candidate(c, facility, trigger_codes) for c in candidates]
