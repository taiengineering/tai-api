"""결제 조회·수동처리·VBANK 상태 — /payments 보조 라우트 (payment.py 용량 분리).

[2026-07-30 #5 감사 완결성] 결제취소(PAYMENT_CANCEL)·수동활성화(PAYMENT_MANUAL_CONFIRM)를
  admin_ops_audit_logs 에 before/after·actor 로 기록한다(best-effort — 감사 실패가 본 처리를 막지 않음).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from db.supabase_client import get_supabase
from schemas.payment import CancelBody, ManualConfirmBody
from services import audit_svc
from services.payment_helpers import SAAS_PRODUCT_TYPES, calc_expired_at, now_iso

log = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["결제"])


@router.get("")
def list_payments(
    user_id: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
    status_code: Optional[str] = Query(None),
    service_status: Optional[str] = Query(None),
    product_type: Optional[str] = Query(None),
    plan_code: Optional[str] = Query(None),
    pg_method: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None, description="회원명 또는 회사명 검색"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    q = supabase.table("v_payments_list").select("*", count="exact")

    if user_id:
        q = q.eq("user_id", user_id)
    if company_id:
        q = q.eq("company_id", company_id)
    if status_code:
        q = q.eq("status_code", status_code)
    if service_status:
        q = q.eq("service_status", service_status)
    if product_type:
        q = q.eq("product_type", product_type)
    if plan_code:
        q = q.eq("plan_code", plan_code)
    if pg_method:
        q = q.eq("pg_method", pg_method)

    if keyword:
        q = q.or_(f"user_name.ilike.%{keyword}%,company_name.ilike.%{keyword}%")

    offset = (page - 1) * size
    res = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    total = res.count or 0
    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


@router.get("/expiring")
def list_expiring_payments(
    days: int = Query(30, ge=1, le=90),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    now = datetime.now(timezone.utc)
    deadline = (now + timedelta(days=days)).isoformat()
    q = supabase.table("v_payments_list").select(
        "id, user_id, user_name, company_name, product_type, plan_code, "
        "period_months, total_amount, status_code, service_status, paid_at, expired_at",
        count="exact",
    ).eq("status_code", "SUCCESS").lte("expired_at", deadline).gte("expired_at", now.isoformat())
    offset = (page - 1) * size
    res = q.order("expired_at", desc=False).range(offset, offset + size - 1).execute()
    total = res.count or 0
    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": total,
            "page": page,
            "size": size,
            "days_threshold": days,
        },
    }


@router.post("/manual/confirm")
def manual_confirm(body: ManualConfirmBody):
    supabase = get_supabase()
    now = now_iso()
    pay_res = (
        supabase.table("payments")
        .select("id, status_code, product_type, period_months")
        .eq("id", body.payment_id)
        .limit(1)
        .execute()
    )
    if not pay_res.data:
        raise HTTPException(status_code=404, detail="결제 레코드를 찾을 수 없습니다.")
    payment = pay_res.data[0]
    if payment["status_code"] == "SUCCESS":
        raise HTTPException(status_code=409, detail="이미 성공 처리된 결제입니다.")

    update_row: dict = {
        "status_code": "SUCCESS",
        "service_status": "ACTIVE",
        "paid_at": now,
        "memo": "수동 활성화 처리",
        "updated_at": now,
    }
    product_type = payment.get("product_type", "")
    period_months = payment.get("period_months")
    if product_type in SAAS_PRODUCT_TYPES and period_months:
        update_row["expired_at"] = calc_expired_at(now, period_months)

    supabase.table("payments").update(update_row).eq("id", body.payment_id).execute()
    supabase.table("contracts").update({"is_active": True, "updated_at": now}).eq("id", body.contract_id).execute()

    audit_svc.record(
        "PAYMENT_MANUAL_CONFIRM", "payment", entity_id=str(body.payment_id),
        actor_id=body.by,
        before={"status_code": payment["status_code"]},
        after={"status_code": "SUCCESS", "service_status": "ACTIVE",
               "contract_id": str(body.contract_id)},
    )

    try:
        from services.payment_post_process import on_payment_success_sync
        on_payment_success_sync(str(body.payment_id))
    except Exception as e:
        log.error("Payment post-process failed: %s", e)

    return {
        "status": "success",
        "message": "수동 활성화 완료",
        "data": {"payment_id": body.payment_id, "contract_id": body.contract_id},
    }


@router.post("/{payment_id}/cancel")
def cancel_payment(payment_id: str, body: CancelBody):
    supabase = get_supabase()
    now = now_iso()
    pay_res = (
        supabase.table("payments")
        .select("id, status_code, contract_id")
        .eq("id", payment_id)
        .limit(1)
        .execute()
    )
    if not pay_res.data:
        raise HTTPException(status_code=404, detail="결제 레코드를 찾을 수 없습니다.")
    payment = pay_res.data[0]
    if payment["status_code"] == "CANCELLED":
        raise HTTPException(status_code=409, detail="이미 취소된 결제입니다.")

    supabase.table("payments").update(
        {
            "status_code": "CANCELLED",
            "service_status": "ENDED",
            "cancel_reason": body.reason,
            "cancelled_at": now,
            "expired_at": None,
            "updated_at": now,
        }
    ).eq("id", payment_id).execute()

    contract_id = payment.get("contract_id")
    if contract_id:
        supabase.table("contracts").update({"is_active": False, "updated_at": now}).eq("id", contract_id).execute()

    audit_svc.record(
        "PAYMENT_CANCEL", "payment", entity_id=str(payment_id),
        actor_id=body.cancelled_by,
        before={"status_code": payment["status_code"], "contract_id": contract_id},
        after={"status_code": "CANCELLED", "service_status": "ENDED", "reason": body.reason},
    )

    return {
        "status": "success",
        "message": "취소 처리되었습니다.",
        "data": {"payment_id": payment_id, "status_code": "CANCELLED"},
    }


@router.get("/{payment_id}/vbank-status")
def get_vbank_status(payment_id: str):
    supabase = get_supabase()
    res = (
        supabase.table("payments")
        .select(
            "id, status_code, total_amount, "
            "vbank_number, vbank_bank, vbank_expires_at, "
            "vbank_depositor, vbank_confirmed_at, paid_at"
        )
        .eq("id", payment_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="결제 정보를 찾을 수 없습니다.")

    p = res.data[0]
    return {
        "status": "success",
        "data": {
            "payment_id": payment_id,
            "status_code": p["status_code"],
            "is_paid": p["status_code"] == "SUCCESS",
            "total_amount": p["total_amount"],
            "vbank_number": p.get("vbank_number"),
            "vbank_bank": p.get("vbank_bank"),
            "vbank_expires_at": p.get("vbank_expires_at"),
            "vbank_depositor": p.get("vbank_depositor"),
            "confirmed_at": p.get("vbank_confirmed_at"),
        },
    }
