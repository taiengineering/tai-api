"""Phase 2 + Phase 3: ApplicabilityCondition 파일럿 API

Phase 3: Condition Scope Layer 연결

금지:
  obligation_result 생성 금지
  diagnosis_result 생성 금지
  is_general 금지
  scope_type 텍스트 런타임 해석 금지
  안전관리자 외 확장 금지
  pilot_safety_manager_api 삭제 금지
"""
from __future__ import annotations

from typing import Dict, List, Any

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase
from services.applicability_condition_service import (
    build_applicability_condition,
    evaluate_condition,
    aggregate_verdict,
)
from services.condition_scope_service import evaluate_scopes
from services.facility_profile_service import build_facility_profile

router = APIRouter(
    prefix="/applicability",
    tags=["Phase2+3 ApplicabilityCondition"],
)


@router.post("/conditions/build")
def build_conditions():
    """SC-01: appendix_condition 7건 → ApplicabilityCondition 7건."""
    supabase = get_supabase()

    ac_res = (
        supabase.table("appendix_condition")
        .select("*, law_appendix(appendix_no, appendix_title, law_master(law_name))")
        .eq("condition_type", "안전관리자_선임기준")
        .eq("sector", "INDUSTRIAL")
        .execute()
    )
    acs = ac_res.data or []

    results = []
    for ac in acs:
        lap = ac.get("law_appendix") or {}
        lm = lap.get("law_master") or {}
        law_name = lm.get("law_name", "")
        appendix_no = lap.get("appendix_no", "")

        existing = (
            supabase.table("applicability_conditions")
            .select("id")
            .eq("appendix_condition_id", str(ac["id"]))
            .execute()
        )
        if existing.data:
            results.append({"status": "already_exists", "appendix_condition_id": str(ac["id"])})
            continue

        cond_dict = build_applicability_condition(ac, law_name, appendix_no)
        insert_res = (
            supabase.table("applicability_conditions")
            .insert(cond_dict)
            .execute()
        )
        saved = insert_res.data[0]
        results.append({"status": "created", "condition_id": str(saved["id"])})

    total = len(acs)
    created = sum(1 for r in results if r["status"] == "created")
    existing_count = sum(1 for r in results if r["status"] == "already_exists")

    return {
        "sc01_pass": (created + existing_count) == total,
        "total_appendix": total,
        "created": created,
        "already_exists": existing_count,
        "details": results,
    }


