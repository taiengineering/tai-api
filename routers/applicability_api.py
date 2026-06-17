"""WO-V4-PHASE2-001: ApplicabilityCondition 파일럿 API

금지:
  obligation_result 생성 금지
  diagnosis_result 생성 금지
  stored_diagnosis_result 생성 금지
  안전관리자 시올 외 확장 금지
  pilot_safety_manager_api 삭제 금지
"""
from __future__ import annotations

from typing import Dict, List, Any, Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase
from services.applicability_condition_service import (
    build_applicability_condition,
    evaluate_facility,
    aggregate_verdict,
)
from services.facility_profile_service import build_facility_profile

router = APIRouter(
    prefix="/applicability",
    tags=["Phase2 ApplicabilityCondition"],
)


# ---------------------------------------------------------------------------
# SC-01: appendix_condition → ApplicabilityCondition 변환 + 저장
# ---------------------------------------------------------------------------

@router.post("/conditions/build")
def build_conditions():
    """SC-01: appendix_condition 7건 → ApplicabilityCondition 7건.

    이미 저장된 경우 반환만. 중복 생성 안 함.
    """
    supabase = get_supabase()

    # appendix_condition 로드
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

        # 이미 있는지 확인
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


# ---------------------------------------------------------------------------
# SC-02~06: FacilityProfile × ApplicabilityCondition 평가
# ---------------------------------------------------------------------------

@router.get("/evaluate/{factory_id}")
def evaluate(
    factory_id: str,
    save: bool = Query(False, description="결과 DB 저장 여부"),
):
    """SC-02~06: C1 파일럿 평가.

    FacilityProfile(factories 실시간 Projection) × ApplicabilityCondition.
    Obligation/Diagnosis 생성 없음.
    """
    supabase = get_supabase()

    # 1) factories 로드 (Source of Record)
    fac_res = (
        supabase.table("factories")
        .select("*")
        .eq("id", factory_id)
        .single()
        .execute()
    )
    if not fac_res.data:
        raise HTTPException(status_code=404, detail="사업장 미존재")

    # 2) FacilityProfile Projection
    profile = build_facility_profile(fac_res.data)

    # 3) ApplicabilityCondition 로드
    cond_res = (
        supabase.table("applicability_conditions")
        .select("*")
        .eq("status", "ACTIVE")
        .execute()
    )
    conditions = cond_res.data or []
    if not conditions:
        raise HTTPException(status_code=404, detail="ApplicabilityCondition 없음. POST /applicability/conditions/build 먼저 호출")

    # 4) C1 평가
    eval_results = evaluate_facility(profile, conditions)

    # 5) 종합 verdict
    verdict = aggregate_verdict(eval_results)

    # 6) Golden Reference 비교 (pilot과 동일 판정인지)
    pilot_verdict = "REQUIRED" if any(
        r["evaluation_result"] == "MATCH" for r in eval_results
    ) else "UNKNOWN" if any(
        r["evaluation_result"] == "UNKNOWN" for r in eval_results
    ) else "NOT_REQUIRED"

    sc04_pass = verdict["verdict"] == pilot_verdict

    # 7) SC-06: 빈 사업장 검증
    all_unknown = all(r["evaluation_result"] == "UNKNOWN" for r in eval_results)
    input_state = (profile.get("workforce", {})
                   .get("regular_workers", {}).get("state", "UNKNOWN"))
    sc06_applicable = (input_state == "UNKNOWN" and all_unknown)

    # 8) 선택적 저장
    if save and eval_results:
        rows = []
        fp_res = (
            supabase.table("facility_profiles")
            .select("id")
            .eq("factory_id", factory_id)
            .order("profile_version", desc=True)
            .limit(1)
            .execute()
        )
        fp_id = fp_res.data[0]["id"] if fp_res.data else None

        for r in eval_results:
            rows.append({
                "factory_id": factory_id,
                "facility_profile_id": fp_id,
                "condition_id": str(r["condition_id"]) if r.get("condition_id") else None,
                "metric": r["metric"],
                "input_state": r["input_state"],
                "input_value": r["input_value"],
                "evaluation_result": r["evaluation_result"],
                "evaluation_reason": r["evaluation_reason"],
                "pilot_verdict": pilot_verdict,
                "pilot_match": sc04_pass,
            })
        supabase.table("applicability_evaluation_result").insert(rows).execute()

    return {
        "factory_id": factory_id,
        "facility_sector": profile.get("sector"),
        "ksic_code": profile.get("ksic_code"),
        "regular_workers": profile.get("workforce", {}).get("regular_workers"),
        # 판정
        "verdict": verdict["verdict"],
        "required_count": verdict["required_count"],
        "matched_conditions": verdict["matched_conditions"],
        # SC 검증
        "sc02_match_count": sum(1 for r in eval_results if r["evaluation_result"] == "MATCH"),
        "sc03_verdict": verdict["verdict"],
        "sc04_pilot_match": sc04_pass,
        "sc05_unknown_count": sum(1 for r in eval_results if r["evaluation_result"] == "UNKNOWN"),
        "sc06_all_unknown_when_no_input": sc06_applicable,
        # 상세
        "evaluation_details": eval_results,
    }
