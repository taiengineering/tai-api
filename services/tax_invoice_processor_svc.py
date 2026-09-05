"""세금계산서 발행 processor (BACKEND-3, SIMPLE FLOW).

얼은 위임자: request 상태확인 → supply_date 검증 → gate → snapshot invoicee → PROCESSING
→ invoice_svc.issue_tax_invoice → ISSUED/FAILED.
결제수단·상호배타·금액 판단은 invoice_svc 중앙 guard가 전담. 여기서는 recovery/drift/reconciliation
상태머신을 두지 않는다(BACKEND-4 수정세금계산서에서 버개 처리).

sb 는 호출측 주입(테스트 격리). 실발행·popbill 은 invoice_svc 위임.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from services.time import now_kst, serialize_external_utc

_REQUEST_COLS = (
    "id, payment_id, company_id, status, doc_type, "
    "invoicee_business_number, invoicee_company_name, invoicee_representative_name, "
    "invoicee_email, invoicee_address, invoicee_business_type, invoicee_business_category, "
    "supply_date, tax_invoice_id, failure_code, failure_reason, processed_at, updated_at"
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


def _mark(sb, request_id: str, patch: Dict[str, Any]) -> None:
    patch = dict(patch)
    patch["updated_at"] = _now_iso()
    sb.table("tax_invoice_requests").update(patch).eq("id", request_id).execute()


def process_tax_invoice_request(sb, request_id: str, supply_date: Optional[str],
                                actor_id: Optional[str]) -> Tuple[Dict[str, Any], str]:
    """(row, outcome) 반환. outcome: ISSUED. 상태충돌/게이트/검증은 ProcessorError."""
    from services.invoice_svc import InvoiceError, invoice_live, issue_tax_invoice

    # 1) gate 최선행 — OFF 면 request mutation 0
    if not invoice_live():
        raise ProcessorError(423, "INVOICE_GATED", "실발행 게이트 잠금(INVOICE_LIVE off).")

    # 2) supply_date 검증(mutation 전)
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

    # 4) 사업자 snapshot 필수 3개 확인(fail-fast, mutation 0)
    if not (req.get("invoicee_business_number") and req.get("invoicee_company_name")
            and req.get("invoicee_representative_name")):
        raise ProcessorError(422, "INVOICEE_INCOMPLETE", "요청 사업자정보(사업자번호/상호/대표자)가 부족합니다.")

    # 5) PROCESSING
    _mark(sb, request_id, {"status": "PROCESSING", "supply_date": supply_date})

    invoicee = {
        "corpNum": req.get("invoicee_business_number"),
        "corpName": req.get("invoicee_company_name"),
        "ceoName": req.get("invoicee_representative_name"),
        "email": req.get("invoicee_email"),
        "addr": req.get("invoicee_address"),
        "bizType": req.get("invoicee_business_type"),
        "bizClass": req.get("invoicee_business_category"),
    }

    # 6) 실발행 위임 (금액/guard/원장은 invoice_svc)
    try:
        res = issue_tax_invoice(req["payment_id"], invoicee, supply_date, created_by=actor_id)
    except InvoiceError as e:
        _mark(sb, request_id, {"status": "FAILED", "failure_code": getattr(e, "code", None) or "ISSUE_FAILED",
                               "failure_reason": (e.detail or "")[:500], "processed_at": _now_iso()})
        raise ProcessorError(e.status_code, getattr(e, "code", None) or "ISSUE_FAILED", e.detail) from e

    _mark(sb, request_id, {"status": "ISSUED", "tax_invoice_id": res.get("invoice_id"),
                           "failure_code": None, "failure_reason": None, "processed_at": _now_iso()})
    return _load_request(sb, request_id) or req, "ISSUED"
