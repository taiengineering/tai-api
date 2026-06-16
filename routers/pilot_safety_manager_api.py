"""WO-D-004B-PILOT-SAFETY-MANAGER

산안법 시행령 별표3 기반 안전관리자 선임 의무 판정 파일럿.

범위 제한:
  - appendix_condition 7건 (안전관리자_선임기준) 만 사용
  - 상시근로자 수 + 업종명 텍스트 매칭
  - KSIC 일반 매핑 엔진 확대 금지
  - 전체 SemanticClause 평가기 확대 금지

금지:
  evaluate_single_factory / evaluate_draft_for_facility 수정 금지
  appendix_condition 외 테이블 수정 금지
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase

router = APIRouter(
    prefix="/pilot/safety-manager",
    tags=["D-004B PILOT Safety Manager"],
)


# 업종 텍스트 매칭 테이블 (수동 유지 — KSIC 바로 매핑 전 임시)
# 구조: {appendix_condition.industry_name 패턴: [KSIC 대분류 prefix, ...]}
_INDUSTRY_KSIC_MAP = {
    # 식료품·음료 제조업 등 고위험 제조업군
    "식료품": ["C10", "C11"],
    "음료": ["C11"],
    # 운수 및 창고업
    "운수": ["H49", "H50", "H51", "H52"],
    "창고": ["H52"],
    # 토사석 광업
    "토사석": ["B071"],
    "광업": ["B"],
}


def _match_industry(ksic_code: str, industry_name: str) -> bool:
    """업종명 텍스트와 KSIC 코드 매칭.

    industry_name에 키워드가 포함되면 KSIC prefix로 멤츠 여부 확인.
    """
    ksic_upper = ksic_code.upper()
    for keyword, prefixes in _INDUSTRY_KSIC_MAP.items():
        if keyword in industry_name:
            for prefix in prefixes:
                if ksic_upper.startswith(prefix):
                    return True
    return False


def _evaluate_condition(
    ac: dict,
    employee_count: int,
    ksic_code: str,
) -> Optional[dict]:
    """appendix_condition 하나와 사업장 프로필 비교.

    반환: {판정, 근거} | None(조건 해당 안 됨)
    """
    industry_name = ac.get("industry_name", "")
    threshold = int(ac.get("threshold_value", 0))
    operator = ac.get("threshold_operator", ">=")

    # 업종 매칭 확인
    # '제1호부터 제27호까지 외의 사업' → 일반 조항: 모든 업종에 적용
    is_general = "외의 사업" in industry_name
    is_matched_industry = (
        is_general or _match_industry(ksic_code, industry_name)
    )

    if not is_matched_industry:
        return None

    # 수치 조건 평가
    if operator == ">=":
        passes = employee_count >= threshold
    elif operator == ">":
        passes = employee_count > threshold
    elif operator == "<=":
        passes = employee_count <= threshold
    elif operator == "<":
        passes = employee_count < threshold
    else:
        passes = False

    if not passes:
        return None

    return {
        "condition_id": ac["id"],
        "industry_name": industry_name,
        "threshold_field": ac.get("threshold_field"),
        "threshold_operator": operator,
        "threshold_value": threshold,
        "threshold_unit": ac.get("threshold_unit"),
        "raw_condition": ac.get("raw_condition"),
        "is_general_clause": is_general,
    }


class SafetyManagerPilotResult(BaseModel):
    facility_id: str
    employee_count: int
    ksic_code: str
    sector: str
    verdict: str                    # REQUIRED / NOT_REQUIRED / UNKNOWN
    required_count: int             # 선임 필요 인원 (단순 평가, 0=해당 없음)
    matched_conditions: List[dict]  # 매칭된 appendix_condition 목록
    evaluation_note: str
    pilot_version: str = "WO-D-004B-PILOT-v1"


@router.get("/evaluate", response_model=SafetyManagerPilotResult)
def evaluate_safety_manager(
    facility_id: str = Query(..., description="factories.id"),
):
    """D-004B 파일럿: 안전관리자 선임 의무 판정.

    appendix_condition 별표3 7건 기반.
    KSIC + 상시근로자 수 + 업종명 텍스트 매칭 사용.
    """
    supabase = get_supabase()

    # 1) 사업장 프로필 로드
    fac_res = (
        supabase.table("factories")
        .select("id, sector, employee_count, ksic_code")
        .eq("id", facility_id)
        .single()
        .execute()
    )
    fac = fac_res.data
    if not fac:
        return SafetyManagerPilotResult(
            facility_id=facility_id,
            employee_count=0,
            ksic_code="",
            sector="",
            verdict="UNKNOWN",
            required_count=0,
            matched_conditions=[],
            evaluation_note="사업장 정보를 찾지 못함",
        )

    employee_count = int(fac.get("employee_count") or 0)
    ksic_code = str(fac.get("ksic_code") or "")
    sector = str(fac.get("sector") or "")

    # 2) appendix_condition 전체 로드 (현재 7건)
    ac_res = (
        supabase.table("appendix_condition")
        .select("*")
        .eq("condition_type", "안전관리자_선임기준")
        .eq("sector", "INDUSTRIAL")
        .execute()
    )
    conditions = ac_res.data or []

    # 3) 각 조건과 비교
    matched = []
    for ac in conditions:
        result = _evaluate_condition(ac, employee_count, ksic_code)
        if result:
            matched.append(result)

    # 4) 판정
    if not matched:
        verdict = "NOT_REQUIRED"
        required_count = 0
        note = (
            f"employee_count={employee_count}, ksic={ksic_code}: "
            f"어떤 별표3 조건에도 해당하지 않음"
        )
    else:
        verdict = "REQUIRED"
        # 여러 조건 매칭 시 업종별 친화 과 일반 조항 구분
        specific = [m for m in matched if not m["is_general_clause"]]
        general = [m for m in matched if m["is_general_clause"]]
        # 업종 특이 조항이 있으면 우선, 없으면 일반 조항
        primary = specific if specific else general
        # 가장 높은 threshold가 매칭된 것 → 요구 인원은 해당 threshold로 판정
        # (실제 선임 필요 수는 raw_condition에 포함되어 있으나 파일럿에서는 단순 집계)
        max_threshold_match = max(primary, key=lambda x: x["threshold_value"])
        required_count = 1 if max_threshold_match["threshold_value"] < 500 else 2
        note = (
            f"employee_count={employee_count}, ksic={ksic_code}: "
            f"{len(matched)}개 조건 매칭 → 안전관리자 {required_count}명 선임 필요"
        )

    return SafetyManagerPilotResult(
        facility_id=facility_id,
        employee_count=employee_count,
        ksic_code=ksic_code,
        sector=sector,
        verdict=verdict,
        required_count=required_count,
        matched_conditions=matched,
        evaluation_note=note,
    )
