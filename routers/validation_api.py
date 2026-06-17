"""Phase 4: Real Facility Validation API

실제 사업장 데이터로 신규 엔진 검증.
배치 평가 + 상식성 확인 + 이상 탐지

금지:
  obligation_result 생성
  Track A 수정
  안전관리자 외 법령 확장
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from services.facility_profile_service import build_facility_profile
from services.applicability_condition_service import aggregate_verdict, evaluate_condition
from services.condition_scope_service import evaluate_scopes

router = APIRouter(
    prefix="/validation",
    tags=["Phase4 Real Facility Validation"],
)


class FacilityResult(BaseModel):
    factory_id: str
    sector: str
    ksic_code: Optional[str]
    employee_count: Optional[int]
    employee_state: str
    verdict: str
    required_count: int
    match_count: int
    not_applicable_count: int
    unknown_count: int
    anomaly: Optional[str]


class BatchValidationResult(BaseModel):
    total: int
    required: int
    not_required: int
    unknown: int
    anomaly_count: int
    results: List[FacilityResult]


def _detect_anomaly(
    verdict: str,
    required_count: int,
    ksic_code: Optional[str],
    employee_count: Optional[int],
) -> Optional[str]:
    """상식적으로 이상한 결과 탐지."""
    # 50명 이상인데 NOT_REQUIRED
    if employee_count and employee_count >= 50 and verdict == "NOT_REQUIRED":
        return f"employee={employee_count}명인데 NOT_REQUIRED: 판단 재확인 필요"

    # 50명 미만인데 REQUIRED
    if employee_count and employee_count < 50 and verdict == "REQUIRED":
        return f"employee={employee_count}명인데 REQUIRED: 판단 재확인 필요"

    # 식료품 C10 500명 이상인데 required_count=1
    if ksic_code and ksic_code.startswith("C10") and employee_count and employee_count >= 500:
        if required_count == 1:
            return f"식료품제조 C10 {employee_count}명 → required_count=2여야 함"

    # employee 있는데 UNKNOWN
    if verdict == "UNKNOWN" and employee_count is not None:
        return f"employee={employee_count}명 입력됐는데 UNKNOWN: scope 또는 데이터 문제"

    return None


@router.get("/batch", response_model=BatchValidationResult)
def batch_validate(
    sector: str = Query(None, description="INDUSTRIAL | CONSTRUCTION | BUILDING"),
    limit: int = Query(30, ge=1, le=100),
    min_employees: int = Query(None),
):
    """실제 사업장 데이터로 신규 엔진 배치 검증.

    Phase 4 목표: 30개 사업장에서 verdict가 상식적인지 확인.
    Track A 수정 없음.
    """
    supabase = get_supabase()

    # 사업장 목록 로드
    q = supabase.table("factories").select("id, sector, ksic_code, employee_count")
    if sector:
        q = q.eq("sector", sector)
    if min_employees:
        q = q.gte("employee_count", min_employees)

    # null 제외: neq 방식 사용
    q = q.not_.is_("employee_count", "null")
    q = q.limit(limit)

    try:
        fac_res = q.execute()
        factories = fac_res.data or []
    except Exception:
        # fallback: filter in Python
        fac_res_all = supabase.table("factories").select("id, sector, ksic_code, employee_count").limit(limit * 3).execute()
        all_facs = fac_res_all.data or []
        factories = [f for f in all_facs if f.get("employee_count") is not None]
        if sector:
            factories = [f for f in factories if f.get("sector") == sector]
        factories = factories[:limit]

    # ApplicabilityCondition + Scope 미리 로드
    cond_res = (
        supabase.table("applicability_conditions")
        .select("*, condition_scopes(*)")
        .eq("status", "ACTIVE")
        .execute()
    )
    conditions = cond_res.data or []

    results = []
    counts = {"REQUIRED": 0, "NOT_REQUIRED": 0, "UNKNOWN": 0, "anomaly": 0}

    for fac in factories:
        try:
            fac_full = (
                supabase.table("factories")
                .select("*")
                .eq("id", fac["id"])
                .single()
                .execute()
            )
            if not fac_full.data:
                continue

            profile = build_facility_profile(fac_full.data)
            regular_workers = (
                profile.get("workforce", {})
                .get("regular_workers", {"state": "UNKNOWN", "value": None})
            )

            # C1 평가
            eval_results = []
            for cond in conditions:
                scopes = cond.get("condition_scopes") or []
                scope_result, scope_reason = evaluate_scopes(scopes, profile)

                if scope_result == "NOT_APPLICABLE":
                    eval_results.append({
                        "evaluation_result": "NOT_APPLICABLE",
                        "threshold_value": cond.get("threshold_value"),
                        "required_count": cond.get("required_count"),
                    })
                    continue

                if scope_result == "UNKNOWN":
                    eval_results.append({
                        "evaluation_result": "UNKNOWN",
                        "threshold_value": cond.get("threshold_value"),
                        "required_count": cond.get("required_count"),
                    })
                    continue

                num_result, _ = evaluate_condition(regular_workers, cond)
                eval_results.append({
                    "evaluation_result": num_result,
                    "threshold_value": cond.get("threshold_value"),
                    "required_count": cond.get("required_count"),
                })

            verdict = aggregate_verdict(eval_results)
            v = verdict["verdict"]
            rc = verdict["required_count"]
            employee_count = fac.get("employee_count")
            ksic_code = fac.get("ksic_code")

            anomaly = _detect_anomaly(v, rc, ksic_code, employee_count)
            if anomaly:
                counts["anomaly"] += 1

            counts[v if v in counts else "UNKNOWN"] += 1

            results.append(FacilityResult(
                factory_id=str(fac["id"]),
                sector=fac.get("sector", ""),
                ksic_code=ksic_code,
                employee_count=employee_count,
                employee_state=regular_workers.get("state", "UNKNOWN"),
                verdict=v,
                required_count=rc,
                match_count=sum(1 for r in eval_results if r["evaluation_result"] == "MATCH"),
                not_applicable_count=sum(1 for r in eval_results if r["evaluation_result"] == "NOT_APPLICABLE"),
                unknown_count=sum(1 for r in eval_results if r["evaluation_result"] == "UNKNOWN"),
                anomaly=anomaly,
            ))
        except Exception:
            continue

    return BatchValidationResult(
        total=len(results),
        required=counts["REQUIRED"],
        not_required=counts["NOT_REQUIRED"],
        unknown=counts["UNKNOWN"],
        anomaly_count=counts["anomaly"],
        results=results,
    )
