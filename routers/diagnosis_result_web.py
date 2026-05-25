"""
routers/diagnosis_result_web.py — v1.0.0

유료 진단 결과 웹 조회 API (JSON)
  GET /diagnosis/paid-result/{public_token}

PDF가 아닌 웹 페이지용 JSON 반환.
paid-diagnosis-result.html에서 호출하여 인터랙티브 대시보드 렌더링.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnosis", tags=["진단결과웹"])

FREE_TIER_CODES = frozenset({
    "BUILDING_FREE", "INDUSTRY_FREE", "CONSTRUCTION_FREE",
    "free", "FREE",
})

SECTOR_LABEL = {
    "BUILDING": "건물", "INDUSTRY": "산업",
    "CONSTRUCTION": "건설", "MANUFACTURING": "산업(제조)",
}

RECOMMEND_PLAN = {
    "BUILDING_V2":          {"name": "건물 소형 플랜",  "price": "월 59,000원~"},
    "BUILDING_LARGE_V2":    {"name": "건물 대형 플랜",  "price": "월 145,000원~"},
    "INDUSTRY_V2":          {"name": "산업 STARTER",   "price": "월 79,000원~"},
    "INDUSTRY_STANDARD":    {"name": "산업 BUSINESS",  "price": "월 149,000원~"},
    "INDUSTRY_PREMIUM":     {"name": "산업 PRO",       "price": "월 249,000원~"},
    "CONSTRUCTION":         {"name": "건설 STANDARD",  "price": "월 145,000원~"},
    "CONSTRUCTION_PREMIUM": {"name": "건설 PREMIUM",   "price": "월 385,000원~"},
}


@router.get("/result/{public_token}")
def get_diagnosis_result_web(public_token: str):
    """
    무료/유료 공통 진단 결과 웹 조회.
    free-diagnosis-result.html → GET /diagnosis/result/{token}
    """
    return _build_result_payload(public_token, free_preview_limit=5)


@router.get("/paid-result/{public_token}")
def get_paid_result_web(public_token: str):
    """
    유료 진단 결과 웹 조회.
    paid-diagnosis-result.html에서 fetch하여 인터랙티브 대시보드 렌더링.
    """
    return _build_result_payload(public_token, free_preview_limit=None)


def _build_result_payload(public_token: str, free_preview_limit: Optional[int]) -> Dict[str, Any]:
    supabase = get_supabase()

    res = (
        supabase.table("anonymous_diagnosis_results")
        .select("id, public_token, tier_code, full_result, input_data, status, expires_at")
        .eq("public_token", public_token)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="진단 결과를 찾을 수 없습니다.")

    rec = res.data[0]

    if rec.get("status") != "ACTIVE":
        raise HTTPException(status_code=410, detail="비활성화된 진단 결과입니다.")

    tier_code = rec.get("tier_code") or ""
    is_free = tier_code in FREE_TIER_CODES or tier_code.endswith("_FREE") or "FREE" in tier_code.upper()

    full_result = rec.get("full_result") or {}
    input_data = rec.get("input_data") or {}

    sector = (full_result.get("sector") or input_data.get("sector") or "BUILDING").upper()
    sector_label = SECTOR_LABEL.get(sector, sector)

    rules_table = [r for r in (full_result.get("rules_table") or []) if isinstance(r, dict)]
    inspection_required = [r for r in (full_result.get("inspection_required") or []) if isinstance(r, dict)]
    appointment_required = [r for r in (full_result.get("appointment_required") or []) if isinstance(r, dict)]
    key_obligations = full_result.get("key_obligations") or []
    law_badges = full_result.get("law_badges") or []
    inspection_schedule = full_result.get("inspection_schedule_ready") or {}

    summary = full_result.get("summary") or {}
    total = full_result.get("applicable_count") or summary.get("total") or len(rules_table)
    risk_level = full_result.get("risk_level") or "MEDIUM"
    worker_count = input_data.get("workers") or input_data.get("worker_count") or 0

    law_groups: Dict[str, list] = {}
    for r in rules_table:
        law = r.get("law_name") or "기타"
        law_groups.setdefault(law, []).append(r)

    law_group_list = sorted(
        [{"law_name": k, "count": len(v), "rules": v} for k, v in law_groups.items()],
        key=lambda x: x["count"],
        reverse=True,
    )

    ob_counts: Dict[str, int] = {}
    for r in rules_table:
        ot = r.get("obligation_type") or "OTHER"
        ob_counts[ot] = ob_counts.get(ot, 0) + 1

    plan_info = RECOMMEND_PLAN.get(tier_code, {})
    company_name = input_data.get("company_name") or full_result.get("company_name") or "사업장"

    limit = free_preview_limit if is_free else None
    rules_out = rules_table[:limit] if limit else rules_table
    key_ob_out = key_obligations[:limit] if limit else key_obligations
    law_grp_out = law_group_list[:limit] if limit else law_group_list

    engine_version = full_result.get("engine_version") or "v3.0-runtime-compiler"

    return {
        "status": "success",
        "data": {
            "public_token": public_token,
            "tier_code": tier_code,
            "is_free": is_free,
            "sector": sector,
            "sector_label": sector_label,
            "company_name": company_name,
            "risk_level": risk_level,
            "risk_reason": full_result.get("risk_reason"),
            "applicable_count": total,
            "engine_version": engine_version,
            "summary": {
                "total": total,
                "inspection": summary.get("inspection") or len(inspection_required),
                "appointment": summary.get("appointment") or len(appointment_required),
                "action": summary.get("action") or 0,
                "report": (summary.get("report") or 0) + (summary.get("notify") or 0),
                "form_linked": summary.get("form_linked") or 0,
                "law_count": len(law_badges),
                "worker_count": worker_count,
                "csia_applicable": int(worker_count or 0) >= 5,
            },
            "obligation_counts": ob_counts,
            "rules_table": rules_out,
            "appointment_required": appointment_required,
            "inspection_required": inspection_required,
            "law_badges": law_badges,
            "key_obligations": key_ob_out,
            "inspection_schedule": inspection_schedule if not is_free else {},
            "law_groups": law_grp_out,
            "input_data": {
                "company_name": company_name,
                "business_no": input_data.get("business_no") or "",
                "ceo_name": input_data.get("ceo_name") or "",
                "address": input_data.get("address") or "",
                "worker_count": worker_count,
                "floor_area": input_data.get("floor_area") or input_data.get("total_floor_area") or "",
            },
            "recommended_plan": plan_info,
            "pdf_url": f"/diagnosis/report-pdf/{public_token}",
        },
    }
