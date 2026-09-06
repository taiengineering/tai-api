"""관리자 수동 세금계산서 발행 (WO-TAX-INVOICE-MANUAL-01).

정본 = 관리자가 결제 없이 직접 세금계산서를 발행하는 예외 경로.
  - 기존 tax_invoice_requests / tax_invoices 재사용 (신규 테이블 금지).
  - source = 'ADMIN_MANUAL', payment_id NULL 허용 (DB 마이그레이션에서 nullable).
  - 회사 스냅샷: EXISTING (companies SoT 재조회) 또는 MANUAL (요청 body invoicee_* 그대로).
    · MANUAL 모드: companies 에 INSERT 금지 — snapshot 만.
  - 금액: server 가 total = supply + vat 를 재계산 (프론트 값 회계 판정 금지).
  - idempotency_key (uuid) → partial UNIQUE (DDL) 로 더블클릭/재시도 방어.
  - Popbill 실호출은 invoice_svc.issue_manual_tax_invoice 위임.

계약 불변:
  - 기존 issue_tax_invoice (payment 기반) 는 한 줄도 완화하지 않음. 신규 함수 별도 신설.
  - INVOICE_LIVE OFF → 423 → request.status=REQUESTED 유지 (FAILED 오염 금지).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from services.tax_invoice_request_svc import (
    MemberTaxError, _COMPANY_COLS, _REQUEST_COLS, _load_company,
    _load_existing_request, _now_iso, _norm_bn10, _select_request,
)


_MANUAL_REQUEST_COLS = _REQUEST_COLS + ", idempotency_key, item_name, issue_reason"


def _load_manual_request(sb, request_id: str) -> Optional[Dict[str, Any]]:
    res = (sb.table("tax_invoice_requests").select(_MANUAL_REQUEST_COLS)
           .eq("id", request_id).limit(1).execute())
    data = res.data or []
    return data[0] if data else None


def _load_manual_by_idempotency_key(sb, idem_key: str) -> Optional[Dict[str, Any]]:
    if not idem_key:
        return None
    res = (sb.table("tax_invoice_requests").select(_MANUAL_REQUEST_COLS)
           .eq("idempotency_key", idem_key).eq("source", "ADMIN_MANUAL").limit(1).execute())
    data = res.data or []
    return data[0] if data else None


def _validate_amounts(supply_amount: Any, vat_amount: Any) -> tuple[int, int, int]:
    """공급가액/부가세 non-negative int 검증 + 서버 total 계산.

    프론트가 준 total 은 신뢰하지 않음 (회계 판정 서버 SoT).
    """
    try:
        supply = int(supply_amount)
        vat = int(vat_amount)
    except (TypeError, ValueError) as e:
        raise MemberTaxError(400, "INVALID_AMOUNT",
                             "공급가액/부가세는 정수여야 합니다.") from e
    if supply < 0 or vat < 0:
        raise MemberTaxError(400, "INVALID_AMOUNT",
                             "공급가액/부가세는 0 이상이어야 합니다.")
    total = supply + vat
    return supply, vat, total


def _validate_supply_date(supply_date: Any) -> str:
    """YYYY-MM-DD 형식 검증. 자동 today 금지 (사용자 명시 입력만)."""
    if not supply_date:
        raise MemberTaxError(400, "SUPPLY_DATE_REQUIRED", "공급일자가 필요합니다.")
    s = str(supply_date).strip()
    from datetime import datetime
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except Exception as e:
        raise MemberTaxError(400, "INVALID_SUPPLY_DATE",
                             "공급일자 형식(YYYY-MM-DD)이 올바르지 않습니다.") from e
    return s


def _build_snapshot_existing(sb, company_id: str) -> Dict[str, Any]:
    """EXISTING 모드: companies SoT 재조회하여 snapshot 구성 (프론트 법적정보 불신뢰)."""
    if not company_id:
        raise MemberTaxError(400, "COMPANY_ID_REQUIRED",
                             "EXISTING 모드에서는 company_id 가 필요합니다.")
    company = _load_company(sb, company_id)
    if not company:
        raise MemberTaxError(404, "COMPANY_NOT_FOUND", "회사를 찾을 수 없습니다.")
    bn = _norm_bn10(company.get("business_number"))
    missing: List[str] = []
    if not bn:
        missing.append("business_number")
    if not (company.get("name") or "").strip():
        missing.append("name")
    if not (company.get("representative_name") or "").strip():
        missing.append("representative_name")
    if missing:
        raise MemberTaxError(400, "COMPANY_PROFILE_INCOMPLETE",
                             "회사정보가 부족합니다: {}".format(",".join(missing)))
    addr = ("{} {}".format(company.get("address_road") or "",
                           company.get("address_detail") or "")).strip()
    addr = addr or (company.get("address") or None)
    return {
        "company_id": company_id,
        "invoicee_business_number": bn,
        "invoicee_company_name": company.get("name"),
        "invoicee_representative_name": company.get("representative_name"),
        "invoicee_email": company.get("contact_email"),
        "invoicee_address": addr,
        "invoicee_business_type": company.get("business_type"),
        "invoicee_business_category": company.get("business_category"),
    }


def _build_snapshot_manual(body: Dict[str, Any]) -> Dict[str, Any]:
    """MANUAL 모드: body 의 invoicee_* 로만 snapshot. companies INSERT 금지.

    필수: 사업자번호(10자리) / 상호 / 대표자.
    선택: 이메일 / 주소 / 업태 / 종목.
    """
    bn_raw = body.get("invoicee_business_number")
    bn = _norm_bn10(bn_raw)
    corp_name = (body.get("invoicee_company_name") or "").strip()
    ceo = (body.get("invoicee_representative_name") or "").strip()
    missing: List[str] = []
    if not bn:
        missing.append("invoicee_business_number(10자리 숫자)")
    if not corp_name:
        missing.append("invoicee_company_name")
    if not ceo:
        missing.append("invoicee_representative_name")
    if missing:
        raise MemberTaxError(400, "INVOICEE_INCOMPLETE",
                             "공급받는자 필수 정보 누락: {}".format(",".join(missing)))
    email = (body.get("invoicee_email") or "").strip() or None
    address = (body.get("invoicee_address") or "").strip() or None
    biz_type = (body.get("invoicee_business_type") or "").strip() or None
    biz_class = (body.get("invoicee_business_category") or "").strip() or None
    return {
        "company_id": None,  # MANUAL 모드는 company_id 없음
        "invoicee_business_number": bn,
        "invoicee_company_name": corp_name,
        "invoicee_representative_name": ceo,
        "invoicee_email": email,
        "invoicee_address": address,
        "invoicee_business_type": biz_type,
        "invoicee_business_category": biz_class,
    }


_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                      re.IGNORECASE)


def _validate_idempotency_key(v: Any) -> str:
    if not v:
        raise MemberTaxError(400, "IDEMPOTENCY_KEY_REQUIRED",
                             "idempotency_key(uuid) 가 필요합니다.")
    s = str(v).strip()
    if not _UUID_RE.match(s):
        raise MemberTaxError(400, "INVALID_IDEMPOTENCY_KEY",
                             "idempotency_key 는 UUID 형식이어야 합니다.")
    return s


def create_manual_request(sb, actor_id: str, body: Dict[str, Any]) -> tuple[Dict[str, Any], bool]:
    """관리자 수동 세금계산서 발행요청 생성.

    Args:
        sb: supabase client
        actor_id: role 001 관리자 id (audit + requested_by)
        body: {
          idempotency_key: uuid str,
          company_mode: "EXISTING" | "MANUAL",
          company_id: str (EXISTING 모드),
          invoicee_business_number / invoicee_company_name / invoicee_representative_name / ...
                                           (MANUAL 모드),
          supply_amount: int, vat_amount: int,
          supply_date: "YYYY-MM-DD", item_name: str, issue_reason: str,
        }

    Returns:
        (row, created)  created=True → 신규 INSERT (201). False → idempotent 재조회 (200).

    계약:
      - source=ADMIN_MANUAL, doc_type=TAX_INVOICE, proof_type=TAX_INVOICE,
        payment_id=NULL, status=REQUESTED
      - total_amount = supply + vat (서버 계산; 프론트 total 무시)
      - MANUAL 모드: companies INSERT 절대 금지
    """
    idem = _validate_idempotency_key(body.get("idempotency_key"))

    # 멱등: 기존 same idempotency_key + ADMIN_MANUAL row 있으면 그대로 반환.
    ex = _load_manual_by_idempotency_key(sb, idem)
    if ex:
        return ex, False

    mode = (body.get("company_mode") or "").strip().upper()
    if mode == "EXISTING":
        snap = _build_snapshot_existing(sb, (body.get("company_id") or "").strip())
    elif mode == "MANUAL":
        snap = _build_snapshot_manual(body)
    else:
        raise MemberTaxError(400, "INVALID_COMPANY_MODE",
                             "company_mode 는 EXISTING 또는 MANUAL 이어야 합니다.")

    supply, vat, total = _validate_amounts(body.get("supply_amount"), body.get("vat_amount"))
    supply_date = _validate_supply_date(body.get("supply_date"))
    item_name = (body.get("item_name") or "").strip()
    if not item_name:
        raise MemberTaxError(400, "ITEM_NAME_REQUIRED", "품목명(item_name)이 필요합니다.")
    issue_reason = (body.get("issue_reason") or "").strip()
    if not issue_reason:
        raise MemberTaxError(400, "ISSUE_REASON_REQUIRED", "발행 사유(issue_reason)가 필요합니다.")

    insert_row = {
        "payment_id": None,                       # ADMIN_MANUAL 은 payment-less
        "company_id": snap["company_id"],
        "requested_by": actor_id,
        "source": "ADMIN_MANUAL",
        "doc_type": "TAX_INVOICE",
        "proof_type": "TAX_INVOICE",
        "invoicee_business_number": snap["invoicee_business_number"],
        "invoicee_company_name": snap["invoicee_company_name"],
        "invoicee_representative_name": snap["invoicee_representative_name"],
        "invoicee_email": snap["invoicee_email"],
        "invoicee_address": snap["invoicee_address"],
        "invoicee_business_type": snap["invoicee_business_type"],
        "invoicee_business_category": snap["invoicee_business_category"],
        "supply_amount": supply,
        "vat_amount": vat,
        "total_amount": total,                    # 서버 재계산 정본
        "supply_date": supply_date,
        "pg_method": None,
        "paid_at": None,
        "product_type": None,
        "status": "REQUESTED",
        "requested_at": _now_iso(),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        # metadata
        "idempotency_key": idem,
        "item_name": item_name,
        "issue_reason": issue_reason,
    }
    try:
        ins = sb.table("tax_invoice_requests").insert(insert_row).execute()
    except Exception as e:
        # 동시성: 같은 idempotency_key 경쟁 → 기존 row 반환 (partial UNIQUE 로 방어)
        ex2 = _load_manual_by_idempotency_key(sb, idem)
        if ex2:
            return ex2, False
        raise MemberTaxError(500, "MANUAL_REQUEST_CREATE_FAILED",
                             "수동 발행요청 생성에 실패했습니다.") from e
    if not ins.data:
        raise MemberTaxError(500, "MANUAL_REQUEST_CREATE_FAILED",
                             "수동 발행요청 생성에 실패했습니다.")
    row = _load_manual_request(sb, ins.data[0]["id"]) or ins.data[0]
    return row, True


def process_manual_request(sb, request_id: str, actor_id: Optional[str]) -> tuple[Dict[str, Any], str]:
    """관리자 수동 발행요청 processor.

    - GUARD: source=ADMIN_MANUAL, doc_type=TAX_INVOICE, status ∈ {REQUESTED, FAILED},
             payment_id NULL, 사업자번호 valid, 상호/대표자 존재, supply/vat >=0,
             total = supply+vat, supply_date/item_name/issue_reason 존재.
    - INVOICE_LIVE OFF → provider 0 / 423 / request.status=REQUESTED 유지 (FAILED 오염 금지).
    - LIVE + mock success → tax_invoices(payment_id NULL, invoice_kind ORIGINAL, ISSUED)
                            + request.status=ISSUED + tax_invoice_id 연결.
    - provider 실패 → request/ledger FAILED, retry 가능 (same request_id/mgt_key, 중복 invoice 0).

    Returns:
        (row, outcome)  outcome: "ISSUED"
    Raises:
        MemberTaxError (4xx) / propagate InvoiceError (from invoice_svc) 를 MemberTaxError 로 감싸 재던지기.
    """
    row = _load_manual_request(sb, request_id)
    if not row:
        raise MemberTaxError(404, "REQUEST_NOT_FOUND", "수동 발행요청을 찾을 수 없습니다.")

    # GUARD: 계약 준수 검증 (mutation 전)
    if row.get("source") != "ADMIN_MANUAL":
        raise MemberTaxError(409, "NOT_ADMIN_MANUAL",
                             "이 엔드포인트는 ADMIN_MANUAL 소스 요청만 처리합니다.")
    if row.get("doc_type") != "TAX_INVOICE":
        raise MemberTaxError(409, "INVALID_DOC_TYPE", "doc_type 이 TAX_INVOICE 가 아닙니다.")
    if row.get("payment_id") is not None:
        raise MemberTaxError(409, "PAYMENT_ID_MUST_BE_NULL",
                             "ADMIN_MANUAL 요청은 payment_id 가 없어야 합니다.")
    st = str(row.get("status") or "").upper()
    if st == "ISSUED":
        return row, "ISSUED"                       # idempotent
    if st == "PROCESSING":
        raise MemberTaxError(409, "REQUEST_ALREADY_PROCESSING", "이미 처리 중입니다.")
    if st == "CANCELLED":
        raise MemberTaxError(409, "REQUEST_CANCELLED", "취소된 요청입니다.")
    if st == "REVIEW_REQUIRED":
        raise MemberTaxError(409, "REQUEST_REVIEW_REQUIRED", "검토가 필요한 요청입니다.")
    # st in (REQUESTED, FAILED)

    # 필수 필드 재검증 (스냅샷 무결성)
    if not (row.get("invoicee_business_number") and row.get("invoicee_company_name")
            and row.get("invoicee_representative_name")):
        raise MemberTaxError(422, "INVOICEE_INCOMPLETE",
                             "요청 사업자정보(사업자번호/상호/대표자)가 부족합니다.")
    supply = int(row.get("supply_amount") or 0)
    vat = int(row.get("vat_amount") or 0)
    total = int(row.get("total_amount") or 0)
    if supply < 0 or vat < 0 or total != supply + vat:
        raise MemberTaxError(422, "AMOUNT_INVARIANT_VIOLATED",
                             "금액 계약 위반 (total = supply + vat).")
    if not row.get("supply_date"):
        raise MemberTaxError(422, "SUPPLY_DATE_MISSING", "공급일자가 없습니다.")
    if not row.get("item_name") or not row.get("issue_reason"):
        raise MemberTaxError(422, "MANUAL_METADATA_MISSING",
                             "품목명/발행사유가 없습니다.")

    # 상태 전이 PROCESSING
    sb.table("tax_invoice_requests").update({
        "status": "PROCESSING", "updated_at": _now_iso(),
    }).eq("id", request_id).execute()

    invoicee = {
        "corpNum": row.get("invoicee_business_number"),
        "corpName": row.get("invoicee_company_name"),
        "ceoName": row.get("invoicee_representative_name"),
        "email": row.get("invoicee_email"),
        "addr": row.get("invoicee_address"),
        "bizType": row.get("invoicee_business_type"),
        "bizClass": row.get("invoicee_business_category"),
    }

    # invoice_svc 위임 (기존 issue_tax_invoice 는 건드리지 않음 — 별도 신규 함수)
    from services.invoice_svc import InvoiceError, issue_manual_tax_invoice
    try:
        res = issue_manual_tax_invoice(
            request_id=request_id, invoicee=invoicee,
            supply=supply, vat=vat, total=total,
            supply_date=row.get("supply_date"), item_name=row.get("item_name"),
            company_id=row.get("company_id"),  # None 이면 standalone ledger
            created_by=actor_id,
        )
    except InvoiceError as e:
        # INVOICE_LIVE OFF (423) → request.status 는 REQUESTED 로 되돌림 (FAILED 오염 금지).
        if getattr(e, "code", None) == "INVOICE_GATED" or e.status_code == 423:
            sb.table("tax_invoice_requests").update({
                "status": "REQUESTED", "updated_at": _now_iso(),
            }).eq("id", request_id).execute()
            raise MemberTaxError(423, "INVOICE_GATED", e.detail)
        # 그 외 실패 → FAILED 로 mark, retry 가능
        sb.table("tax_invoice_requests").update({
            "status": "FAILED",
            "failure_code": getattr(e, "code", None) or "ISSUE_FAILED",
            "failure_reason": (e.detail or "")[:500],
            "processed_at": _now_iso(),
            "updated_at": _now_iso(),
        }).eq("id", request_id).execute()
        raise MemberTaxError(e.status_code, getattr(e, "code", None) or "ISSUE_FAILED",
                             e.detail)

    # 성공 → ISSUED + tax_invoice_id 연결
    sb.table("tax_invoice_requests").update({
        "status": "ISSUED",
        "tax_invoice_id": res.get("invoice_id"),
        "failure_code": None,
        "failure_reason": None,
        "processed_at": _now_iso(),
        "updated_at": _now_iso(),
    }).eq("id", request_id).execute()

    return _load_manual_request(sb, request_id) or row, "ISSUED"
