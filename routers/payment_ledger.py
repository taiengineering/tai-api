"""결제 원장 결선 라우터 (WO-7 PaymentLedger + BACKEND-3 issuance + BACKEND-4 수정세금계산서).

[2026-08-15 P0-보정1 → BACKEND-3 실적용] 게이트/증빙 실발행 엔드포인트를 role 001(_require_admin)로 실제 적용.
  증빙 발행은 invoice_svc 중앙 guard(저장금액·명시 supply_date·상호배타) 공통 통과.
  BACKEND-3 신규: POST /payments/tax-invoice-requests/{request_id}/process (processor).
  BACKEND-4 신규: POST /payments/refunds/{refund_id}/tax-adjustment (수정세금계산서 재처리, 운영복구용).

[2026-09-06 WO-TAX-INVOICE-ADMIN-01] 관리자 세금계산서 조회(read) 엔드포인트 추가(role 001):
  GET /payments/admin/tax-invoices (목록), GET /payments/admin/tax-invoices/{request_id} (상세).
  새 엔진/발행 로직 없음 — tax_invoice_requests/tax_invoices/payments/companies 조회만.
  doc_type=TAX_INVOICE 경계 필수(현금영수증 제외). N+1 금지(배치). tax_status 는 payment_ops._attach_tax_status 재사용.
  처리/재시도는 기존 processor(/tax-invoice-requests/{id}/process) 그대로 사용(신규 발행 엔드포인트 없음).
  PATCH-1: (1) admin list tax_invoices 배치 조회 fail-safe — 조회 실패를 '없음'으로 위장하지 않고
  invoice_projection_ok=false + 관련 필드 null. (2) q 검색에 companies fallback(name/business_number) 포함.
  PATCH-2: (A-P1) 기간검색을 requested_at 기준 + civil date 입력(422) + KST 경계([date]T00:00:00+09:00 ~ T23:59:59.999999+09:00)
  로 수정(종료일 당일 포함). (A-P2) detail request 섹션에 기존 supply_date 투영.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from routers.matching_deps import _require_admin
from routers.payment_ops import _attach_tax_status

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


def _batch_map(sb, table: str, ids: list, key: str, columns: str) -> dict:
    """id 목록을 1쿼리로 조회해 {key: row} 맵으로. N+1 금지용."""
    if not ids:
        return {}
    res = sb.table(table).select(columns).in_(key, ids).execute()
    out = {}
    for row in (res.data or []):
        out[row.get(key)] = row
    return out


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


# ── 수정세금계산서 재처리 (role 001, 운영복구용) ──
@router.post("/refunds/{refund_id}/tax-adjustment")
def refund_tax_adjustment(refund_id: str, current_user: dict = Depends(_require_admin)):
    """환불 후처리 재실행. refund/original을 DB에서 직접 읽어 수정세금계산서/요청취소. INVOICE_LIVE OFF 면 423."""
    from services.invoice_svc import InvoiceError, process_refund_tax_adjustment
    try:
        res = process_refund_tax_adjustment(refund_id, created_by=current_user["id"])
        return {"status": "success", "data": res}
    except InvoiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


# ── 관리자 세금계산서 목록 (role 001) ──
@router.get("/admin/tax-invoices")
def admin_list_tax_invoices(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    q: Optional[str] = Query(None, description="회사명·사업자번호 검색(스냅샷+companies fallback)"),
    payment_id: Optional[str] = Query(None),
    request_id: Optional[str] = Query(None),
    current_user: dict = Depends(_require_admin),
):
    """세금계산서 발행요청 운영 목록. doc_type=TAX_INVOICE 만(현금영수증 제외). 배치 조회(N+1 금지).

    기간검색(PATCH-2): requested_at(화면 표시 요청일) 기준, civil date 입력(잘못된 값 422),
    KST 경계 [date]T00:00:00+09:00 ~ T23:59:59.999999+09:00 (종료일 당일 포함).
    """
    sb = get_supabase()

    # BLOCKER-2: q 검색은 발행요청 스냅샷 + companies fallback(표시값과 일치) 모두 대상.
    matched_company_ids: list = []
    if q:
        try:
            cres = (
                sb.table("companies").select("id")
                .or_(f"name.ilike.%{q}%,business_number.ilike.%{q}%")
                .execute()
            )
            matched_company_ids = [c.get("id") for c in (cres.data or []) if c.get("id")]
        except Exception as e:  # noqa: BLE001
            log.warning("[admin tax] company 검색 실패: %s", e)
            matched_company_ids = []

    query = (
        sb.table("tax_invoice_requests")
        .select(
            "id, payment_id, company_id, source, status, requested_at, created_at, "
            "invoicee_company_name, invoicee_business_number, proof_type, "
            "supply_amount, vat_amount, total_amount",
            count="exact",
        )
        .eq("doc_type", "TAX_INVOICE")
    )
    if status:
        query = query.eq("status", status)
    if request_id:
        query = query.eq("id", request_id)
    if payment_id:
        query = query.eq("payment_id", payment_id)
    if date_from:
        query = query.gte("requested_at", f"{date_from.isoformat()}T00:00:00+09:00")
    if date_to:
        query = query.lte("requested_at", f"{date_to.isoformat()}T23:59:59.999999+09:00")
    if q:
        ors = [f"invoicee_company_name.ilike.%{q}%", f"invoicee_business_number.ilike.%{q}%"]
        for cid in matched_company_ids:
            ors.append(f"company_id.eq.{cid}")
        query = query.or_(",".join(ors))

    offset = (page - 1) * size
    res = query.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    reqs = res.data or []
    total = res.count or 0

    pay_ids = list({r["payment_id"] for r in reqs if r.get("payment_id")})
    co_ids = list({r["company_id"] for r in reqs if r.get("company_id")})
    payments = _batch_map(sb, "payments", pay_ids, "id",
                          "id, supply_amount, vat_amount, total_amount, pg_method, proof_type, paid_at")
    companies = _batch_map(sb, "companies", co_ids, "id", "id, name, business_number")

    # BLOCKER-1: invoice 배치 조회 fail-safe — 실패를 '없음'으로 위장하지 않고 null + ok=false.
    invoice_projection_ok = True
    inv_by_pid: dict = {}
    if pay_ids:
        try:
            inv = (
                sb.table("tax_invoices")
                .select("payment_id, invoice_kind, status, issued_at, nts_confirm_num")
                .in_("payment_id", pay_ids)
                .eq("doc_type", "TAX_INVOICE")
                .execute()
            )
            for iv in (inv.data or []):
                inv_by_pid.setdefault(iv.get("payment_id"), []).append(iv)
        except Exception as e:  # noqa: BLE001 — fail-safe(조회 실패 != 0건)
            invoice_projection_ok = False
            log.warning("[admin tax] invoice projection 실패: %s", e)

    st_rows = [{"id": pid} for pid in pay_ids]
    _attach_tax_status(sb, st_rows)
    tax_status_by_pid = {r["id"]: r["tax_status"] for r in st_rows}

    items = []
    for r in reqs:
        pid = r.get("payment_id")
        pay = payments.get(pid, {})
        co = companies.get(r.get("company_id"), {})
        if invoice_projection_ok:
            invs = inv_by_pid.get(pid, [])
            originals = [i for i in invs if i.get("invoice_kind") != "MODIFIED"]
            modifieds = [i for i in invs if i.get("invoice_kind") == "MODIFIED"]
            orig = next((i for i in originals if str(i.get("status")) == "ISSUED"), None)
            if orig is None and originals:
                orig = originals[0]
            inv_fields = {
                "original_invoice_status": (orig or {}).get("status"),
                "issued_at": (orig or {}).get("issued_at"),
                "nts_confirm_num": (orig or {}).get("nts_confirm_num"),
                "has_modified_invoice": len(modifieds) > 0,
                "modified_count": len(modifieds),
            }
        else:
            inv_fields = {
                "original_invoice_status": None,
                "issued_at": None,
                "nts_confirm_num": None,
                "has_modified_invoice": None,
                "modified_count": None,
            }
        item = {
            "request_id": r.get("id"),
            "payment_id": pid,
            "requested_at": r.get("requested_at") or r.get("created_at"),
            "request_status": r.get("status"),
            # [WO-TAX-INVOICE-MANUAL-01] source 노출: 자동/고객/관리자수동 구분 UI 용
            "source": r.get("source"),
            "company_name": r.get("invoicee_company_name") or co.get("name"),
            "business_number": r.get("invoicee_business_number") or co.get("business_number"),
            "payment_method": pay.get("pg_method"),
            "proof_type": r.get("proof_type") or pay.get("proof_type"),
            # [WO-TAX-INVOICE-AUTO-01 STEP 5] 3분할 금액 투영 (request snapshot 우선, payments SoT fallback).
            # 프론트 계산 금지 — authoritative 값 그대로. 재계산(total/1.1 등) 금지.
            "supply_amount": r.get("supply_amount") if r.get("supply_amount") is not None else pay.get("supply_amount"),
            "vat_amount": r.get("vat_amount") if r.get("vat_amount") is not None else pay.get("vat_amount"),
            "total_amount": r.get("total_amount") if r.get("total_amount") is not None else pay.get("total_amount"),
            "tax_status": tax_status_by_pid.get(pid, "UNKNOWN"),
            "invoice_projection_ok": invoice_projection_ok,
        }
        item.update(inv_fields)
        items.append(item)

    return {"status": "success", "data": {"items": items, "total": total, "page": page, "size": size,
            "total_pages": (total + size - 1) // size if total else 0}}


# ── 관리자 세금계산서 상세 (role 001) ──
@router.get("/admin/tax-invoices/{request_id}")
def admin_tax_invoice_detail(request_id: str, current_user: dict = Depends(_require_admin)):
    """발행요청 상세: 요청/결제/사업자스냅샷/원장(원본+수정[]). doc_type=TAX_INVOICE 경계."""
    sb = get_supabase()
    rq = (
        sb.table("tax_invoice_requests").select("*")
        .eq("id", request_id).eq("doc_type", "TAX_INVOICE").limit(1).execute()
    )
    if not rq.data:
        raise HTTPException(status_code=404, detail="세금계산서 발행요청을 찾을 수 없습니다.")
    r = rq.data[0]
    pid = r.get("payment_id")

    pay = {}
    if pid:
        p = sb.table("payments").select(
            "id, supply_amount, vat_amount, total_amount, pg_method, proof_type, paid_at, product_type"
        ).eq("id", pid).limit(1).execute()
        pay = (p.data or [{}])[0] if p.data else {}

    # COMPANY SNAPSHOT: 발행요청 스냅샷이 있으면 그대로 우선(합쳐서 덮어쓰지 않음), 없으면 companies.
    if r.get("invoicee_business_number"):
        snapshot = {
            "source": "request_snapshot",
            "company_name": r.get("invoicee_company_name"),
            "business_number": r.get("invoicee_business_number"),
            "representative_name": r.get("invoicee_representative_name"),
            "email": r.get("invoicee_email"),
            "address": r.get("invoicee_address"),
            "business_type": r.get("invoicee_business_type"),
            "business_category": r.get("invoicee_business_category"),
        }
    else:
        co = {}
        if r.get("company_id"):
            c = sb.table("companies").select(
                "name, business_number, representative_name, contact_email, "
                "contact_phone, zipcode, address_road, address_detail, address, "
                "business_type, business_category"
            ).eq("id", r["company_id"]).limit(1).execute()
            co = (c.data or [{}])[0] if c.data else {}
        addr = " ".join([x for x in [co.get("zipcode"), co.get("address_road"), co.get("address_detail")] if x]) or co.get("address")
        snapshot = {
            "source": "company",
            "company_name": co.get("name"),
            "business_number": co.get("business_number"),
            "representative_name": co.get("representative_name"),
            "email": co.get("contact_email"),
            "address": addr,
            "business_type": co.get("business_type"),
            "business_category": co.get("business_category"),
        }

    invs = []
    if pid:
        iv = (
            sb.table("tax_invoices").select(
                "id, invoice_kind, status, issued_at, nts_confirm_num, "
                "modify_code, adjustment_reason, refund_ref, total_amount, created_at"
            ).eq("payment_id", pid).eq("doc_type", "TAX_INVOICE")
            .order("created_at", desc=False).execute()
        )
        invs = iv.data or []
    originals = [i for i in invs if i.get("invoice_kind") != "MODIFIED"]
    modifieds = [i for i in invs if i.get("invoice_kind") == "MODIFIED"]

    st_rows = [{"id": pid}] if pid else []
    _attach_tax_status(sb, st_rows)
    tax_status = st_rows[0]["tax_status"] if st_rows else "UNKNOWN"

    return {"status": "success", "data": {
        "request": {
            "request_id": r.get("id"), "status": r.get("status"),
            "requested_at": r.get("requested_at") or r.get("created_at"),
            "source": r.get("source"),
            "supply_date": r.get("supply_date"),
            "failure_code": r.get("failure_code"),
            "failure_reason": r.get("failure_reason"),
            "updated_at": r.get("updated_at"),
        },
        # [PATCH-1 A-P3] 3분할 fallback 규칙 통일: request.<x> ?? payment.<x> 로 supply/vat/total 동시 결정.
        # amount(alias) = resolved total_amount (시점 혼합 금지 — list 와 detail 동일 규칙).
        "payment": {
            "payment_id": pid,
            "supply_amount": (r.get("supply_amount") if r.get("supply_amount") is not None
                              else pay.get("supply_amount")),
            "vat_amount": (r.get("vat_amount") if r.get("vat_amount") is not None
                           else pay.get("vat_amount")),
            "total_amount": (r.get("total_amount") if r.get("total_amount") is not None
                             else pay.get("total_amount")),
            # amount 는 resolved total_amount 와 동일 값 (하위호환 alias).
            "amount": (r.get("total_amount") if r.get("total_amount") is not None
                       else pay.get("total_amount")),
            "payment_method": pay.get("pg_method"), "proof_type": pay.get("proof_type"),
            "paid_at": pay.get("paid_at"),
        },
        "company_snapshot": snapshot,
        "invoice_ledger": {
            "tax_status": tax_status,
            "original": originals[0] if originals else None,
            "modified": modifieds,
        },
    }}


# ══════════════════════════════════════════════════════════════════
# [WO-TAX-INVOICE-MANUAL-01 WP-B / WP-C / WP-D / WP-E] 관리자 수동발행 라우터
# ══════════════════════════════════════════════════════════════════
class ManualRequestBody(BaseModel):
    """관리자 수동 발행 요청 body. 라우터 계층 whitelist — extra 필드 거부."""
    idempotency_key: str
    company_mode: str  # "EXISTING" | "MANUAL"
    company_id: Optional[str] = None
    # MANUAL 모드 (invoicee_* 세트)
    invoicee_business_number: Optional[str] = None
    invoicee_company_name: Optional[str] = None
    invoicee_representative_name: Optional[str] = None
    invoicee_email: Optional[str] = None
    invoicee_address: Optional[str] = None
    invoicee_business_type: Optional[str] = None
    invoicee_business_category: Optional[str] = None
    # 공통
    supply_amount: int
    vat_amount: int
    supply_date: str            # YYYY-MM-DD (사용자 명시 입력)
    item_name: str
    issue_reason: str

    class Config:
        extra = "forbid"        # payment_id/source/status 등 우회 주입 거부


# ── WP-B 업체조회 API (role 001) ──
@router.get("/admin/tax-invoice-companies")
def admin_search_companies(
    q: Optional[str] = Query(None, description="회사명·사업자번호 검색어(ilike)"),
    current_user: dict = Depends(_require_admin),
):
    """관리자 수동발행용 회사 검색. companies SoT. ≤20건 반환.

    선택 후에도 서버가 companies 에서 재조회하여 snapshot 구성 (프론트 법적정보 불신뢰).
    이 엔드포인트는 검색 편의 — 실제 발행은 POST manual 에서 companies 재조회.
    """
    sb = get_supabase()
    query = sb.table("companies").select(
        "id, name, business_number, representative_name, contact_email, contact_phone, "
        "zipcode, address, address_road, address_detail, business_type, business_category"
    )
    if q and q.strip():
        term = q.strip()
        query = query.or_(f"name.ilike.%{term}%,business_number.ilike.%{term}%")
    query = query.limit(20)
    try:
        res = query.execute()
        items = res.data or []
    except Exception as e:  # noqa: BLE001
        log.warning("[MANUAL_TAX] 회사 검색 실패: %s", e)
        items = []
    return {"status": "success", "data": {"items": items, "count": len(items)}}


# ── WP-C/D 수동 발행요청 생성 (role 001) ──
@router.post("/admin/tax-invoices/manual")
def admin_create_manual_tax_invoice_request(body: ManualRequestBody,
                                            current_user: dict = Depends(_require_admin)):
    """관리자 수동 세금계산서 발행요청 생성. 신규 201 / idempotent 기존 200 / 400·409·422 오류.

    - source = ADMIN_MANUAL, payment_id = NULL
    - EXISTING 모드: 서버가 companies 재조회 → snapshot (프론트 법적정보 무시)
    - MANUAL 모드: body.invoicee_* 로 snapshot, companies INSERT 금지
    - total_amount = supply + vat (서버 재계산; 프론트 total 무시)
    - idempotency_key partial UNIQUE (DDL) → 더블클릭/재시도 안전
    """
    from services import tax_manual_svc as m_svc
    from services.tax_invoice_request_svc import MemberTaxError
    sb = get_supabase()
    try:
        row, created = m_svc.create_manual_request(sb, current_user["id"], body.dict())
    except MemberTaxError as e:
        detail = e.payload if e.payload is not None else {"code": e.code, "detail": e.detail}
        raise HTTPException(status_code=e.status_code, detail=detail) from e
    return {"status": "success", "data": row, "created": created}


# ── WP-E 수동 발행 processor (role 001) ──
@router.post("/admin/tax-invoices/manual/{request_id}/process")
def admin_process_manual_tax_invoice(request_id: str,
                                     current_user: dict = Depends(_require_admin)):
    """관리자 수동 발행 processor. 기존 payment 기반 /invoice/tax 와 분리.

    - GUARD: source=ADMIN_MANUAL, status ∈ {REQUESTED, FAILED}, payment_id NULL
    - INVOICE_LIVE OFF → 423 (mutation 0, request.status=REQUESTED 유지 — FAILED 오염 금지)
    - LIVE + provider 성공 → tax_invoices(payment_id NULL, ISSUED) + request.status=ISSUED
    - provider 실패 → request/ledger FAILED, retry 가능 (same mgt_key, 중복 invoice 0)
    """
    from services import tax_manual_svc as m_svc
    from services.tax_invoice_request_svc import MemberTaxError
    sb = get_supabase()
    try:
        row, outcome = m_svc.process_manual_request(sb, request_id, current_user["id"])
    except MemberTaxError as e:
        detail = e.payload if e.payload is not None else {"code": e.code, "detail": e.detail}
        raise HTTPException(status_code=e.status_code, detail=detail) from e
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
