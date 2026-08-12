"""SaaS 플랜 월요금 리졸버 — 기존계약 정기결제/기한연장용 (읽기 전용).

정본(SSOT) = price_master(service_type='SAAS'). 뷰/레거시 테이블 참조 안 함.
계약의 plan_code 를 price_master.tier_code 로 정규화(_V\\d+ 접미어 제거)해 월요금을 반환.

VAT: price_master.amount 는 공급가(vat_included=false). 두 값 모두 반환한다.
  - monthly_supply : 단건 기한연장(POST /payments/inicis/prepare)의 amount(=공급가). 백엔드가 VAT 가산.
  - monthly_total  : 정기결제(GET /payments/billing/pay?amount=)의 amount(=VAT 포함 총액).

CUSTOM(협의, amount=0) 또는 매핑 불가 → resolvable=false. 프론트는 결제 대신 담당자 문의 안내.
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from db.supabase_client import get_supabase

router = APIRouter(prefix="/payments", tags=["결제"])


def _normalize_tier(plan_code: str) -> str:
    """계약 plan_code → price_master tier_code 정규화. 예: INDUSTRY_STARTER_V2 → INDUSTRY_STARTER."""
    code = (plan_code or "").strip().upper()
    code = re.sub(r"_V\d+$", "", code)

    return code


@router.get("/plan-amount")
def resolve_plan_amount(
    contract_id: Optional[str] = Query(None, description="기존 계약 id (우선)"),
    plan_code: Optional[str] = Query(None, description="contract_id 없을 때 직접 지정"),
):
    """기존 계약의 SaaS 플랜 월요금 조회. price_master(SSOT) 기준."""
    sb = get_supabase()

    raw_plan = plan_code
    if contract_id:
        ct = (
            sb.table("contracts")
            .select("id, plan_code, service_type")
            .eq("id", contract_id)
            .limit(1)
            .execute()
        )
        if not ct.data:
            raise HTTPException(status_code=404, detail="계약을 찾을 수 없습니다.")
        raw_plan = ct.data[0].get("plan_code")

    if not raw_plan:
        return {"status": "success", "data": {"resolvable": False, "reason": "UNMAPPED", "plan_code_raw": None}}

    tier = _normalize_tier(raw_plan)

    res = (
        sb.table("price_master")
        .select("tier_code, sector, amount, vat_rate, display_name")
        .eq("service_type", "SAAS")
        .eq("is_active", True)
        .eq("tier_code", tier)
        .limit(1)
        .execute()
    )
    if not res.data:
        return {"status": "success", "data": {"resolvable": False, "reason": "UNMAPPED", "plan_code_raw": raw_plan}}

    row = res.data[0]
    amount = int(row.get("amount") or 0)
    is_custom = "CUSTOM" in tier or amount <= 0
    if is_custom:
        return {
            "status": "success",
            "data": {
                "resolvable": False,
                "reason": "CUSTOM",
                "plan_code": tier,
                "display_name": row.get("display_name"),
            },
        }

    vat_rate = float(row.get("vat_rate") or 0.1)
    sector = row.get("sector")
    monthly_total = int(round(amount * (1 + vat_rate)))

    return {
        "status": "success",
        "data": {
            "resolvable": True,
            "contract_id": contract_id,
            "plan_code": tier,
            "sector": sector,
            "product_type": f"SAAS_{sector}" if sector else None,
            "monthly_supply": amount,
            "monthly_total": monthly_total,
            "vat_rate": vat_rate,
            "display_name": row.get("display_name"),
            "is_custom": False,
        },
    }
