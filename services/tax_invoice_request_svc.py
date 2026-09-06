"""세금계산서 발행요청 + 중앙 eligibility (BACKEND-2).

- 고객용 REQUEST만 담당. 실발행(Popbill)·invoice_svc·수정세금계산서·refund hook 미포함.
- ownership = current_user.company_id == payment.company_id (payment.user_id 미사용).
- 증빙 상호배타: 한 payment 에 TAX_INVOICE ⊕ CASH_RECEIPT.
- snapshot 은 companies/payments SoT 에서 서버 생성(client 법적정보 body 금지). 금액 재계산 금지.
- INVOICE_LIVE 는 Popbill 실호출 gate 이므로 request queue 에서는 보지 않는다.

sb(supabase) 는 호출측 주입(단위테스트 격리).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from services.time import now_kst, serialize_external_utc

_ALLOWED_SOURCES = ("MYPAGE", "SAAS", "AUTO_PAYMENT", "AUTO_SAAS", "ADMIN_MANUAL")
# MYPAGE/SAAS = 고객 UI/SaaS 셀프서비스 (라우터에서 이 두 값만 허용).
# AUTO_PAYMENT = 결제성공 자동 오케스트레이터(tax_auto_svc). AUTO_SAAS = 예비.
# ADMIN_MANUAL = 관리자 수동발행 (payment-less 허용, 별도 라우터/서비스).
# AUTO_* / ADMIN_MANUAL 는 서버 내부 전용 — 고객 API (POST /payments/{id}/tax-invoice/request)
# 노출 금지 (라우터에서 여전히 MYPAGE|SAAS 만 허용).

REASON = {
    "ELIGIBLE": None,
    "ALREADY_REQUESTED": "이미 세금계산서 발행 요청이 접수되어 있습니다.",
    "REQUEST_CANCELLED": "환불로 취소된 요청입니다.",
    "PAYMENT_NOT_SUCCESS": "결제완료(SUCCESS) 건만 세금계산서를 요청할 수 있습니다.",
    "TAX_INVOICE_ALREADY_EXISTS": "이미 세금계산서가 발행되었습니다.",
    "TAX_INVOICE_HISTORY_REVIEW": "과거 세금계산서 이력이 있어 확인이 필요합니다.",
    "CASH_RECEIPT_EXISTS": "현금영수증이 발행되어 세금계산서를 중복 발행할 수 없습니다.",
    "CASH_RECEIPT_HISTORY_REVIEW": "과거 현금영수증 이력이 있어 확인이 필요합니다.",
    "CARD_RECEIPT_IS_EVIDENCE": "카드 결제는 카드매출전표가 증빙이므로 세금계산서를 발행하지 않습니다.",
    "UNKNOWN_PAYMENT_METHOD": "결제수단을 확인할 수 없어 검토가 필요합니다.",
    "CASH_RECEIPT_SELECTED": "현금영수증을 선택한 결제입니다.",
    "LEGACY_PROOF_UNKNOWN": "증빙 선택 정보가 없어 확인이 필요합니다.",
    "PROOF_NOT_SELECTED": "증빙이 선택되지 않았습니다.",
    "PROOF_CONFLICT": "증빙 선택 정보가 결제수단과 맞지 않아 확인이 필요합니다.",
    "COMPANY_PROFILE_INCOMPLETE": "세금계산서 발행에 필요한 회사정보가 부족합니다.",
}

_PAYMENT_COLS = (
    "id, status_code, company_id, pg_method, proof_type, "
    "supply_amount, vat_amount, total_amount, paid_at, product_type"
)
_COMPANY_COLS = (
    "id, name, business_number, representative_name, contact_email, "
    "address, address_road, address_detail, business_type, business_category"
)
_REQUEST_COLS = (
    "id, payment_id, company_id, requested_by, source, doc_type, status, proof_type, "
    "invoicee_business_number, invoicee_company_name, invoicee_representative_name, "
    "invoicee_email, invoicee_address, invoicee_business_type, invoicee_business_category, "
    "supply_amount, vat_amount, total_amount, pg_method, paid_at, supply_date, product_type, "
    "tax_invoice_id, failure_code, failure_reason, requested_at, processed_at, created_at, updated_at"
)


class MemberTaxError(Exception):
    """고객 세금계산서 API 오류(라우터에서 HTTPException 변환). payload 는 409 상세."""
    def __init__(self, status_code: int, code: str, detail: Optional[str] = None,
                 payload: Optional[Dict[str, Any]] = None):
        self.status_code = status_code
        self.code = code
        self.detail = detail if detail is not None else code
        self.payload = payload
        super().__init__(self.detail)


def _now_iso() -> str:
    return serialize_external_utc(now_kst())


def canonical_payment_instrument(pg_method: Optional[str]) -> str:
    """pg_method(SoT) → canonical 결제수단. 중앙 helper(다른 곳 매핑 금지).

    Frozen: Card/CardBilling→CARD, DirectBank→ACCOUNT_TRANSFER, VBank/VBANK/Vbank→VBANK, else UNKNOWN.
    임의 alias 확장 금지.
    """
    low = (pg_method or "").strip().lower()
    if low in ("card", "cardbilling"):
        return "CARD"
    if low == "directbank":
        return "ACCOUNT_TRANSFER"
    if low == "vbank":
        return "VBANK"
    return "UNKNOWN"


def _norm_bn10(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    d = re.sub(r"\D", "", str(raw))
    return d if len(d) == 10 else None


def _company_missing(company: Dict[str, Any]) -> List[str]:
    """invoice_svc 필수(business_number·name·representative_name) 기준 부족 필드."""
    missing: List[str] = []
    if _norm_bn10(company.get("business_number")) is None:
        missing.append("business_number")
    if not (company.get("representative_name") or "").strip():
        missing.append("representative_name")
    if not (company.get("name") or "").strip():
        missing.append("name")
    return missing


def _load_payment(sb, payment_id: str) -> Optional[Dict[str, Any]]:
    res = sb.table("payments").select(_PAYMENT_COLS).eq("id", payment_id).limit(1).execute()
    data = res.data or []
    return data[0] if data else None


def _load_company(sb, company_id: Optional[str]) -> Dict[str, Any]:
    if not company_id:
        return {}
    res = sb.table("companies").select(_COMPANY_COLS).eq("id", company_id).limit(1).execute()
    data = res.data or []
    return data[0] if data else {}


def _load_existing_request(sb, payment_id: str) -> Optional[Dict[str, Any]]:
    res = (
        sb.table("tax_invoice_requests").select(_REQUEST_COLS)
        .eq("payment_id", payment_id).eq("doc_type", "TAX_INVOICE").limit(1).execute()
    )
    data = res.data or []
    return data[0] if data else None


def _select_request(sb, request_id: str) -> Optional[Dict[str, Any]]:
    res = sb.table("tax_invoice_requests").select(_REQUEST_COLS).eq("id", request_id).limit(1).execute()
    data = res.data or []
    return data[0] if data else None


def _ledger_flags(sb, payment_id: str) -> Dict[str, bool]:
    res = sb.table("tax_invoices").select("doc_type, status, invoice_kind").eq("payment_id", payment_id).execute()
    ti = [r.get("status") for r in (res.data or [])
          if r.get("doc_type") == "TAX_INVOICE" and (r.get("invoice_kind") in (None, "ORIGINAL"))]
    cr = [r.get("status") for r in (res.data or []) if r.get("doc_type") == "CASH_RECEIPT"]
    ti_active = any(s in ("PENDING", "ISSUED") for s in ti)
    cr_active = any(s in ("PENDING", "ISSUED", "FAILED") for s in cr)
    return {
        "has_ti": bool(ti), "ti_active": ti_active,
        "ti_hist_only": (not ti_active) and any(s in ("FAILED", "CANCELLED") for s in ti),
        "has_cr": bool(cr), "cr_active": cr_active,
        "cr_hist_only": (not cr_active) and any(s == "CANCELLED" for s in cr),
    }


def load_and_authorize(sb, current_user: Dict[str, Any], payment_id: str) -> Dict[str, Any]:
    """ownership: current_user.company_id == payment.company_id. 타사/미존재는 404(비노출)."""
    if not current_user.get("id"):
        raise MemberTaxError(401, "UNAUTHENTICATED", "사용자 식별에 실패했습니다.")
    company_id = current_user.get("company_id")
    if not company_id:
        raise MemberTaxError(403, "COMPANY_REQUIRED", "소속 회사가 없어 요청할 수 없습니다.")
    payment = _load_payment(sb, payment_id)
    if not payment:
        raise MemberTaxError(404, "PAYMENT_NOT_FOUND", "결제 건을 찾을 수 없습니다.")
    if str(payment.get("company_id")) != str(company_id):
        # 타사 payment 존재 비노출 → 404
        raise MemberTaxError(404, "PAYMENT_NOT_FOUND", "결제 건을 찾을 수 없습니다.")
    return payment


def evaluate_eligibility(sb, payment: Dict[str, Any]) -> Dict[str, Any]:
    """E2~E7 고정 순서 평가(E1 ownership 은 load_and_authorize 에서 선행)."""
    method = canonical_payment_instrument(payment.get("pg_method"))
    proof = payment.get("proof_type")
    company = _load_company(sb, payment.get("company_id"))
    missing = _company_missing(company or {})
    existing_req = _load_existing_request(sb, payment["id"])
    flags = _ledger_flags(sb, payment["id"])

    base = {
        "payment_method": method,
        "proof_type": proof,
        "company_complete": (len(missing) == 0),
        "missing_fields": missing,
        "existing_request": existing_req,
        "existing_tax_invoice": flags["has_ti"],
        "existing_cash_receipt": flags["has_cr"],
    }

    def result(decision: str, code: str) -> Dict[str, Any]:
        out = dict(base)
        out.update({"eligible": decision == "ALLOW", "decision": decision,
                    "reason_code": code, "reason": REASON.get(code)})
        return out

    # E2 payment SUCCESS
    if payment.get("status_code") != "SUCCESS":
        return result("DENY", "PAYMENT_NOT_SUCCESS")

    # E3 existing request lifecycle
    if existing_req:
        st = existing_req.get("status")
        if st in ("REQUESTED", "PROCESSING", "ISSUED"):
            return result("ALLOW", "ALREADY_REQUESTED")
        if st == "CANCELLED":
            return result("DENY", "REQUEST_CANCELLED")
        # FAILED / REVIEW_REQUIRED → 아래에서 재평가

    # E4 existing TAX_INVOICE ledger (ORIGINAL)
    if flags["ti_active"]:
        return result("DENY", "TAX_INVOICE_ALREADY_EXISTS")
    if flags["ti_hist_only"]:
        return result("REVIEW_REQUIRED", "TAX_INVOICE_HISTORY_REVIEW")

    # E4b existing CASH_RECEIPT ledger (상호배타)
    if flags["cr_active"]:
        return result("DENY", "CASH_RECEIPT_EXISTS")
    if flags["cr_hist_only"]:
        return result("REVIEW_REQUIRED", "CASH_RECEIPT_HISTORY_REVIEW")

    # E5 payment-method / proof policy
    if method == "CARD":
        return result("DENY", "CARD_RECEIPT_IS_EVIDENCE")
    if method == "UNKNOWN":
        return result("REVIEW_REQUIRED", "UNKNOWN_PAYMENT_METHOD")
    if proof == "CASH_RECEIPT":
        return result("DENY", "CASH_RECEIPT_SELECTED")
    if method == "ACCOUNT_TRANSFER":
        if proof == "TAX_INVOICE":
            pass
        elif proof is None:
            return result("REVIEW_REQUIRED", "LEGACY_PROOF_UNKNOWN")
        elif proof == "NONE":
            return result("REVIEW_REQUIRED", "PROOF_NOT_SELECTED")
        elif proof == "CARD_RECEIPT":
            return result("REVIEW_REQUIRED", "PROOF_CONFLICT")
    elif method == "VBANK":
        if proof == "CARD_RECEIPT":
            return result("REVIEW_REQUIRED", "PROOF_CONFLICT")
        # TAX_INVOICE / None / NONE → 허용(CASH_RECEIPT 는 위에서 DENY)

    # E6 company completeness
    if missing:
        return result("DENY", "COMPANY_PROFILE_INCOMPLETE")

    # E7
    return result("ALLOW", "ELIGIBLE")


def _deny_payload(elig: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "decision": elig["decision"],
        "reason_code": elig["reason_code"],
        "reason": elig.get("reason"),
        "missing_fields": elig.get("missing_fields", []),
    }


def _is_payment_doc_unique(e: Exception) -> bool:
    parts = [str(getattr(e, a, "") or "") for a in ("code", "message", "details", "hint")] + [str(e)]
    text = " ".join(parts)
    if "tax_invoice_requests_payment_doc_unique" in text:
        return True
    if str(getattr(e, "code", "") or "") == "23505" and "payment_id" in text:
        return True
    return False


def _snapshot(current_user: Dict[str, Any], payment: Dict[str, Any],
              company: Dict[str, Any], source: str) -> Dict[str, Any]:
    bn = _norm_bn10(company.get("business_number"))
    addr = ("{} {}".format(company.get("address_road") or "", company.get("address_detail") or "")).strip()
    addr = addr or (company.get("address") or None)
    return {
        "payment_id": payment["id"],
        "company_id": payment["company_id"],
        "requested_by": current_user.get("id"),
        "source": source,
        "doc_type": "TAX_INVOICE",
        "proof_type": "TAX_INVOICE",
        "invoicee_business_number": bn,
        "invoicee_company_name": company.get("name"),
        "invoicee_representative_name": company.get("representative_name"),
        "invoicee_email": company.get("contact_email"),
        "invoicee_address": addr,
        "invoicee_business_type": company.get("business_type"),
        "invoicee_business_category": company.get("business_category"),
        # 금액 재계산 금지 — payments 저장값 그대로
        "supply_amount": payment.get("supply_amount"),
        "vat_amount": payment.get("vat_amount"),
        "total_amount": payment.get("total_amount"),
        "pg_method": payment.get("pg_method"),
        "paid_at": payment.get("paid_at"),
        "supply_date": None,  # BACKEND-2 에서는 공급일자 미확정
        "product_type": payment.get("product_type"),
    }


def _audit(payment_id: str, request_id: str, source: str, status: str, method: str,
           actor_id: Optional[str]) -> None:
    try:
        from services import audit_svc
        audit_svc.record(
            "TAX_INVOICE_REQUEST", "payment", entity_id=payment_id, actor_id=actor_id,
            after={"request_id": request_id, "source": source, "status": status, "payment_method": method},
        )
    except Exception:  # noqa: BLE001  best-effort (audit 실패가 request 를 실패시키지 않음)
        pass


def create_request(sb, current_user: Dict[str, Any], payment: Dict[str, Any],
                   source: str) -> Tuple[Dict[str, Any], bool]:
    """세금계산서 발행요청. (row, created) 반환. created=True → 201, False → 200. DENY/REVIEW → 409."""
    if source not in _ALLOWED_SOURCES:
        raise MemberTaxError(422, "INVALID_SOURCE", "source 는 MYPAGE 또는 SAAS 여야 합니다.")

    elig = evaluate_eligibility(sb, payment)
    existing = elig["existing_request"]

    # 활성 기존 요청 → idempotent 반환(policy 재계산보다 우선)
    if existing and existing.get("status") in ("REQUESTED", "PROCESSING", "ISSUED"):
        return existing, False

    if elig["decision"] != "ALLOW":
        raise MemberTaxError(409, elig["reason_code"], elig.get("reason"), payload=_deny_payload(elig))

    company = _load_company(sb, payment.get("company_id"))
    snap = _snapshot(current_user, payment, company, source)

    # ALLOW + 기존 FAILED/REVIEW_REQUIRED → 같은 row 재사용(UPDATE), 신규 INSERT 금지
    if existing and existing.get("status") in ("FAILED", "REVIEW_REQUIRED"):
        patch = dict(snap)
        patch.update({
            "status": "REQUESTED", "failure_code": None, "failure_reason": None,
            "processed_at": None, "requested_at": _now_iso(), "updated_at": _now_iso(),
        })
        sb.table("tax_invoice_requests").update(patch).eq("id", existing["id"]).execute()
        row = _select_request(sb, existing["id"]) or existing
        _audit(payment["id"], existing["id"], source, "REQUESTED", elig["payment_method"], current_user.get("id"))
        return row, False

    # 신규 INSERT
    insert_row = dict(snap)
    insert_row.update({"status": "REQUESTED", "requested_at": _now_iso(),
                       "created_at": _now_iso(), "updated_at": _now_iso()})
    try:
        ins = sb.table("tax_invoice_requests").insert(insert_row).execute()
    except Exception as e:
        # concurrent flat UNIQUE(payment_id, doc_type) → 기존 row 반환(idempotent)
        if _is_payment_doc_unique(e):
            ex = _load_existing_request(sb, payment["id"])
            if ex:
                return ex, False
        raise MemberTaxError(500, "REQUEST_CREATE_FAILED", "세금계산서 요청 생성에 실패했습니다.") from e
    if not ins.data:
        raise MemberTaxError(500, "REQUEST_CREATE_FAILED", "세금계산서 요청 생성에 실패했습니다.")
    new_id = ins.data[0]["id"]
    row = _select_request(sb, new_id) or ins.data[0]
    _audit(payment["id"], new_id, source, "REQUESTED", elig["payment_method"], current_user.get("id"))
    return row, True


# ═════════════════════════════════════════════════════════════════════
# [WO-TAX-INVOICE-AUTO-01 PATCH-1 A-P1] AUTO 예외큐 helper.
# 자동 orchestrator 전용 — 고객 라우터/create_request/evaluate_eligibility 계약은 불변.
# 목적: eligibility REVIEW_REQUIRED 또는 자동 복구 가능 DENY (COMPANY_PROFILE_INCOMPLETE) 시,
#       tax_invoice_requests 에 REVIEW_REQUIRED row 를 남겨 Admin 예외콘솔에서 노출.
# ═════════════════════════════════════════════════════════════════════
def ensure_auto_exception_request(sb, payment: Dict[str, Any], source: str,
                                  reason_code: str, reason: Optional[str] = None,
                                  missing_fields: Optional[List[str]] = None
                                  ) -> Tuple[Dict[str, Any], bool]:
    """AUTO 경로 예외큐 기록 (신규 table 금지 — 기존 tax_invoice_requests 재사용).

    Args:
        sb: supabase client
        payment: authoritative payment row (payments SoT)
        source: AUTO_PAYMENT 등 (라우터에서 오는 MYPAGE/SAAS 아님)
        reason_code: eligibility.reason_code 또는 helper 내부 코드
                     (예: COMPANY_PROFILE_INCOMPLETE, LEGACY_PROOF_UNKNOWN,
                          SUPPLY_DATE_UNRESOLVED, ...)
        reason: 사람 읽기 텍스트 (없으면 REASON dict 에서 조회)
        missing_fields: COMPANY_PROFILE_INCOMPLETE 시 상세 (audit only)

    Returns:
        (row, created)  created=True → INSERT, False → UPDATE(기존 예외 갱신) 또는 활성 request 존재로 no-op

    계약:
      - status = REVIEW_REQUIRED, source = AUTO_PAYMENT (or 입력값), doc_type = TAX_INVOICE
      - failure_code = reason_code, failure_reason = reason
      - 기존 활성 request (REQUESTED / PROCESSING / ISSUED) 는 절대 덮어쓰지 않음
        → 정상 발행 상태를 예외로 승격 금지. 이 경우 (existing, False) 반환.
      - 기존 FAILED / REVIEW_REQUIRED / CANCELLED row 는 REVIEW_REQUIRED 로 갱신 (멱등)
      - 신규 INSERT 는 _snapshot 재사용 (금액 = payments SoT 그대로, 재계산 0)
    """
    if source not in _ALLOWED_SOURCES:
        raise MemberTaxError(422, "INVALID_SOURCE", "source 는 허용 목록에 없습니다.")

    reason_text = reason if reason is not None else REASON.get(reason_code)

    existing = _load_existing_request(sb, payment["id"])
    if existing:
        st = str(existing.get("status") or "").upper()
        # 활성 request 는 절대 예외로 승격 금지 (정상 발행 흐름 우선)
        if st in ("REQUESTED", "PROCESSING", "ISSUED"):
            return existing, False
        # 기존 예외/실패 row 를 REVIEW_REQUIRED 로 갱신 (멱등)
        patch = {
            "status": "REVIEW_REQUIRED",
            "source": source,
            "failure_code": reason_code,
            "failure_reason": (reason_text or "")[:500] if reason_text else None,
            "processed_at": None,
            "updated_at": _now_iso(),
        }
        sb.table("tax_invoice_requests").update(patch).eq("id", existing["id"]).execute()
        row = _select_request(sb, existing["id"]) or existing
        _audit(payment["id"], existing["id"], source, "REVIEW_REQUIRED",
               canonical_payment_instrument(payment.get("pg_method")),
               None)  # AUTO 경로 → actor_id None
        return row, False

    # 신규 INSERT (예외 request)
    company = _load_company(sb, payment.get("company_id"))
    # AUTO 는 system user (id=None). snapshot 은 _snapshot 재사용 — 금액 재계산 0.
    system_user = {"id": None, "company_id": payment.get("company_id")}
    snap = _snapshot(system_user, payment, company, source)
    insert_row = dict(snap)
    insert_row.update({
        "status": "REVIEW_REQUIRED",
        "failure_code": reason_code,
        "failure_reason": (reason_text or "")[:500] if reason_text else None,
        "requested_at": _now_iso(),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    })
    try:
        ins = sb.table("tax_invoice_requests").insert(insert_row).execute()
    except Exception as e:  # noqa: BLE001 — 동시성/UNIQUE 재조회
        if _is_payment_doc_unique(e):
            ex = _load_existing_request(sb, payment["id"])
            if ex:
                # 위 branch 로 재분기 — 활성이면 그대로, 아니면 REVIEW 갱신
                return ensure_auto_exception_request(sb, payment, source, reason_code,
                                                     reason=reason, missing_fields=missing_fields)
        raise MemberTaxError(500, "AUTO_EXCEPTION_CREATE_FAILED",
                             "자동 예외큐 생성에 실패했습니다.") from e
    if not ins.data:
        raise MemberTaxError(500, "AUTO_EXCEPTION_CREATE_FAILED",
                             "자동 예외큐 생성에 실패했습니다.")
    new_id = ins.data[0]["id"]
    row = _select_request(sb, new_id) or ins.data[0]
    _audit(payment["id"], new_id, source, "REVIEW_REQUIRED",
           canonical_payment_instrument(payment.get("pg_method")), None)
    return row, True
