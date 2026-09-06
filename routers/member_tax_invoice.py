"""고객 세금계산서 eligibility + 발행요청 API (BACKEND-2).

- GET  /payments/{payment_id}/tax-invoice/eligibility
- POST /payments/{payment_id}/tax-invoice/request
- ownership = current_user.company_id == payment.company_id (토큰만). 타사/미존재 404.
- client company_id/user_id/requested_by 미수립. requested_by = public.users.id(서버).
- 실발행(Popbill)·invoice_svc·수정계산서 미포함. INVOICE_LIVE 미참조.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

try:
    from typing import Literal
except ImportError:  # pragma: no cover
    Literal = None  # type: ignore

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services import tax_invoice_request_svc as svc

router = APIRouter(prefix="/payments", tags=["세금계산서 요청"])


class TaxInvoiceRequestBody(BaseModel):
    source: str = "MYPAGE"  # MYPAGE | SAAS (AUTO_SAAS 금지)

    class Config:
        extra = "forbid"  # company_id/user_id/requested_by 등 주입 거부


@router.get("/{payment_id}/tax-invoice/eligibility")
def get_tax_invoice_eligibility(payment_id: str, current_user: dict = Depends(get_current_user)):
    """세금계산서 발행가능 여부(eligibility) 조회. 항상 200(decision 포함)."""
    sb = get_supabase()
    try:
        payment = svc.load_and_authorize(sb, current_user, payment_id)
        elig = svc.evaluate_eligibility(sb, payment)
    except svc.MemberTaxError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
    # existing_request row 는 응답에서 요약만 노출(전체 row 대신 id/status)
    er = elig.get("existing_request")
    elig["existing_request"] = ({"id": er.get("id"), "status": er.get("status")} if er else None)
    return {"status": "success", "data": elig}


@router.post("/{payment_id}/tax-invoice/request")
def create_tax_invoice_request(payment_id: str, body: TaxInvoiceRequestBody,
                               current_user: dict = Depends(get_current_user)):
    """세금계산서 발행요청. 신규 201 / idempotent 기존 200 / DENY·REVIEW 409.

    [WO-TAX-INVOICE-AUTO-01 STEP 2-B] eligibility ALLOW 후 자동으로 processor 까지 진행.
    orchestrator 는 fail-soft — 발행 실패/게이트(423)가 request 생성 자체를 실패시키지 않음.
    orchestrator 는 자체 멱등(ISSUED/PROCESSING 이면 재발행 스킵). ORIGINAL 최대 1.
    """
    source = (body.source or "").strip().upper()
    if source not in ("MYPAGE", "SAAS"):
        raise HTTPException(status_code=422, detail="source 는 MYPAGE 또는 SAAS 여야 합니다.")
    sb = get_supabase()
    try:
        payment = svc.load_and_authorize(sb, current_user, payment_id)
        row, created = svc.create_request(sb, current_user, payment, source)
    except svc.MemberTaxError as e:
        detail = e.payload if e.payload is not None else e.detail
        raise HTTPException(status_code=e.status_code, detail=detail) from e

    # STEP 2-B: 요청 접수 후 자동 processor 위임 (fail-soft — 응답 상태에 영향 없음).
    # orchestrator 가 eligibility/create_request 를 다시 호출하지만 모두 멱등 → ORIGINAL 1 보장.
    try:
        from services.tax_auto_svc import maybe_auto_issue_tax_invoice
        maybe_auto_issue_tax_invoice(sb, payment_id, "CUSTOMER_REQUEST",
                                     actor_id=current_user.get("id"))
        fresh = svc._select_request(sb, row["id"])
        if fresh:
            row = fresh
    except Exception:  # noqa: BLE001 — 응답에 영향 금지
        pass

    return JSONResponse(status_code=(201 if created else 200),
                        content={"status": "success", "data": row})
