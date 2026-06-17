"""Phase 2: ApplicabilityCondition 파일럿

appendix_condition → ApplicabilityCondition 변환 (B4)
FacilityProfile × ApplicabilityCondition C1 평가

핵심 원칙:
  UNKNOWN ≠ FALSE
  PRESENT → 비교 / UNKNOWN → UNKNOWN 반환 / ABSENT → NOT_APPLICABLE
  Obligation/Diagnosis 생성 금지
  안전관리자 선임 7건 파일럿만
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# B4: appendix_condition → ApplicabilityCondition 변환
# ---------------------------------------------------------------------------

def build_applicability_condition(ac: dict, law_name: str, appendix_no: str) -> dict:
    """appendix_condition 1건 → ApplicabilityCondition dict.

    subject_raw = "상시근로자" 고정값 (파일럿 한정).
    """
    return {
        "appendix_condition_id": str(ac["id"]),
        "law_name": law_name,
        "appendix_no": appendix_no,
        "sector": ac.get("sector"),
        "industry_name": ac.get("industry_name"),
        # actor
        "actor_code": "ACTOR:OWNER",
        "actor_raw": "사업주",
        # quantifier
        "metric": "METRIC:EMPLOYEE_COUNT",
        "subject_raw": "상시근로자",
        "operator": ac.get("threshold_operator", ">="),
        "threshold_value": float(ac.get("threshold_value", 0)),
        "threshold_unit": ac.get("threshold_unit", "명"),
        # obligation
        "action_type": "APPOINTMENT",
        "action_text": ac.get("raw_condition", ""),
        "required_count": _infer_required_count(ac.get("raw_condition", "")),
        # completeness
        "actor_coded": True,
        "subject_ok": True,
        "status": "ACTIVE",
    }


def _infer_required_count(raw_condition: str) -> int:
    """raw_condition에서 선임 수 추론."""
    if "2명" in raw_condition:
        return 2
    return 1


# ---------------------------------------------------------------------------
# C1: FacilityProfile × ApplicabilityCondition 평가
# ---------------------------------------------------------------------------

def evaluate_condition(
    tri_value: dict,
    condition: dict,
) -> tuple[str, str]:
    """(evaluation_result, reason) 반환.

    규칙:
      actor ≠ ACTOR:OWNER → NOT_APPLICABLE
      PRESENT → 수치 비교
      UNKNOWN → UNKNOWN (비교 불가 — null→0 자동매칭 차단)
      ABSENT  → NOT_APPLICABLE
    """
    # actor 검사
    if condition.get("actor_code") != "ACTOR:OWNER":
        return "NOT_APPLICABLE", f"actor={condition.get('actor_code')}: 사업주 의무 아님"

    state = tri_value.get("state", "UNKNOWN")
    value = tri_value.get("value")

    if state == "UNKNOWN":
        return "UNKNOWN", "regular_workers.state=UNKNOWN: 수치 비교 불가"

    if state == "ABSENT":
        return "NOT_APPLICABLE", "regular_workers.state=ABSENT: 해당없음"

    # PRESENT → 수치 비교
    if value is None:
        return "UNKNOWN", "state=PRESENT이지만 value=None: 데이터 오류"

    threshold = float(condition.get("threshold_value", 0))
    operator = condition.get("operator", ">=")
    num_value = float(value)

    ops = {
        ">=": num_value >= threshold,
        ">": num_value > threshold,
        "<=": num_value <= threshold,
        "<": num_value < threshold,
        "==": num_value == threshold,
    }
    matched = ops.get(operator, False)

    if matched:
        return "MATCH", (
            f"regular_workers={num_value} {operator} {threshold}: 조건 충족"
        )
    else:
        return "NOT_MATCH", (
            f"regular_workers={num_value} {operator} {threshold}: 조건 미충족"
        )


def evaluate_facility(
    profile: dict,
    conditions: List[dict],
) -> List[dict]:
    """FacilityProfile × ApplicabilityCondition 전체 평가.

    반환: [
      {condition_id, metric, input_state, input_value,
       evaluation_result, evaluation_reason}
    ]
    """
    regular_workers = (
        profile.get("workforce", {})
        .get("regular_workers", {"state": "UNKNOWN", "value": None})
    )

    results = []
    for cond in conditions:
        result, reason = evaluate_condition(regular_workers, cond)
        results.append({
            "condition_id": cond.get("id"),
            "metric": "METRIC:EMPLOYEE_COUNT",
            "input_state": regular_workers.get("state"),
            "input_value": regular_workers.get("value"),
            "evaluation_result": result,
            "evaluation_reason": reason,
            "industry_name": cond.get("industry_name"),
            "threshold_value": cond.get("threshold_value"),
            "operator": cond.get("operator"),
            "required_count": cond.get("required_count"),
        })
    return results


def aggregate_verdict(results: List[dict]) -> dict:
    """MATCH한 조건에서 verdict + required_count 산정.

    정대 선임 수 = 업종 특이 조건 우선,
    없으면 일반 조건 사용.
    """
    matched = [r for r in results if r["evaluation_result"] == "MATCH"]
    unknown = [r for r in results if r["evaluation_result"] == "UNKNOWN"]

    if not matched and unknown:
        return {"verdict": "UNKNOWN", "required_count": 0, "matched_conditions": []}

    if not matched:
        return {"verdict": "NOT_REQUIRED", "required_count": 0, "matched_conditions": []}

    # 매칭 중 최대 threshold에 해당하는 required_count 선택
    best = max(matched, key=lambda r: r["threshold_value"])
    return {
        "verdict": "REQUIRED",
        "required_count": best["required_count"],
        "matched_conditions": [r["evaluation_reason"] for r in matched],
    }
