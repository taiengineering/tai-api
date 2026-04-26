"""
price_commission CRUD — prefix /price-commission (main.py에서 지정).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from db.supabase_client import get_supabase
from routers.matching_deps import _require_admin
from schemas.matching import CalcBody, CommissionBody
from services.matching_helpers import now_iso

commission_router = APIRouter()


@commission_router.get("")
def list_commissions(
    service_type: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: dict = Depends(_require_admin),
):
    """어드민: 수수료율 목록 — GET /price-commission"""
    supabase = get_supabase()
    q = supabase.table("price_commission").select("*")
    if service_type:
        q = q.eq("service_type", service_type)
    if is_active is not None:
        q = q.eq("is_active", is_active)
    res = q.order("service_type").order("period_min").order("amount_min").execute()
    return {"status": "success", "data": {"items": res.data or []}}


@commission_router.post("")
def create_commission(
    body: CommissionBody,
    current_user: dict = Depends(_require_admin),
):
    """수수료율 신규 등록 — POST /price-commission"""
    supabase = get_supabase()
    now = now_iso()
    res = supabase.table("price_commission").insert({
        "service_type": body.service_type,
        "fee_rate": body.fee_rate,
        "period_min": body.period_min,
        "period_max": body.period_max,
        "amount_min": body.amount_min,
        "amount_max": body.amount_max,
        "description": body.description,
        "is_active": body.is_active,
        "created_at": now,
        "updated_at": now,
    }).execute()
    return {"status": "success", "data": res.data[0] if res.data else {}}


@commission_router.post("/calculate")
def calculate_commission(body: CalcBody):
    """
    수수료 미리 계산 (로그인 불필요 — 견적 확인용)
    POST /price-commission/calculate
    """
    supabase = get_supabase()
    period_days = (body.period_months or 1) * 30

    res = (
        supabase.table("price_commission")
        .select("fee_rate, period_min, period_max, amount_min, amount_max, description")
        .eq("service_type", body.service_type)
        .eq("is_active", True)
        .execute()
    )

    fee_rate = 10.0
    if res.data:
        matched = False
        for row in res.data:
            p_min = row.get("period_min") or 0
            p_max = row.get("period_max") or 999_999
            a_min = row.get("amount_min") or 0
            a_max = row.get("amount_max") or 9_999_999_999
            if p_min <= period_days <= p_max and a_min <= body.contract_amount <= a_max:
                fee_rate = float(row["fee_rate"])
                matched = True
                break
        if not matched:
            fee_rate = float(res.data[0]["fee_rate"])

    tai_fee = round(body.contract_amount * fee_rate / 100)
    expert_amt = body.contract_amount - tai_fee

    return {
        "status": "success",
        "data": {
            "contract_amount": body.contract_amount,
            "fee_rate": fee_rate,
            "tai_fee_amount": tai_fee,
            "expert_amount": expert_amt,
        },
    }


@commission_router.patch("/{commission_id}")
def update_commission(
    commission_id: str,
    body: CommissionBody,
    current_user: dict = Depends(_require_admin),
):
    """수수료율 수정 — PATCH /price-commission/{id}"""
    supabase = get_supabase()
    supabase.table("price_commission").update({
        "service_type": body.service_type,
        "fee_rate": body.fee_rate,
        "period_min": body.period_min,
        "period_max": body.period_max,
        "amount_min": body.amount_min,
        "amount_max": body.amount_max,
        "description": body.description,
        "is_active": body.is_active,
        "updated_at": now_iso(),
    }).eq("id", commission_id).execute()
    return {"status": "success", "message": "수수료율이 수정되었습니다."}


@commission_router.delete("/{commission_id}")
def deactivate_commission(
    commission_id: str,
    current_user: dict = Depends(_require_admin),
):
    """수수료율 비활성화 (소프트 삭제) — DELETE /price-commission/{id}"""
    supabase = get_supabase()
    supabase.table("price_commission").update({
        "is_active": False,
        "updated_at": now_iso(),
    }).eq("id", commission_id).execute()
    return {"status": "success", "message": "비활성화 처리되었습니다."}
