"""Obligation Adapter Service — v1.0.0 (WO-OBLIGATION-ADAPTER-IMPL-001)

B안 어댑터: V4 verdict → result_data.obligations 스키마 변환.

설계 원칙 (PROJECT_POLICY / 기획서 역할 분리):
  - V4(applicability_api / applicability_condition_service) 불변 — 판정만
  - 정제레이어(diagnosis_transform) 불변 — 표현만
  - 이 어댑터는 그 사이 "변환"만 담당
  - 새 판단 금지: MATCH 여부는 V4가 이미 결정한 것을 그대로 사용
  - 새 법령/threshold/scope 생성 금지

입력: V4 evaluate() 결과 dict (evaluation_details 포함)
처리:
  1. evaluation_result == MATCH 인 condition만 필터
  2. condition 레코드의 law_name / appendix_no / action_text / action_type 사용
  3. action_type → category 매핑 (정제레이어 CATEGORY_MAP과 정합)
  4. result_data.obligations 스키마로 변환
출력: {obligations: [...], obligation_count, source}

FastAPI import 없음 (서비스 레이어 규칙).
"""
from __future__ import annotations

from typing import Any, Dict, List


# action_type → 정제레이어 category (diagnosis_transform.CATEGORY_MAP 정합)
#   정제레이어 카테고리: 선임 / 점검 / 신고 / 교육 / 서류
ACTION_TYPE_TO_CATEGORY = {
    "APPOINTMENT": "선임",       # 안전관리자 선임
    "DESIGNATION": "선임",       # 관리감독자 지정
    "EDUCATION": "교육",         # 안전보건교육
    "HEALTH_CHECK": "점검",      # 건강진단 (정기 점검 성격)
    "RISK_ASSESSMENT": "서류",   # 위험성평가 (문서 의무)
    "INSTALLATION": "서류",      # 설비 설치 (점검 대상화 전까지 서류)
}


def _category_from_action_type(action_type: str) -> str:
    """action_type → 정제레이어 category. 미매핑은 '서류' 기본."""
    return ACTION_TYPE_TO_CATEGORY.get((action_type or "").upper(), "서류")


def _build_obligation(detail: Dict[str, Any], condition: Dict[str, Any]) -> Dict[str, Any]:
    """MATCH detail 1건 + condition 레코드 → obligation dict.

    condition 레코드(applicability_conditions)가 가진 필드만 사용.
    새 데이터 생성 없음.
    """
    law_name = str(condition.get("law_name") or "").strip()
    appendix_no = str(condition.get("appendix_no") or "").strip()
    action_text = str(condition.get("action_text") or "").strip()
    action_type = str(condition.get("action_type") or "").strip()

    # 근거(evidence) = 법령명 + 조문/별표
    legal_basis = " ".join(p for p in (law_name, appendix_no) if p)

    # title: APPOINTMENT/DESIGNATION 류는 action_text가 길 수 있어
    #        action_type 기반 짧은 제목을 우선, action_text는 description으로
    category = _category_from_action_type(action_type)

    return {
        "id": str(condition.get("id") or ""),
        "category": category,
        "title": action_text or condition.get("industry_name") or "의무사항",
        "law_name": law_name,
        "rule_type": action_type,
        "risk_level": "MEDIUM",  # V4 미보유 → 정제레이어 폴백과 동일 기본값
        "description": action_text,
        "evidence": [legal_basis] if legal_basis else [],
        "required_count": condition.get("required_count"),
        "auto_schedulable": False,
    }


def build_obligations_from_v4(
    v4_result: Dict[str, Any],
    conditions_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """V4 evaluate() 결과 → result_data.obligations 스키마.

    Args:
      v4_result: applicability_api.evaluate() 반환 dict
      conditions_by_id: {condition_id: applicability_conditions row}

    Returns:
      {obligations, obligation_count, verdict, source}

    새 판단 없음: evaluation_result == 'MATCH'만 통과.
    """
    details = v4_result.get("evaluation_details") or []

    obligations: List[Dict[str, Any]] = []
    for detail in details:
        if detail.get("evaluation_result") != "MATCH":
            continue
        cond_id = str(detail.get("condition_id") or "")
        condition = conditions_by_id.get(cond_id)
        if not condition:
            # condition 레코드 없으면 변환 불가 → 건너뜀 (추정 금지)
            continue
        obligations.append(_build_obligation(detail, condition))

    return {
        "obligations": obligations,
        "obligation_count": len(obligations),
        "verdict": v4_result.get("verdict"),
        "factory_id": v4_result.get("factory_id"),
        "source": "V4_OBLIGATION_ADAPTER_v1",
    }
