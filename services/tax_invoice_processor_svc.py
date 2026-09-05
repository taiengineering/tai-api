"""세금계산서 발행 processor (BACKEND-3).

request(REQUESTED/FAILED) → 발행 직전 current-state 재검증 → 조건부 PROCESSING claim
→ invoice_svc.issue_tax_invoice → ISSUED/FAILED. 명시 supply_date 필수. INVOICE_LIVE gate 최선행.

sb 는 호출측 주입(테스트 격리). 실발행·popbill 은 invoice_svc 위임.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from services.time import now_kst, serialize_external_utc

_REQUEST_COLS = (
    "id, payment_id, company_id, requested_by, source, doc_type, status, proof_type, "
    "invoicee_business_number, invoicee_company_name, invoicee_representative_name, "
    "invoicee_email, invoicee_address, invoicee_business_type, invoicee_business_category, "
    "supply_amount, vat_amount, total_amount, pg_method, paid_at, supply_date, product_type, "
    "tax_invoice_id, failure_code, failure_reason, requested_at, processed_at, created_at, updated_at"
)


class ProcessorError(Exception):
    def __init__(self, status_code: int, code: str, detail: Optional[str] = None):
        self.status_code = status_code
        self.code = code
        self.detail = detail if detail is not None else code
        super().__init__(self.detail)


def _now_iso() -> str:
    return serialize_external_utc(now_kst())


def _validate_supply_date(supply_date: Optional[str]) -> None:
    if not supply_date:
        raise ProcessorError(400, "SUPPLY_DATE_REQUIRED", "공급일자(supply_date)가 필요합니다.")
    try:
        datetime.strptime(str(supply_date).strip(), "%Y-%m-%d")
    except Exception as e:  # noqa: BLE001
        raise ProcessorError(400, "INVALID_SUPPLY_DATE", "공급일자 형식(YYYY-MM-DD)이 올바르지 않습니다.") from e


def _load_request(sb, request_id: str) -> Optional[Dict[str, Any]]:
    res = sb.table("tax_invoice_requests").select(_REQUEST_COLS).eq("id", request_id).limit(1).execute()
    data = res.data or []
    return data[0] if data else None


def _load_payment(sb, payment_id: str) -> Optional[Dict[str, Any]]:
    res = (
        sb.table("payments")
        .select("id, status_code, company_id, pg_method, proof_type, supply_amount, vat_amount, total_amount, paid_at, product_type")
        .eq("id", payment_id).limit(1).execute()
    )
    data = res.data or []
    return data[0] if data else None


def _existing_issued_tax_invoice(sb, payment_id: str) -> Optional[Dict[str, Any]]:
    res = (
        sb.table("tax_invoices").select("id, doc_type, status, invoice_kind")
        .eq("payment_id", payment_id).execute()
    )
    for r in (res.data or []):
        if r.get("doc_type") == "TAX_INVOICE" and (r.get("invoice_kind") in (None, "ORIGINAL")) and r.get("status") == "ISSUED":
            return r
    return None


def _cash_statuses(sb, payment_id: str) -> list:
    res = sb.table("tax_invoices").select("doc_type, status").eq("payment_id", payment_id).execute()
    return [r.get("status") for r in (res.data or []) if r.get("doc_type") == "CASH_RECEIPT"]


def _int(v) -> int:
    try:
        return int(v or 0)
    except Exception:  # noqa: BLE001
        return 0


def _mark(sb, request_id: str, patch: Dict[str, Any]) -> None:
    patch = dict(patch)
    patch["updated_at"] = _now_iso()
    sb.table("tax_invoice_requests").update(patch).eq("id", request_id).execute()


def process_tax_invoice_request(sb, request_id: str, supply_date: Optional[str],
                                actor_id: Optional[str]) -> Tuple[Dict[str, Any], str]:
    """(row, outcome) 반환. outcome: ISSUED | RECONCILED. DENY/상태충돌은 ProcessorError."""
    from services.invoice_svc import InvoiceError, invoice_live, issue_tax_invoice

    # 1) gate 최선행 — OFF 면 request/ledger mutation 0
    if not invoice_live():
        raise ProcessorError(423, "INVOICE_GATED", "실발행 게이트 잠금(INVOICE_LIVE off).")

    # 2) supply_date 조기 검증(claim 전)
    _validate_supply_date(supply_date)

    # 3) request 상태머신
    req = _load_request(sb, request_id)
    if not req:
        raise ProcessorError(404, "REQUEST_NOT_FOUND", "발행요청을 찾을 수 없습니다.")
    st = req.get("status")
    if st == "ISSUED":
        return req, "ISSUED"  # idempotent
    if st == "PROCESSING":
        raise ProcessorError(409, "REQUEST_ALREADY_PROCESSING", "이미 처리 중입니다.")
    if st == "CANCELLED":
        raise ProcessorError(409, "REQUEST_CANCELLED", "취소된 요청입니다.")
    if st == "REVIEW_REQUIRED":
        raise ProcessorError(409, "REQUEST_REVIEW_REQUIRED", "검토가 필요한 요청입니다.")
    # st in (REQUESTED, FAILED)

    payment = _load_payment(sb, req["payment_id"])
    if not payment:
        raise ProcessorError(404, "PAYMENT_NOT_FOUND", "결제 건을 찾을 수 없습니다.")

    # 4) reconciliation: 이미 ORIGINAL TAX_INVOICE ISSUED → Popbill 재호출 없이 request 복구
    issued_inv = _existing_issued_tax_invoice(sb, req["payment_id"])
    if issued_inv:
        _mark(sb, request_id, {"status": "ISSUED", "tax_invoice_id": issued_inv["id"],
                               "failure_code": None, "failure_reason": None, "processed_at": _now_iso()})
        return _load_request(sb, request_id) or req, "RECONCILED"

    # 5) current-state 재검증 (snapshot drift / invoicee 결여 / 상대증빙 출현)
    if (str(payment.get("company_id")) != str(req.get("company_id"))
            or _int(payment.get("supply_amount")) != _int(req.get("supply_amount"))
            or _int(payment.get("vat_amount")) != _int(req.get("vat_amount"))
            or _int(payment.get("total_amount")) != _int(req.get("total_amount"))):
        _mark(sb, request_id, {"status": "REVIEW_REQUIRED", "failure_code": "PAYMENT_SNAPSHOT_DRIFT",
                               "failure_reason": "결제 금액/회사 스냅샷이 현재와 달라 확인 필요"})
        raise ProcessorError(409, "PAYMENT_SNAPSHOT_DRIFT", "결제 스냅샷이 현재와 달라 발행을 멈췥니다.")

    if not (req.get("invoicee_business_number") and req.get("invoicee_company_name") and req.get("invoicee_representative_name")):
        _mark(sb, request_id, {"status": "REVIEW_REQUIRED", "failure_code": "REQUEST_SNAPSHOT_INCOMPLETE",
                               "failure_reason": "요청 시점 법적정보 스냅샷이 불완전"})
        raise ProcessorError(409, "REQUEST_SNAPSHOT_INCOMPLETE", "요청 시점 법적정보가 부족합니다.")

    cr = _cash_statuses(sb, req["payment_id"])
    if any(s in ("PENDING", "ISSUED", "FAILED", "CANCELLED") for s in cr):
        _mark(sb, request_id, {"status": "REVIEW_REQUIRED", "failure_code": "CASH_RECEIPT_APPEARED",
                               "failure_reason": "동일 결제에 현금영수증이 발생해 확인 필요"})
        raise ProcessorError(409, "CASH_RECEIPT_APPEARED", "현금영수증이 발생해 세금계산서를 발행할 수 없습니다.")

    # 6) 조건부 PROCESSING claim (REQUESTED/FAILED 만)
    claim = (
        sb.table("tax_invoice_requests")
        .update({"status": "PROCESSING", "supply_date": supply_date, "updated_at": _now_iso()})
        .eq("id", request_id).in_("status", ["REQUESTED", "FAILED"]).execute()
    )
    if not claim.data:
        cur = _load_request(sb, request_id)
        if cur and cur.get("status") == "ISSUED":
            return cur, "ISSUED"
        raise ProcessorError(409, "REQUEST_ALREADY_PROCESSING", "동시 처리 충돌입니다.")

    # 7) invoice_svc 실발행 (snapshot invoicee 사용)
    invoicee = {
        "corpNum": req.get("invoicee_business_number"),
        "corpName": req.get("invoicee_company_name"),
        "ceoName": req.get("invoicee_representative_name"),
        "email": req.get("invoicee_email"),
        "addr": req.get("invoicee_address"),
        "bizType": req.get("invoicee_business_type"),
        "bizClass": req.get("invoicee_business_category"),
    }
    try:
        res = issue_tax_invoice(req["payment_id"], invoicee, supply_date, created_by=actor_id)
    except InvoiceError as e:
        _mark(sb, request_id, {"status": "FAILED", "failure_code": getattr(e, "code", None) or "ISSUE_FAILED",
                               "failure_reason": (e.detail or "")[:500], "processed_at": _now_iso()})
        raise ProcessorError(e.status_code, getattr(e, "code", None) or "ISSUE_FAILED", e.detail) from e

    _mark(sb, request_id, {"status": "ISSUED", "tax_invoice_id": res.get("invoice_id"),
                           "failure_code": None, "failure_reason": None, "processed_at": _now_iso()})
    return _load_request(sb, request_id) or req, "ISSUED"
