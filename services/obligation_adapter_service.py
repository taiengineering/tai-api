"""Obligation Adapter Service — v1.3.0 (WO-ADAPTER-LAW-ENRICHMENT-001)

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

v1.1.0: build_result_data() 추가 — factory_diagnosis_results.result_data 조립
        (Track A 저장 배선용. 기존 함수 불변.)
v1.2.0: build_obligations_from_trigger_candidates() 추가 (CURSOR-TASK-002)
        Trigger 기반 semantic_clause 후보 → result_data.obligations 변환.
        기존 V4 흐름 무수정. FastAPI import 없음.
v1.3.0: Trigger 경로 obligation에 law_name/law_article/evidence 보강
        (WO-ADAPTER-LAW-ENRICHMENT-001). 값은 Glue(_resolve_law_for_candidates)가
        채운 candidate 필드를 그대로 사용 — 어댑터는 조합만, 새 판단/법령 생성 없음.
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

# content_type → rule_type 매핑 (Trigger 기반 후보용)
_CONTENT_TYPE_TO_RULE_TYPE = {
    "OBLIGATION": "OBLIGATION",
    "PROHIBITION": "PROHIBITION",
}

# Trigger 타입 → category 추정 (action_type 미제공 시 폴백)
_TRIGGER_TO_CATEGORY = {
    "WORK": "점검",
    "EQUIPMENT": "점검",
    "EQUIPMENT_ACT": "점검",
    "HAZARD_FACTOR": "점검",
    "THRESHOLD": "선임",
    "BUSINESS": "서류",
    "INDUSTRY": "서류",
}


def _category_from_action_type(action_type: str) -> str:
    """액션타입 → 정제레이어 category. 미매핑은 '서류' 기본."""
    return ACTION_TYPE_TO_CATEGORY.get((action_type or "").upper(), "서류")


def _category_from_trigger(trigger_code: str) -> str:
    """trigger_code 타입 머리 → category. 예: WORK:CONFINED_SPACE → '점검'."""
    family = trigger_code.split(":", 1)[0] if ":" in trigger_code else ""
    return _TRIGGER_TO_CATEGORY.get(family, "서류")


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

    category = _category_from_action_type(action_type)

    return {
        "id": str(condition.get("id") or ""),
        "category": category,
        "title": action_text or condition.get("industry_name") or "의무사항",
        "law_name": law_name,
        "law_article": appendix_no,
        "rule_type": action_type,
        "risk_level": "MEDIUM",
        "description": action_text,
        "evidence": [legal_basis] if legal_basis else [],
        "required_count": condition.get("required_count"),
        "auto_schedulable": False,
    }


def _build_obligation_from_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Trigger 기반 의무후보 1건 → obligation dict.

    semantic_clause 후보를 정제레이어 호환 포맷으로 변환.
    새 판단 없음. candidate에 있는 데이터만 사용.
    law_name/law_article/evidence는 Glue(_resolve_law_for_candidates)가 채운
    값을 그대로 사용 — 새 법령 생성 아님, 조합만.
    """
    trigger_code = candidate.get("trigger_code") or ""
    action_text = str(candidate.get("action_text") or "").strip()
    condition_text = str(candidate.get("condition_text") or "").strip()
    category = _category_from_trigger(trigger_code)

    # 제목: action_text 앞 50자
    title = action_text[:50] if action_text else "의무사항"

    # 법령정보 (Glue가 보강한 값. 없으면 빈 값 — 새 생성 아님)
    law_name = str(candidate.get("law_name") or "").strip()
    law_article = str(candidate.get("law_article") or "").strip()
    legal_basis = " ".join(p for p in (law_name, law_article) if p)

    return {
        "id": candidate.get("clause_id") or candidate.get("source_article_id") or "",
        "category": category,
        "title": title,
        "law_name": law_name,          # Glue 보강
        "law_article": law_article,    # Glue 보강
        "rule_type": _CONTENT_TYPE_TO_RULE_TYPE.get(
            candidate.get("content_type") or "", "OBLIGATION"
        ),
        "risk_level": "MEDIUM",
        "description": action_text,
        "condition": condition_text or None,
        "trigger_code": trigger_code,
        "confidence": candidate.get("confidence") or "MEDIUM",
        "evidence": [legal_basis] if legal_basis else [],   # Glue 보강
        "required_count": None,
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
            continue
        obligations.append(_build_obligation(detail, condition))

    return {
        "obligations": obligations,
        "obligation_count": len(obligations),
        "verdict": v4_result.get("verdict"),
        "factory_id": v4_result.get("factory_id"),
        "source": "V4_OBLIGATION_ADAPTER_v1",
    }


def build_obligations_from_trigger_candidates(
    candidates: List[Dict[str, Any]],
    factory_id: str,
    trigger_codes: List[str],
) -> Dict[str, Any]:
    """Trigger 기반 의무후보 → result_data.obligations 스키마 (v1.2.0).

    Args:
      candidates: trigger_obligation_generator.generate_obligation_candidates() 결과
      factory_id: 대상 사업장 ID
      trigger_codes: 생성된 Trigger Code Set

    Returns:
      build_obligations_from_v4()와 동일한 스키마.
      다운스트림 정제레이어가 그대로 소비 가능.

    새 판단 없음. candidates에 있는 데이터만 사용.
    """
    obligations = [_build_obligation_from_candidate(c) for c in candidates]
    verdict = "APPLICABLE" if obligations else "NOT_APPLICABLE"
    return {
        "obligations": obligations,
        "obligation_count": len(obligations),
        "verdict": verdict,
        "factory_id": factory_id,
        "trigger_codes": trigger_codes,
        "source": "TRIGGER_BASED_ADAPTER_v1",
    }


def build_result_data(adapter_result: Dict[str, Any], v4_result: Dict[str, Any]) -> Dict[str, Any]:
    """어댑터 obligations → factory_diagnosis_results.result_data 스키마.

    정제레이어(diagnosis_transform._extract_obligations)가 읽는 키:
      obligations / key_obligations 우선
    정제레이어가 읽는 보조 필드: sector / rule_count / risk_level

    이 함수는 어댑터 obligations를 그 스키마로 감싸기만 한다.
    새 판단/데이터 생성 없음 (obligations는 어댑터가 이미 만든 것).
    """
    obligations = adapter_result.get("obligations") or []
    return {
        "obligations": obligations,
        "key_obligations": obligations,
        "sector": v4_result.get("facility_sector") or "INDUSTRIAL",
        "rule_count": len(obligations),
        "applicable_count": len(obligations),
        "risk_level": "MEDIUM",
        "verdict": adapter_result.get("verdict"),
        "engine_version": "V4_OBLIGATION_ADAPTER_v1",
        "source": adapter_result.get("source"),
    }
