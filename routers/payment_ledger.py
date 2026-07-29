"""결제 원장 결선 라우터 (WO-7 PaymentLedger).

Goal: G-ms4je4z3-33eada (구축 이어받기 G-ms5pdquz-9e76e5)
- 기존 payment_ops.py는 불변. WO-1~4 서비스(refund/credit/invoice)를 결제에 결선.
- 얇은 위임: 각 서비스가 payment_id로 자기 검증·감사. 로직 중복 금지.
- prefix /payments (기존 결제 네임스페이스와 동일).

[2026-07-29 P0-1] 환불 라우트 정본 단일화:
  기존 이 파일의 POST /{id}/refund, POST /{id}/refund/partial 은
  routers/payment.py 의 동일/유사 라우트에 의해 선등록 그림자 처리(사문)였다.
  프론트가 이 파일 스펙(body.by)을 보고 구현하면 처리자 정보가 조용히 누락되는
  위험이 있어 제거한다. 환불 정본 = routers/payment.py:
    POST /payments/{id}/refund          body: reason, cancelled_by
    POST /payments/{id}/partial-refund  body: amount, reason, cancelled_by
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["결제원장"])


# ── 요청 스키마 ──────────────────────────────────────────────────────
class CreditGrantBody(BaseModel):
    # diagnosis_purchase_id가 있으면 전환크레딧, 없으면 수동 지급(amount 필수)
    diagnosis_purchase_id: Optional[str] = None
    amount: Optional[int] = None
    memo: Optional[str] = None
    by: Optional[str] = None


class TaxInvoiceBody(BaseModel):
    corpNum: str
    corpName: str
    ceoName: str
    email: Optional[str] = None
    addr: Optional[str] = None
    bizType: Optional[str] = None
    bizClass: Optional[str] = None
    by: Optional[str] = None


class CashReceiptBody(BaseModel):
    trade_usage: str           # 소득공제용 | 지출증빙용
    identity_num: str          # 휴대폰/주민번호(소득공제용) 또는 사업자번호(지출증빙용)
    by: Optional[str] = None


# ── 환불 결선 ────────────────────────────────────────────────────────
# [2026-07-29 P0-1] 이 파일의 환불 라우트는 routers/payment.py 로 단일화되어 제거됨.
#   정본: POST /payments/{id}/refund  (body: reason, cancelled_by)
#         POST /payments/{id}/partial-refund  (body: amount, reason, cancelled_by)


# ── 전환크레딧 결선 (credit_svc) ─────────────────────────────────────
@router.post("/{payment_id}/credit")
def grant_credit(payment_id: str, body: CreditGrantBody):
    """전환크레딧 발행. diagnosis_purchase_id 있으면 진단전환, 없으면 수동지급."""
    from services.credit_svc import CreditError, grant, grant_from_diagnosis
    try:
        if body.diagnosis_purchase_id:
            credit_id = grant_from_diagnosis(body.diagnosis_purchase_id, created_by=body.by)
        else:
            if not body.amount or body.amount <= 0:
                raise HTTPException(status_code=400, detail="수동 지급은 amount가 필요합니다.")
            pay = (
                get_supabase().table("payments").select("company_id")
                .eq("id", payment_id).limit(1).execute()
            )
            if not pay.data:
                raise HTTPException(status_code=404, detail="결제 건을 찾을 수 없습니다.")
            credit_id = grant(
                company_id=pay.data[0]["company_id"], amount=body.amount,
                source="MANUAL", source_ref=payment_id, expires_at=None,
                created_by=body.by, memo=body.memo,
            )
        return {"status": "success", "data": {"credit_id": credit_id}}
    except CreditError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ── 증빙 결선 (invoice_svc) ──────────────────────────────────────────
@router.post("/{payment_id}/invoice/tax")
def issue_tax(payment_id: str, body: TaxInvoiceBody):
    """세금계산서 발행 (팝빌)."""
    from services.invoice_svc import InvoiceError, issue_tax_invoice
    try:
        invoicee = {
            "corpNum": body.corpNum, "corpName": body.corpName, "ceoName": body.ceoName,
            "email": body.email, "addr": body.addr,
            "bizType": body.bizType, "bizClass": body.bizClass,
        }
        res = issue_tax_invoice(payment_id, invoicee, created_by=body.by)
        return {"status": "success", "data": res}
    except InvoiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/{payment_id}/invoice/cash")
def issue_cash(payment_id: str, body: CashReceiptBody):
    """현금영수증 발행 (팝빌)."""
    from services.invoice_svc import InvoiceError, issue_cash_receipt
    try:
        res = issue_cash_receipt(
            payment_id, trade_usage=body.trade_usage,
            identity_num=body.identity_num, created_by=body.by,
        )
        return {"status": "success", "data": res}
    except InvoiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ── 결제 원장 통합 조회 ──────────────────────────────────────────────
@router.get("/{payment_id}/ledger")
def get_payment_ledger(payment_id: str):
    """결제 1건의 환불·크레딧·증빙 통합 조회."""
    supabase = get_supabase()
    pay = (
        supabase.table("payments")
        .select("id, company_id, contract_id, status_code, total_amount, product_type, paid_at")
        .eq("id", payment_id).limit(1).execute()
    )
    if not pay.data:
        raise HTTPException(status_code=404, detail="결제 건을 찾을 수 없습니다.")
    payment = pay.data[0]

    refunds = (
        supabase.table("refunds")
        .select("id, refund_type, amount, status, reason_text, created_at")
        .eq("payment_id", payment_id).order("created_at", desc=True).execute()
    ).data or []

    invoices = (
        supabase.table("tax_invoices")
        .select("id, doc_type, status, nts_confirm_num, total_amount, issued_at")
        .eq("payment_id", payment_id).order("created_at", desc=True).execute()
    ).data or []

    # 크레딧: source_ref=payment_id로 이 결제에서 파생된 것
    credits = (
        supabase.table("credits")
        .select("id, source, amount, balance, status, expires_at, created_at")
        .eq("source_ref", payment_id).order("created_at", desc=True).execute()
    ).data or []

    return {
        "status": "success",
        "data": {
            "payment": payment,
            "refunds": refunds,
            "invoices": invoices,
            "credits": credits,
            "refund_total": sum(int(r["amount"] or 0) for r in refunds if r.get("status") == "DONE"),
        },
    }
