"""Phase 4: Real Facility Validation API

실제 사업장 데이터로 신규 엔진 검증.
◇ 배치 평가: 여러 사업장 한 번에
◇ 상식성 확인: verdict가 기대 범위 안에 있는가
◇ 이상 탐지: UNKNOWN이 너무 많거나 예상밖 결과

금지:
  obligation_result 생성
  Track A 수정
  안전관리자 외 법령 확장
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from services.facility_profile_service import build_facility_profile
from services.applicability_condition_service import evaluate_facility, aggregate_verdict
from services.condition_scope_service import evaluate_scopes

router = APIRouter(
    prefix="/validation",
    tags=["Phase4 Real Facility Validation"],
)


class FacilityResult(BaseModel):
    factory_id: str
    sector: str
    ksic_code: str | None
    employee_count: int | None
    employee_state: str
    verdict: str
    required_count: int
    match_count: int
    not_applicable_count: int
    unknown_count: int
    anomaly: str | None  # 상식에 맞지 않는 결과 설명


class BatchValidationResult(BaseModel):
    total: int
    required: int
    not_required: int
    unknown: int
    anomaly_count: int
    results: List[FacilityResult]


def _detect_anomaly(result: dict, sector: str, ksic_code: str | None, employee_count: int | None) -> str | None:
    """\uc0c1\uc2dd\uc801\uc73c\ub85c \uc774\uc0c1\ud55c \uacb0\uacfc \ud0d0\uc9c0."""
    verdict = result["verdict"]
    required_count = result["required_count"]

    # 50\uba85 \uc774\uc0c1\uc778\ub370 NOT_REQUIRED
    if employee_count and employee_count >= 50 and verdict == "NOT_REQUIRED":
        return f"employee={employee_count}\uba85\uc778\ub370 NOT_REQUIRED: \ud310\ub2e8 \uc7ac\ud655\uc778 \ud544\uc694"

    # 50\uba85 \ubbf8\ub9cc\uc778\ub370 REQUIRED
    if employee_count and employee_count < 50 and verdict == "REQUIRED":
        return f"employee={employee_count}\uba85\uc778\ub370 REQUIRED: \ud310\ub2e8 \uc7ac\ud655\uc778 \ud544\uc694"

    # \uc2dd\ub8cc\ud488 \uc81c\uc870\uc5c5(C10) 600\uba85\uc778\ub370 required_count=1
    if ksic_code and ksic_code.startswith("C10") and employee_count and employee_count >= 500:
        if required_count == 1:
            return f"\uc2dd\ub8cc\ud488\uc81c\uc870 C10 {employee_count}\uba85 \u2192 required_count=2\uc774\uc5b4\uc57c \ud568\uc778\ub370 1\uba85"

    # UNKNOWN\uc778\ub370 employee\uc774 \uc788\ub294 \uacbd\uc6b0
    if verdict == "UNKNOWN" and employee_count is not None:
        return f"employee={employee_count}\uba85 \uc785\ub825\ub418\uc5c8\ub294\ub370 UNKNOWN: scope \ub610\ub294 \ub370\uc774\ud130 \ubb38\uc81c"

    return None


@router.get("/batch", response_model=BatchValidationResult)
def batch_validate(
    sector: str = Query(None, description="INDUSTRIAL | CONSTRUCTION | BUILDING"),
    limit: int = Query(30, ge=1, le=100),
    min_employees: int = Query(None),
):
    """\uc2e4\uc81c \uc0ac\uc5c5\uc7a5 \ub370\uc774\ud130\ub85c \uc2e0\uaddc \uc5d4\uc9c4 \ubc30\uce58 \uac80\uc99d.

    Phase 4 \ubaa9\ud45c: 30\uac1c \uc0ac\uc5c5\uc7a5\uc5d0\uc11c verdict\uac00 \uc0c1\uc2dd\uc801\uc778\uc9c0 \ud655\uc778.
    Track A \uc218\uc815 \uc5c6\uc74c.
    """
    supabase = get_supabase()

    # \uc0ac\uc5c5\uc7a5 \ubaa9\ub85d \ub85c\ub4dc
    q = (
        supabase.table("factories")
        .select("id, sector, ksic_code, employee_count")
    )
    if sector:
        q = q.eq("sector", sector)
    if min_employees:
        q = q.gte("employee_count", min_employees)

    q = q.not_.is_("employee_count", "null").limit(limit)
    fac_res = q.execute()
    factories = fac_res.data or []

    # ApplicabilityCondition + Scope \ub85c\ub4dc (\ubbf8\ub9ac \ub85c\ub4dc)
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
        # factories \uc6d0\ubcf8 \ub85c\ub4dc (FacilityProfile Projection)
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

        # C1 \ud3c9\uac00 (Scope + \uc218\uce58)
        eval_results = []
        for cond in conditions:
            scopes = cond.get("condition_scopes") or []
            scope_result, scope_reason = evaluate_scopes(scopes, profile)

            if scope_result == "NOT_APPLICABLE":
                eval_results.append({
                    "condition_id": cond.get("id"),
                    "evaluation_result": "NOT_APPLICABLE",
                    "threshold_value": cond.get("threshold_value"),
                    "required_count": cond.get("required_count"),
                })
                continue

            if scope_result == "UNKNOWN":
                eval_results.append({
                    "condition_id": cond.get("id"),
                    "evaluation_result": "UNKNOWN",
                    "threshold_value": cond.get("threshold_value"),
                    "required_count": cond.get("required_count"),
                })
                continue

            from services.applicability_condition_service import evaluate_condition
            num_result, _ = evaluate_condition(regular_workers, cond)
            eval_results.append({
                "condition_id": cond.get("id"),
                "evaluation_result": num_result,
                "threshold_value": cond.get("threshold_value"),
                "required_count": cond.get("required_count"),
            })

        verdict = aggregate_verdict(eval_results)
        employee_count = fac.get("employee_count")
        ksic_code = fac.get("ksic_code")

        anomaly = _detect_anomaly(
            verdict, fac.get("sector", ""), ksic_code, employee_count
        )
        if anomaly:
            counts["anomaly"] += 1

        v = verdict["verdict"]
        counts[v if v in counts else "UNKNOWN"] += 1

        results.append(FacilityResult(
            factory_id=str(fac["id"]),
            sector=fac.get("sector", ""),
            ksic_code=ksic_code,
            employee_count=employee_count,
            employee_state=regular_workers.get("state", "UNKNOWN"),
            verdict=v,
            required_count=verdict["required_count"],
            match_count=sum(1 for r in eval_results if r["evaluation_result"] == "MATCH"),
            not_applicable_count=sum(1 for r in eval_results if r["evaluation_result"] == "NOT_APPLICABLE"),
            unknown_count=sum(1 for r in eval_results if r["evaluation_result"] == "UNKNOWN"),
            anomaly=anomaly,
        ))

    return BatchValidationResult(
        total=len(results),
        required=counts["REQUIRED"],
        not_required=counts["NOT_REQUIRED"],
        unknown=counts["UNKNOWN"],
        anomaly_count=counts["anomaly"],
        results=results,
    )