@router.get("/evaluate/{factory_id}")
def evaluate(
    factory_id: str,
    save: bool = Query(False),
):
    """Phase 3: Scope 필터 포함 C1 평가.

    순서:
    1) FacilityProfile Projection
    2) ApplicabilityCondition + condition_scopes 로드
    3) Scope 평가 먼저 (NOT_APPLICABLE 이면 수치 비교 건너끈)
    4) 수치 비교 (PRESENT vs threshold)
    5) verdict 집계
    """
    supabase = get_supabase()

    fac_res = (
        supabase.table("factories")
        .select("*")
        .eq("id", factory_id)
        .single()
        .execute()
    )
    if not fac_res.data:
        raise HTTPException(status_code=404, detail="사업장 미존재")

    profile = build_facility_profile(fac_res.data)

    # ApplicabilityCondition + condition_scopes 로드
    cond_res = (
        supabase.table("applicability_conditions")
        .select("*, condition_scopes(*)")
        .eq("status", "ACTIVE")
        .execute()
    )
    conditions = cond_res.data or []
    if not conditions:
        raise HTTPException(
            status_code=404,
            detail="ApplicabilityCondition 없음. POST /applicability/conditions/build 먼저"
        )

    eval_results = []
    for cond in conditions:
        scopes = cond.get("condition_scopes") or []

        # 1) Scope 평가 먼저
        scope_result, scope_reason = evaluate_scopes(scopes, profile)

        if scope_result == "NOT_APPLICABLE":
            eval_results.append({
                "condition_id": cond.get("id"),
                "metric": "METRIC:EMPLOYEE_COUNT",
                "input_state": None,
                "input_value": None,
                "evaluation_result": "NOT_APPLICABLE",
                "evaluation_reason": f"[SCOPE] {scope_reason}",
                "industry_name": cond.get("industry_name"),
                "threshold_value": cond.get("threshold_value"),
                "operator": cond.get("operator"),
                "required_count": cond.get("required_count"),
                "scope_result": scope_result,
                "scope_reason": scope_reason,
            })
            continue

        if scope_result == "UNKNOWN":
            eval_results.append({
                "condition_id": cond.get("id"),
                "metric": "METRIC:EMPLOYEE_COUNT",
                "input_state": None,
                "input_value": None,
                "evaluation_result": "UNKNOWN",
                "evaluation_reason": f"[SCOPE] {scope_reason}",
                "industry_name": cond.get("industry_name"),
                "threshold_value": cond.get("threshold_value"),
                "operator": cond.get("operator"),
                "required_count": cond.get("required_count"),
                "scope_result": scope_result,
                "scope_reason": scope_reason,
            })
            continue

        # 2) Scope 통과 → 수치 비교
        regular_workers = (
            profile.get("workforce", {})
            .get("regular_workers", {"state": "UNKNOWN", "value": None})
        )
        num_result, num_reason = evaluate_condition(regular_workers, cond)

        eval_results.append({
            "condition_id": cond.get("id"),
            "metric": "METRIC:EMPLOYEE_COUNT",
            "input_state": regular_workers.get("state"),
            "input_value": regular_workers.get("value"),
            "evaluation_result": num_result,
            "evaluation_reason": f"[SCOPE_OK] {scope_reason} | [NUM] {num_reason}",
            "industry_name": cond.get("industry_name"),
            "threshold_value": cond.get("threshold_value"),
            "operator": cond.get("operator"),
            "required_count": cond.get("required_count"),
            "scope_result": scope_result,
            "scope_reason": scope_reason,
        })

    verdict = aggregate_verdict(eval_results)

    pilot_verdict = (
        "REQUIRED" if any(r["evaluation_result"] == "MATCH" for r in eval_results)
        else "UNKNOWN" if any(r["evaluation_result"] == "UNKNOWN" for r in eval_results)
        else "NOT_REQUIRED"
    )
    sc04_pass = verdict["verdict"] == pilot_verdict

    all_unknown = all(r["evaluation_result"] == "UNKNOWN" for r in eval_results)
    input_state = (
        profile.get("workforce", {})
        .get("regular_workers", {}).get("state", "UNKNOWN")
    )
    sc06_applicable = input_state == "UNKNOWN" and all_unknown

    # SC-05: 새 Scope Type 추가 시 C1 코드 수정 없음을 나타내는 메타 필드
    scope_types_used = list({
        s["scope_type"]
        for c in conditions
        for s in (c.get("condition_scopes") or [])
    })

    return {
        "factory_id": factory_id,
        "facility_sector": profile.get("sector"),
        "ksic_code": profile.get("ksic_code"),
        "regular_workers": (
            profile.get("workforce", {})
            .get("regular_workers")
        ),
        "verdict": verdict["verdict"],
        "required_count": verdict["required_count"],
        "matched_conditions": verdict["matched_conditions"],
        "sc02_match_count": sum(
            1 for r in eval_results if r["evaluation_result"] == "MATCH"
        ),
        "sc03_verdict": verdict["verdict"],
        "sc04_pilot_match": sc04_pass,
        "sc05_scope_types_used": scope_types_used,
        "sc05_note": "condition_scopes에 데이터만 추가하면 C1 코드 수정 없이 확장 가능",
        "sc06_all_unknown_when_no_input": sc06_applicable,
        "not_applicable_count": sum(
            1 for r in eval_results if r["evaluation_result"] == "NOT_APPLICABLE"
        ),
        "evaluation_details": eval_results,
    }
