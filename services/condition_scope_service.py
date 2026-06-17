"""Phase 3: Condition Scope Layer

C1 평가기에 Scope 필터 추가.

핵심 원칙:
  scope_type 무관하게 동일한 인터페이스
  새 Scope Type 추가 시 C1 코드 수정 0
  텍스트 런타임 해석 금지
  is_general 금지
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# FacilityProfile에서 scope_type에 해당하는 값 추출
# 새 Scope Type 추가 시 이 함수만 확장 (C1 evaluator 코드 수정 없음)
# ---------------------------------------------------------------------------

def get_facility_scope_value(
    profile: dict,
    scope_type: str,
) -> Optional[str]:
    """FacilityProfile에서 scope_type에 해당하는 값 추출.

    반환: 값(문자열) 또는 None(UNKNOWN)
    
    Phase 0B 이후 확장 예시:
      PROCESS  → profile.get("processes", []) ... (TriList)
      ACTIVITY → profile.get("activities", [])
      EQUIP    → profile.get("equipment", [])
    """
    if scope_type == "INDUSTRY":
        return profile.get("ksic_code")  # None → UNKNOWN

    # Phase 0B 이후 확장 예정
    # PROCESS, ACTIVITY, EQUIP, MATERIAL는 현재 Phase 0B 미수집
    # 지금은 None 반환 (UNKNOWN 처리)
    return None


# ---------------------------------------------------------------------------
# 공통 Scope 평가 인터페이스
# ---------------------------------------------------------------------------

def evaluate_scope(
    scope: dict,
    facility_profile: dict,
) -> tuple[str, str]:
    """(result, reason) 반환.

    인터페이스 규칙:
      scope_type이 INDUSTRY든 PROCESS든 동일 로직.
      새 Type 추가 시 get_facility_scope_value만 확장.
    """
    scope_type = scope["scope_type"]
    operator = scope["scope_operator"]
    values = scope["scope_values"] or []

    facility_value = get_facility_scope_value(facility_profile, scope_type)

    if facility_value is None:
        return "UNKNOWN", (
            f"scope_type={scope_type}: "
            f"facility 값 미확인 (Phase 0B 이후 확장 예정 또는 입력 없음)"
        )

    if operator == "IN":
        matched = any(facility_value.startswith(v) for v in values)
        if matched:
            return "SCOPE_MATCH", (
                f"facility={facility_value} ∈ {values}"
            )
        else:
            return "NOT_APPLICABLE", (
                f"facility={facility_value} ∉ {values}: 업종 범위 외"
            )

    if operator == "NOT_IN":
        matched = any(facility_value.startswith(v) for v in values)
        if not matched:
            return "SCOPE_MATCH", (
                f"facility={facility_value} ∉ 배타집합 {values}: 일반 조항 해당"
            )
        else:
            return "NOT_APPLICABLE", (
                f"facility={facility_value} ∈ 배타집합: 명시 업종 해당, 일반 조항 도달 안 됨"
            )

    if operator == "HAS":
        # 나중에 EQUIP/PROC에서 TriList 기반 체크 확장 예정
        return "UNKNOWN", "HAS operator: Phase 0B 이후 구현 예정"

    return "UNKNOWN", f"operator={operator}: 미정의 연산자"


def evaluate_scopes(
    scopes: List[dict],
    facility_profile: dict,
) -> tuple[str, str]:
    """condition에 얰결된 scope 목록 전체 평가.

    하나라도 SCOPE_MATCH이면 통과.
    모두 NOT_APPLICABLE이면 NOT_APPLICABLE.
    UNKNOWN 포함 시 UNKNOWN.
    """
    if not scopes:
        # Scope 없으면 전체 허용 (미정의 조건은 PASS)
        return "SCOPE_MATCH", "no scope restriction"

    results = [evaluate_scope(s, facility_profile) for s in scopes]

    if any(r[0] == "SCOPE_MATCH" for r in results):
        reasons = [r[1] for r in results if r[0] == "SCOPE_MATCH"]
        return "SCOPE_MATCH", " | ".join(reasons)

    if any(r[0] == "UNKNOWN" for r in results):
        reasons = [r[1] for r in results if r[0] == "UNKNOWN"]
        return "UNKNOWN", " | ".join(reasons)

    reasons = [r[1] for r in results]
    return "NOT_APPLICABLE", " | ".join(reasons)
