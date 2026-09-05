"""결제 원장 결선 라우터 (WO-7 PaymentLedger + BACKEND-3 issuance).

[2026-08-15 P0-보정1 → BACKEND-3 실적용] 게이트/증빙 실발행 엔드포인트를
  role 001(_require_admin)로 실제 적용(이전 docstring 주장과 달리 get_current_user 만 쓰던 것 보정).
  증빙 발행은 invoice_svc 중앙 guard(저장금액·명시 supply_date·상호배타)를 공통 통과.
  신규: POST /payments/tax-invoice-requests/{request_id}/process (processor).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from routers.matching_deps import _require_admin

log = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["결제원장"])


class CreditGrantBody(BaseModel):
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
    supply_date: str            # BACKEND-3: 명시 공급일자(YYYY-MM-DD) 필수
    by: Optional[str] = None


class CashReceiptBody(BaseModel):
    trade_usage: str
    identity_num: str
    by: Optional[str] = None


class GateBody(BaseModel):
    channel: str
    confirm: bool = False
    by: Optional[str] = None
    note: Optional[str] = None


class ProcessBody(BaseModel):
    supply_date: str            # YYYY-MM-DD


# ── 실호출 게이트 상태 (조회는 인증만) ──
@router.get("/ops/live-flags")
def live_flags(current_user: dict = Depends(get_current_user)):
    try:
        from services.invoice_svc import invoice_live
        from services.refund_svc import refund_live
        return {"status": "success", "data": {"refund_live": refund_live(), "invoice_live": invoice_live()}}
    except Exception as e:  # noqa: BLE001
        log.warning("[LEDGER] live-flags 조회 실패: %s", e)
        return {"status": "success", "data": {"refund_live": False, "invoice_live": False}}


# ── 실행 게이트 해제 절차 (role 001) ──
@router.get("/ops/gate-readiness")
def gate_readiness_ep(current_user: dict = Depends(_require_admin)):
    from services.ops_gate_svc import readiness
    return {"status": "success", "data": readiness()}


@router.post("/ops/gate/activate")
def gate_activate(body: GateBody, current_user: dict = Depends(_require_admin)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail="활성화 확인(confirm)이 필요합니다.")
    from services.ops_gate_svc import GateError, set_gate
    try:
        res = set_gate(body.channel, True, by=current_user["id"], note=body.note)
    except GateError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"status": "success", "data": res}


@router.post("/ops/gate/deactivate")
def gate_deactivate(body: GateBody, current_user: dict = Depends(_require_admin)):
    from services.ops_gate_svc import GateError, set_gate
    try:
        res = set_gate(body.channel, False, by=current_user["id"], note=body.note)
    except GateError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"status": "success", "data": res}


# ── 전환크레딧 결선 (기존 유지) ──
@router.post("/{payment_id}/credit")
def grant_credit(payment_id: str, body: CreditGrantBody, current_user: dict = Depends(get_current_user)):
    from services.credit_svc import CreditError, grant, grant_from_diagnosis
    try:
        if body.diagnosis_purchase_id:
            credit_id = grant_from_diagnosis(body.diagnosis_purchase_id, created_by=current_user["id"])
        else:
            if not body.amount or body.amount <= 0:
                raise HTTPException(status_code=400, detail="수동 지급은 amount가 필요합니다.")
            pay = get_supabase().table("payments").select("company_id").eq("id", payment_id).limit(1).execute()
            if not pay.data:
                raise HTTPException(status_code=404, detail="결제 건을 찾을 수 없습니다.")
            credit_id = grant(company_id=pay.data[0]["company_id"], amount=body.amount, source="MANUAL",
                              source_ref=payment_id, expires_at=None, created_by=current_user["id"], memo=body.memo)
        return {"status": "success", "data": {"credit_id": credit_id}}
    except CreditError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ── 증빙 발행 결선 (role 001, 중앙 guard) ──
@router.post("/{payment_id}/invoice/tax")
def issue_tax(payment_id: str, body: TaxInvoiceBody, current_user: dict = Depends(_require_admin)):
    """세금계산서 관리자 직접발행 — 중앙 guard/저장금액/명시 supply_date 동일 적용."""
    from services.invoice_svc import InvoiceError, issue_tax_invoice
    try:
        invoicee = {"corpNum": body.corpNum, "corpName": body.corpName, "ceoName": body.ceoName,
                    "email": body.email, "addr": body.addr, "bizType": body.bizType, "bizClass": body.bizClass}
        res = issue_tax_invoice(payment_id, invoicee, body.supply_date, created_by=current_user["id"])
        return {"status": "success", "data": res}
    except InvoiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/{payment_id}/invoice/cash")
def issue_cash(payment_id: str, body: CashReceiptBody, current_user: dict = Depends(_require_admin)):
    """현금영수증 관리자 직접발행 — 중앙 guard/저장금액 동일 적용."""
    from services.invoice_svc import InvoiceError, issue_cash_receipt
    try:
        res = issue_cash_receipt(payment_id, trade_usage=body.trade_usage,
                                 identity_num=body.identity_num, created_by=current_user["id"])
        return {"status": "success", "data": res}
    except InvoiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ── 세금계산서 발행요청 processor (role 001) ──
@router.post("/tax-invoice-requests/{request_id}/process")
def process_request(request_id: str, body: ProcessBody, current_user: dict = Depends(_require_admin)):
    """승인된 발행요청 → 실발행 processor. INVOICE_LIVE OFF 면 423(mutation 0)."""
    from services.tax_invoice_processor_svc import ProcessorError, process_tax_invoice_request
    sb = get_supabase()
    try:
        row, outcome = process_tax_invoice_request(sb, request_id, body.supply_date, current_user["id"])
    except ProcessorError as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "detail": e.detail})
    return {"status": "success", "data": {"outcome": outcome, "request": row}}


# ── 결제 원장 통합 조회 ──
@router.get("/{payment_id}/ledger")
def get_payment_ledger(payment_id: str, current_user: dict = Depends(get_current_user)):
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
        supabase.table("refunds").select("id, refund_type, amount, status, reason_text, created_at")
        .eq("payment_id", payment_id).order("created_at", desc=True).execute()
    ).data or []
    invoices = (
        supabase.table("tax_invoices").select("id, doc_type, status, nts_confirm_num, total_amount, issued_at")
        .eq("payment_id", payment_id).order("created_at", desc=True).execute()
    ).data or []
    credits = (
        supabase.table("credits").select("id, source, amount, balance, status, expires_at, created_at")
        .eq("source_ref", payment_id).order("created_at", desc=True).execute()
    ).data or []
    return {
        "status": "success",
        "data": {"payment": payment, "refunds": refunds, "invoices": invoices, "credits": credits,
                 "refund_total": sum(int(r["amount"] or 0) for r in refunds if r.get("status") == "DONE")},
    }
