"""세무 발행 현황 라우터 (WO-15 TaxInvoiceOps).

Goal: G-ms4je4z3-33eada
- 세금계산서 발행 현황·미발행 결제·발행 목록. 얇은 위임.
"""
from fastapi import APIRouter, Query

from services.tax_ops_svc import get_tax_ops, issued_list, unissued_payments

router = APIRouter(prefix="/tax", tags=["세무"])


@router.get("/ops")
def tax_ops():
    """세무 발행 현황 종합."""
    return {"status": "success", "data": get_tax_ops()}


@router.get("/unissued")
def tax_unissued(limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    """세금계산서 미발행 결제 목록(발행 대상)."""
    return {"status": "success", "data": unissued_payments(limit=limit, offset=offset)}


@router.get("/issued")
def tax_issued(limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    """발행 완료 세금계산서 목록."""
    return {"status": "success", "data": issued_list(limit=limit, offset=offset)}
