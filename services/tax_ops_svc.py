"""세무(세금계산서) 발행 현황 서비스 (WO-15 TaxInvoiceOps).

Goal: G-ms4je4z3-33eada
- 고객(회사) 세금계산서(tax_invoices) 발행 현황. WO-4 InvoiceService(발행 액션)와 상보.
- settlements(전문가/매칭 정산)는 서비스 범위 밖 → 미사용.
- 결제 상태(payment_status): SUCCESS=결제완료. 미발행 = SUCCESS 결제 − 발행된 payment_id.
- 원천 읽기만. 오류 격리.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

_PAGE = 1000


def _fetch_all(table: str, select: str, build=None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    offset = 0
    try:
        while True:
            q = get_supabase().table(table).select(select)
            if build:
                q = build(q)
            res = q.range(offset, offset + _PAGE - 1).execute()
            rows = res.data or []
            out.extend(rows)
            if len(rows) < _PAGE:
                break
            offset += _PAGE
    except Exception as e:  # noqa: BLE001
        log.warning("[TAX-OPS] fetch 실패 %s: %s", table, e)
    return out


def invoice_status_summary() -> Dict[str, Any]:
    """세금계산서 상태별 집계 + 공급가·세액 합."""
    invs = _fetch_all("tax_invoices", "status, supply_cost, tax, total_amount")
    by_status: Dict[str, int] = {}
    supply_sum = tax_sum = total_sum = 0
    for i in invs:
        key = i.get("status") or "UNKNOWN"
        by_status[key] = by_status.get(key, 0) + 1
        supply_sum += int(i.get("supply_cost") or 0)
        tax_sum += int(i.get("tax") or 0)
        total_sum += int(i.get("total_amount") or 0)
    return {
        "total_invoices": len(invs),
        "by_status": by_status,
        "supply_cost_sum": supply_sum,
        "tax_sum": tax_sum,
        "total_amount_sum": total_sum,
    }


def _issued_payment_ids() -> set:
    return {
        i.get("payment_id") for i in
        _fetch_all("tax_invoices", "payment_id")
        if i.get("payment_id")
    }


def unissued_payments(limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    """SUCCESS 결제 중 세금계산서 미발행 건(발행 대상)."""
    issued = _issued_payment_ids()
    pays = _fetch_all(
        "payments",
        "id, company_id, total_amount, product_type, paid_at, created_at",
        lambda q: q.eq("status_code", "SUCCESS"),
    )
    unissued = [p for p in pays if p.get("id") not in issued]
    total = len(unissued)
    page = unissued[offset: offset + limit]
    return {"total": total, "items": page, "limit": limit, "offset": offset}


def issued_list(limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    """발행 완료 세금계산서 목록."""
    invs = _fetch_all(
        "tax_invoices",
        "id, payment_id, company_id, doc_type, supply_cost, tax, total_amount, "
        "nts_confirm_num, status, issued_at, created_at",
    )
    invs.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    total = len(invs)
    page = invs[offset: offset + limit]
    return {"total": total, "items": page, "limit": limit, "offset": offset}


def get_tax_ops() -> Dict[str, Any]:
    """세무 발행 현황 종합."""
    out: Dict[str, Any] = {}
    try:
        out["summary"] = invoice_status_summary()
    except Exception as e:  # noqa: BLE001
        out["summary"] = {"error": str(e)}
    try:
        u = unissued_payments(limit=10)
        out["unissued_preview"] = {"total": u["total"], "items": u["items"]}
    except Exception as e:  # noqa: BLE001
        out["unissued_preview"] = {"error": str(e)}
    return out
