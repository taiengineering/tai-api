"""세금계산서·현금영수증 발행 서비스 (WO-4 + BACKEND-3 guard + BACKEND-4 수정세금계산서) — 팝빌 실연동.

BACKEND-3: 저장금액 그대로 · 명시 supply_date · 중앙 issuance guard · ledger lifecycle · INVOICE_LIVE gate 선행 · popbill seam.
BACKEND-4: 환불 DONE → 원 TAX_INVOICE ISSUED 있으면 수정세금계산서(전액철환불=코드4/그외=코드2),
  없으면 미발행 request CANCELLED. 동일 refund 중복방지(parent_invoice_id, refund_ref). INVOICE_LIVE gate 동일 적용.

[2026-07-30 A-2] INVOICE_LIVE(기본 off): 사람 게이트 전 실호출 차단(423, 원장 오염 없음).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase
from services import audit_svc
from services.payment_helpers import now_iso
from services.tax_invoice_request_svc import canonical_payment_instrument
from services.time import now_kst

log = logging.getLogger(__name__)

_INVOICE_LIVE_ENV = "INVOICE_LIVE"


class InvoiceError(Exception):
    def __init__(self, status_code: int, detail: str, code: Optional[str] = None):
        self.status_code = status_code
        self.detail = detail
        self.code = code
        super().__init__(detail)


def invoice_live() -> bool:
    try:
        from services.ops_gate_svc import is_live
        return is_live(_INVOICE_LIVE_ENV)
    except Exception:  # noqa: BLE001
        return os.getenv(_INVOICE_LIVE_ENV, "").strip().lower() in ("1", "true", "on", "yes")


def _assert_invoice_live(payment_id: Optional[str], doc_type: str, op: str,
                         created_by: Optional[str]) -> None:
    if invoice_live():
        return
    audit_svc.record(
        "INVOICE_GATED", "payment", entity_id=payment_id, actor_id=created_by,
        after={"doc_type": doc_type, "op": op, "gate": "INVOICE_LIVE=off"},
    )
    raise InvoiceError(
        423,
        "실발행 실호출이 운영 게이트로 잠겨 있습니다(INVOICE_LIVE 비활성). 실제 팝빌 발행/취소는 나가지 않았습니다.",
        "INVOICE_GATED",
    )


# ── 팝빌 설정 (env 상수) ──
def _popbill_conf() -> Dict[str, Any]:
    link_id = os.getenv("POPBILL_LINK_ID", "").strip()
    secret_key = os.getenv("POPBILL_SECRET_KEY", "").strip()
    if not link_id or not secret_key:
        raise InvoiceError(501, "팝빌 연동정보(POPBILL_LINK_ID/SECRET_KEY)가 설정되지 않았습니다.")
    return {
        "link_id": link_id, "secret_key": secret_key,
        "is_test": os.getenv("POPBILL_IS_TEST", "true").lower() == "true",
        "corp_num": os.getenv("TAI_CORP_NUM", "").strip(),
        "corp_name": os.getenv("TAI_CORP_NAME", "").strip(),
        "ceo_name": os.getenv("TAI_CEO_NAME", "").strip(),
        "corp_addr": os.getenv("TAI_CORP_ADDR", "").strip(),
        "biz_type": os.getenv("TAI_BIZ_TYPE", "").strip(),
        "biz_class": os.getenv("TAI_BIZ_CLASS", "").strip(),
        "user_id": os.getenv("POPBILL_USER_ID", "").strip(),
    }


def _tax_service(conf: Dict[str, Any]):
    try:
        from popbill import TaxinvoiceService
    except Exception as e:  # noqa: BLE001
        raise InvoiceError(501, f"팝빌 SDK 미설치: {e}") from e
    svc = TaxinvoiceService(conf["link_id"], conf["secret_key"])
    svc.IsTest = conf["is_test"]
    return svc


def _cash_service(conf: Dict[str, Any]):
    try:
        from popbill import CashbillService
    except Exception as e:  # noqa: BLE001
        raise InvoiceError(501, f"팝빌 SDK 미설치: {e}") from e
    svc = CashbillService(conf["link_id"], conf["secret_key"])
    svc.IsTest = conf["is_test"]
    return svc


# ── 공통 헬퍼 ──
def _load_payment(payment_id: str) -> Dict[str, Any]:
    res = (
        get_supabase().table("payments")
        .select("id, status_code, company_id, product_type, pg_method, proof_type, "
                "supply_amount, vat_amount, total_amount, paid_at")
        .eq("id", payment_id).limit(1).execute()
    )
    if not res.data:
        raise InvoiceError(404, "결제 건을 찾을 수 없습니다.")
    return res.data[0]


def _make_mgt_key(payment_id: str, doc_type: str) -> str:
    prefix = "TX" if doc_type == "TAX_INVOICE" else "CR"
    return f"{prefix}-{payment_id.replace('-', '')[:20]}"


def _insert_invoice(row: Dict[str, Any]) -> str:
    res = get_supabase().table("tax_invoices").insert(row).execute()
    if not res.data:
        raise InvoiceError(500, "발행 원장 생성 실패")
    return res.data[0]["id"]


def _update_invoice(invoice_id: str, patch: Dict[str, Any]) -> None:
    get_supabase().table("tax_invoices").update(patch).eq("id", invoice_id).execute()


def _doc_statuses(sb, payment_id: str, doc_type: str) -> List[str]:
    """해당 payment · doc_type · ORIGINAL 의 status 목록."""
    res = sb.table("tax_invoices").select("doc_type, status, invoice_kind").eq("payment_id", payment_id).execute()
    return [r.get("status") for r in (res.data or [])
            if r.get("doc_type") == doc_type and (r.get("invoice_kind") in (None, "ORIGINAL"))]


def _existing_original(sb, payment_id: str, doc_type: str) -> Optional[Dict[str, Any]]:
    res = (
        sb.table("tax_invoices")
        .select("id, mgt_key, status, nts_confirm_num, invoice_kind, doc_type")
        .eq("payment_id", payment_id).eq("doc_type", doc_type).execute()
    )
    for r in (res.data or []):
        if r.get("invoice_kind") in (None, "ORIGINAL"):
            return r
    return None


def _amounts(payment: Dict[str, Any]) -> tuple:
    supply = int(payment.get("supply_amount") or 0)
    tax = int(payment.get("vat_amount") or 0)
    total = int(payment.get("total_amount") or 0)
    if supply + tax != total:
        raise InvoiceError(409, "결제 금액 구성(공급가+부가세=합계)이 일치하지 않습니다.", "PAYMENT_AMOUNT_INCONSISTENT")
    return supply, tax, total


def _fmt_supply_date(supply_date: Optional[str]) -> str:
    if not supply_date:
        raise InvoiceError(400, "공급일자(supply_date)가 필요합니다.", "SUPPLY_DATE_REQUIRED")
    try:
        d = datetime.strptime(str(supply_date).strip(), "%Y-%m-%d")
    except Exception as e:  # noqa: BLE001
        raise InvoiceError(400, "공급일자 형식(YYYY-MM-DD)이 올바르지 않습니다.", "INVALID_SUPPLY_DATE") from e
    return d.strftime("%Y%m%d")


# ── 중앙 issuance guard ──
def _assert_tax_issuable(payment: Dict[str, Any], sb) -> None:
    if payment.get("status_code") != "SUCCESS":
        raise InvoiceError(409, "결제완료(SUCCESS) 건만 발행할 수 있습니다.", "PAYMENT_NOT_SUCCESS")
    method = canonical_payment_instrument(payment.get("pg_method"))
    proof = payment.get("proof_type")
    if method == "CARD":
        raise InvoiceError(409, "카드 결제는 세금계산서를 발행하지 않습니다.", "CARD_RECEIPT_IS_EVIDENCE")
    if method == "UNKNOWN":
        raise InvoiceError(409, "결제수단을 확인할 수 없습니다.", "UNKNOWN_PAYMENT_METHOD")
    if proof == "CASH_RECEIPT":
        raise InvoiceError(409, "현금영수증을 선택한 결제입니다.", "CASH_RECEIPT_SELECTED")
    if method == "ACCOUNT_TRANSFER":
        if proof != "TAX_INVOICE":
            raise InvoiceError(409, "계좌이체는 증빙선택(TAX_INVOICE) 확정 건만 실발행합니다.", "PROOF_NOT_TAX_INVOICE")
    elif method == "VBANK":
        if proof == "CARD_RECEIPT":
            raise InvoiceError(409, "증빙 선택이 결제수단과 맞지 않습니다.", "PROOF_CONFLICT")
    cr = _doc_statuses(sb, payment["id"], "CASH_RECEIPT")
    if any(s in ("PENDING", "ISSUED", "FAILED") for s in cr):
        raise InvoiceError(409, "현금영수증이 존재해 세금계산서를 발행할 수 없습니다.", "CASH_RECEIPT_EXISTS")
    if any(s == "CANCELLED" for s in cr):
        raise InvoiceError(409, "현금영수증 이력이 있어 확인이 필요합니다.", "CASH_RECEIPT_HISTORY_REVIEW")


def _assert_cash_issuable(payment: Dict[str, Any], sb) -> None:
    if payment.get("status_code") != "SUCCESS":
        raise InvoiceError(409, "결제완료(SUCCESS) 건만 발행할 수 있습니다.", "PAYMENT_NOT_SUCCESS")
    method = canonical_payment_instrument(payment.get("pg_method"))
    if method == "CARD":
        raise InvoiceError(409, "카드 결제는 현금영수증을 발행하지 않습니다.", "CARD_RECEIPT_IS_EVIDENCE")
    if payment.get("proof_type") != "CASH_RECEIPT":
        raise InvoiceError(409, "현금영수증 선택(CASH_RECEIPT) 건만 발행합니다.", "PROOF_NOT_CASH_RECEIPT")
    ti = _doc_statuses(sb, payment["id"], "TAX_INVOICE")
    if any(s in ("PENDING", "ISSUED", "FAILED") for s in ti):
        raise InvoiceError(409, "세금계산서가 존재해 현금영수증을 발행할 수 없습니다.", "TAX_INVOICE_EXISTS")
    if any(s == "CANCELLED" for s in ti):
        raise InvoiceError(409, "세금계산서 이력이 있어 확인이 필요합니다.", "TAX_INVOICE_HISTORY_REVIEW")


# ── popbill 실의존 seam (테스트 mock) ──
def _popbill_issue_tax(conf: Dict[str, Any], *, mgt_key: str, write_date: str,
                       supply: int, tax: int, total: int, invoicee: Dict[str, str],
                       item_name: str) -> Dict[str, Any]:
    from popbill import Taxinvoice, TaxinvoiceDetail
    svc = _tax_service(conf)
    ti = Taxinvoice(
        writeDate=write_date, issueType="정발행", taxType="과세", chargeDirection="정과금",
        purposeType="영수",
        supplyCostTotal=str(supply), taxTotal=str(tax), totalAmount=str(total),
        invoicerCorpNum=conf["corp_num"], invoicerCorpName=conf["corp_name"],
        invoicerCEOName=conf["ceo_name"], invoicerMgtKey=mgt_key,
        invoicerAddr=conf["corp_addr"] or None,
        invoicerBizType=conf["biz_type"] or None, invoicerBizClass=conf["biz_class"] or None,
        invoiceeType="사업자",
        invoiceeCorpNum=invoicee["corpNum"], invoiceeCorpName=invoicee["corpName"],
        invoiceeCEOName=invoicee["ceoName"], invoiceeEmail1=invoicee.get("email"),
        invoiceeAddr=invoicee.get("addr"),
        invoiceeBizType=invoicee.get("bizType"), invoiceeBizClass=invoicee.get("bizClass"),
        detailList=[TaxinvoiceDetail(serialNum=1, purchaseDT=write_date, itemName=item_name,
                                     supplyCost=str(supply), tax=str(tax))],
    )
    result = svc.registIssue(conf["corp_num"], ti, UserID=conf["user_id"] or None)
    nts = getattr(result, "ntsConfirmNum", "") or ""
    return {"nts": nts, "code": getattr(result, "code", None), "message": getattr(result, "message", None)}


def _popbill_issue_cash(conf: Dict[str, Any], *, mgt_key: str, trade_dt: str, trade_usage: str,
                        identity_num: str, supply: int, tax: int, total: int) -> Dict[str, Any]:
    from popbill import Cashbill
    svc = _cash_service(conf)
    cb = Cashbill(
        mgtKey=mgt_key, tradeDT=trade_dt, tradeType="승인거래", taxationType="과세",
        tradeUsage=trade_usage, tradeOpt="일반",
        supplyCost=str(supply), tax=str(tax), serviceFee="0", totalAmount=str(total),
        franchiseCorpNum=conf["corp_num"], franchiseCorpName=conf["corp_name"],
        franchiseCEOName=conf["ceo_name"], franchiseAddr=conf["corp_addr"] or None,
        identityNum=identity_num,
    )
    result = svc.registIssue(conf["corp_num"], cb, "", UserID=conf["user_id"] or None)
    nts = getattr(result, "confirmNum", "") or getattr(result, "ntsConfirmNum", "") or ""
    return {"nts": nts, "code": getattr(result, "code", None), "message": getattr(result, "message", None)}


# ── 세금계산서 발행 ──
def issue_tax_invoice(payment_id: str, invoicee: Dict[str, str], supply_date: Optional[str],
                      created_by: Optional[str] = None) -> dict:
    """매출 정발행. 저장 금액 그대로 + 명시 supply_date + 중앙 guard + ledger lifecycle."""
    for k in ("corpNum", "corpName", "ceoName"):
        if not invoicee.get(k):
            raise InvoiceError(400, f"공급받는자 정보({k})가 필요합니다.", "INVOICEE_INCOMPLETE")
    write_date = _fmt_supply_date(supply_date)

    sb = get_supabase()
    payment = _load_payment(payment_id)
    _assert_tax_issuable(payment, sb)
    supply, tax, total = _amounts(payment)
    mgt_key = _make_mgt_key(payment_id, "TAX_INVOICE")

    existing = _existing_original(sb, payment_id, "TAX_INVOICE")
    invoice_id: Optional[str] = None
    if existing:
        st = existing.get("status")
        if st == "ISSUED":
            return {"invoice_id": existing["id"], "nts_confirm_num": existing.get("nts_confirm_num") or "", "status": "ISSUED"}
        if st == "PENDING":
            raise InvoiceError(409, "발행 처리가 진행 중입니다.", "INVOICE_ALREADY_PROCESSING")
        if st == "CANCELLED":
            raise InvoiceError(409, "취소 이력이 있어 확인이 필요합니다.", "INVOICE_HISTORY_REVIEW")
        invoice_id = existing["id"]
        mgt_key = existing.get("mgt_key") or mgt_key

    _assert_invoice_live(payment_id, "TAX_INVOICE", "ISSUE", created_by)

    conf = _popbill_conf()
    if not conf["corp_num"]:
        raise InvoiceError(501, "공급자(TAI) 사업자번호(TAI_CORP_NUM)가 설정되지 않았습니다.")
    item_name = payment.get("product_type") or "TAI Safe 서비스"

    if invoice_id:
        _update_invoice(invoice_id, {"status": "PENDING", "supply_cost": supply, "tax": tax,
                                     "total_amount": total, "updated_at": now_iso()})
    else:
        invoice_id = _insert_invoice({
            "payment_id": payment_id, "company_id": payment.get("company_id"),
            "doc_type": "TAX_INVOICE", "invoice_kind": "ORIGINAL", "mgt_key": mgt_key,
            "invoicee_type": "사업자", "supply_cost": supply, "tax": tax, "total_amount": total,
            "status": "PENDING", "created_by": created_by, "created_at": now_iso(),
        })

    try:
        pr = _popbill_issue_tax(conf, mgt_key=mgt_key, write_date=write_date, supply=supply,
                                tax=tax, total=total, invoicee=invoicee, item_name=item_name)
        _update_invoice(invoice_id, {
            "status": "ISSUED", "nts_confirm_num": pr["nts"], "issued_at": now_iso(),
            "popbill_raw": {"code": pr.get("code"), "message": pr.get("message"), "ntsConfirmNum": pr["nts"]},
        })
        audit_svc.record("INVOICE_ISSUE", "payment", entity_id=payment_id, actor_id=created_by,
                         after={"invoice_id": invoice_id, "doc_type": "TAX_INVOICE", "nts": pr["nts"], "amount": total})
        return {"invoice_id": invoice_id, "nts_confirm_num": pr["nts"], "status": "ISSUED"}
    except InvoiceError:
        _update_invoice(invoice_id, {"status": "FAILED"})
        raise
    except Exception as e:  # noqa: BLE001
        _update_invoice(invoice_id, {"status": "FAILED", "popbill_raw": {"error": str(e)}})
        audit_svc.record("INVOICE_ISSUE", "payment", entity_id=payment_id, actor_id=created_by,
                         after={"invoice_id": invoice_id, "doc_type": "TAX_INVOICE", "status": "FAILED", "error": str(e)})
        raise InvoiceError(400, f"세금계산서 발행 실패: {e}", "ISSUE_FAILED") from e


# ── 현금영수증 발행 ──
def issue_cash_receipt(payment_id: str, trade_usage: str, identity_num: str,
                       created_by: Optional[str] = None) -> dict:
    if trade_usage not in ("소득공제용", "지출증빙용"):
        raise InvoiceError(400, "trade_usage는 소득공제용 또는 지출증빙용이어야 합니다.")
    if not identity_num:
        raise InvoiceError(400, "구매자 식별번호가 필요합니다.")

    sb = get_supabase()
    payment = _load_payment(payment_id)
    _assert_cash_issuable(payment, sb)
    supply, tax, total = _amounts(payment)
    mgt_key = _make_mgt_key(payment_id, "CASH_RECEIPT")

    existing = _existing_original(sb, payment_id, "CASH_RECEIPT")
    invoice_id: Optional[str] = None
    if existing:
        st = existing.get("status")
        if st == "ISSUED":
            return {"invoice_id": existing["id"], "nts_confirm_num": existing.get("nts_confirm_num") or "", "status": "ISSUED"}
        if st == "PENDING":
            raise InvoiceError(409, "발행 처리가 진행 중입니다.", "INVOICE_ALREADY_PROCESSING")
        if st == "CANCELLED":
            raise InvoiceError(409, "취소 이력이 있어 확인이 필요합니다.", "INVOICE_HISTORY_REVIEW")
        invoice_id = existing["id"]
        mgt_key = existing.get("mgt_key") or mgt_key

    _assert_invoice_live(payment_id, "CASH_RECEIPT", "ISSUE", created_by)

    conf = _popbill_conf()
    if not conf["corp_num"]:
        raise InvoiceError(501, "가맹점(TAI) 사업자번호(TAI_CORP_NUM)가 설정되지 않았습니다.")
    trade_dt = now_kst().strftime("%Y%m%d%H%M%S")

    if invoice_id:
        _update_invoice(invoice_id, {"status": "PENDING", "supply_cost": supply, "tax": tax,
                                     "total_amount": total, "updated_at": now_iso()})
    else:
        invoice_id = _insert_invoice({
            "payment_id": payment_id, "company_id": payment.get("company_id"),
            "doc_type": "CASH_RECEIPT", "invoice_kind": "ORIGINAL", "mgt_key": mgt_key,
            "trade_usage": trade_usage,
            "invoicee_type": "사업자" if trade_usage == "지출증빙용" else "개인",
            "identity_num": identity_num,
            "supply_cost": supply, "tax": tax, "total_amount": total,
            "status": "PENDING", "created_by": created_by, "created_at": now_iso(),
        })

    try:
        pr = _popbill_issue_cash(conf, mgt_key=mgt_key, trade_dt=trade_dt, trade_usage=trade_usage,
                                 identity_num=identity_num, supply=supply, tax=tax, total=total)
        _update_invoice(invoice_id, {
            "status": "ISSUED", "nts_confirm_num": pr["nts"], "issued_at": now_iso(),
            "popbill_raw": {"code": pr.get("code"), "message": pr.get("message"), "confirmNum": pr["nts"]},
        })
        audit_svc.record("INVOICE_ISSUE", "payment", entity_id=payment_id, actor_id=created_by,
                         after={"invoice_id": invoice_id, "doc_type": "CASH_RECEIPT", "trade_usage": trade_usage, "nts": pr["nts"], "amount": total})
        return {"invoice_id": invoice_id, "nts_confirm_num": pr["nts"], "status": "ISSUED"}
    except InvoiceError:
        _update_invoice(invoice_id, {"status": "FAILED"})
        raise
    except Exception as e:  # noqa: BLE001
        _update_invoice(invoice_id, {"status": "FAILED", "popbill_raw": {"error": str(e)}})
        audit_svc.record("INVOICE_ISSUE", "payment", entity_id=payment_id, actor_id=created_by,
                         after={"invoice_id": invoice_id, "doc_type": "CASH_RECEIPT", "status": "FAILED", "error": str(e)})
        raise InvoiceError(400, f"현금영수증 발행 실패: {e}", "ISSUE_FAILED") from e


# ── BACKEND-4: 환불 → 수정세금계산서 ──
def _load_refund(sb, refund_id: str) -> Optional[Dict[str, Any]]:
    res = (sb.table("refunds")
           .select("id, payment_id, refund_type, amount, status, reason_text, created_at, cumulative_refunded")
           .eq("id", refund_id).limit(1).execute())
    data = res.data or []
    return data[0] if data else None


def _load_original_issued(sb, payment_id: str) -> Optional[Dict[str, Any]]:
    res = (sb.table("tax_invoices")
           .select("id, company_id, doc_type, invoice_kind, status, nts_confirm_num, supply_cost, tax, total_amount, mgt_key")
           .eq("payment_id", payment_id).execute())
    for r in (res.data or []):
        if (r.get("doc_type") == "TAX_INVOICE" and r.get("invoice_kind") in (None, "ORIGINAL")
                and r.get("status") == "ISSUED"):
            return r
    return None


def _existing_modified(sb, parent_invoice_id: str, refund_id: str) -> Optional[Dict[str, Any]]:
    res = (sb.table("tax_invoices")
           .select("id, mgt_key, status, invoice_kind, parent_invoice_id, refund_ref, modify_code")
           .eq("refund_ref", refund_id).execute())
    for r in (res.data or []):
        if r.get("invoice_kind") == "MODIFIED" and str(r.get("parent_invoice_id")) == str(parent_invoice_id):
            return r
    return None


def _make_modified_mgt_key(refund_id: str) -> str:
    return f"MT-{str(refund_id).replace('-', '')[:20]}"


def _kst_yyyymmdd(ts) -> str:
    if not ts:
        raise InvoiceError(409, "환불 완료시각을 확인할 수 없습니다.", "REFUND_DATE_MISSING")
    s = str(ts).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except Exception:  # noqa: BLE001
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
        except Exception as e:  # noqa: BLE001
            raise InvoiceError(409, "환불 완료시각 형식을 해석할 수 없습니다.", "REFUND_DATE_INVALID") from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(timedelta(hours=9))).strftime("%Y%m%d")


def _resolve_modified_invoicee(sb, payment_id: str, original: Dict[str, Any]) -> Dict[str, Any]:
    res = (sb.table("tax_invoice_requests")
           .select("invoicee_business_number, invoicee_company_name, invoicee_representative_name, "
                   "invoicee_email, invoicee_address, invoicee_business_type, invoicee_business_category, status, doc_type")
           .eq("payment_id", payment_id).execute())
    for r in (res.data or []):
        if (r.get("doc_type") == "TAX_INVOICE" and r.get("status") == "ISSUED"
                and r.get("invoicee_business_number") and r.get("invoicee_company_name")
                and r.get("invoicee_representative_name")):
            return {"corpNum": r["invoicee_business_number"], "corpName": r["invoicee_company_name"],
                    "ceoName": r["invoicee_representative_name"], "email": r.get("invoicee_email"),
                    "addr": r.get("invoicee_address"), "bizType": r.get("invoicee_business_type"),
                    "bizClass": r.get("invoicee_business_category")}
    company_id = original.get("company_id")
    if company_id:
        cres = (sb.table("companies")
                .select("business_number, company_name, representative_name, address, business_type, business_category")
                .eq("id", company_id).limit(1).execute())
        c = (cres.data or [None])[0]
        if c and c.get("business_number") and c.get("company_name") and c.get("representative_name"):
            return {"corpNum": c["business_number"], "corpName": c["company_name"],
                    "ceoName": c["representative_name"], "email": None,
                    "addr": c.get("address"), "bizType": c.get("business_type"), "bizClass": c.get("business_category")}
    raise InvoiceError(409, "수정세금계산서 공급받는자 정보(사업자번호/상호/대표자)가 부족합니다.", "MODIFIED_INVOICEE_INCOMPLETE")


def _cancel_unissued_requests(sb, payment_id: str) -> int:
    res = sb.table("tax_invoice_requests").select("id, status, doc_type").eq("payment_id", payment_id).execute()
    n = 0
    for r in (res.data or []):
        if r.get("doc_type") == "TAX_INVOICE" and r.get("status") not in ("ISSUED", "CANCELLED"):
            sb.table("tax_invoice_requests").update(
                {"status": "CANCELLED", "failure_code": "REFUNDED_BEFORE_ISSUE", "updated_at": now_iso()}
            ).eq("id", r["id"]).execute()
            n += 1
    return n


def _popbill_issue_modified_tax(conf: Dict[str, Any], *, mgt_key: str, write_date: str, modify_code: int,
                                org_nts: str, supply: int, vat: int, total: int,
                                invoicee: Dict[str, str], item_name: str) -> Dict[str, Any]:
    from popbill import Taxinvoice, TaxinvoiceDetail
    svc = _tax_service(conf)
    ti = Taxinvoice(
        writeDate=write_date, issueType="정발행", taxType="과세", chargeDirection="정과금", purposeType="영수",
        modifyCode=str(modify_code), orgNTSConfirmNum=org_nts,
        supplyCostTotal=str(supply), taxTotal=str(vat), totalAmount=str(total),
        invoicerCorpNum=conf["corp_num"], invoicerCorpName=conf["corp_name"], invoicerCEOName=conf["ceo_name"],
        invoicerMgtKey=mgt_key, invoicerAddr=conf["corp_addr"] or None,
        invoicerBizType=conf["biz_type"] or None, invoicerBizClass=conf["biz_class"] or None,
        invoiceeType="사업자", invoiceeCorpNum=invoicee["corpNum"], invoiceeCorpName=invoicee["corpName"],
        invoiceeCEOName=invoicee["ceoName"], invoiceeEmail1=invoicee.get("email"),
        invoiceeAddr=invoicee.get("addr"), invoiceeBizType=invoicee.get("bizType"), invoiceeBizClass=invoicee.get("bizClass"),
        detailList=[TaxinvoiceDetail(serialNum=1, purchaseDT=write_date, itemName=item_name,
                                     supplyCost=str(supply), tax=str(vat))],
    )
    result = svc.registIssue(conf["corp_num"], ti, UserID=conf["user_id"] or None)
    nts = getattr(result, "ntsConfirmNum", "") or ""
    return {"nts": nts, "code": getattr(result, "code", None), "message": getattr(result, "message", None)}


def process_refund_tax_adjustment(refund_id: str, created_by: Optional[str] = None) -> dict:
    """환불 DONE 후처리: 원 TAX_INVOICE ISSUED 있으면 수정세금계산서, 없으면 미발행 request 취소."""
    sb = get_supabase()
    refund = _load_refund(sb, refund_id)
    if not refund:
        raise InvoiceError(404, "환불 건을 찾을 수 없습니다.", "REFUND_NOT_FOUND")
    if refund.get("status") != "DONE":
        raise InvoiceError(409, "환불완료(DONE) 건만 처리할 수 있습니다.", "REFUND_NOT_DONE")
    payment_id = refund["payment_id"]
    payment = _load_payment(payment_id)
    original = _load_original_issued(sb, payment_id)
    if not original or not original.get("nts_confirm_num"):
        n = _cancel_unissued_requests(sb, payment_id)
        return {"outcome": "REQUEST_CANCELLED" if n else "NOOP", "cancelled_requests": n, "modified_invoice_id": None}
    return _issue_modified_for_refund(sb, refund, payment, original, created_by)


def _issue_modified_for_refund(sb, refund: Dict[str, Any], payment: Dict[str, Any],
                               original: Dict[str, Any], created_by: Optional[str]) -> dict:
    mgt_key = _make_modified_mgt_key(refund["id"])
    existing = _existing_modified(sb, original["id"], refund["id"])
    invoice_id: Optional[str] = None
    if existing:
        st = existing.get("status")
        if st == "ISSUED":
            return {"outcome": "ISSUED", "modified_invoice_id": existing["id"],
                    "modify_code": existing.get("modify_code"), "status": "ISSUED"}
        if st == "PENDING":
            raise InvoiceError(409, "수정세금계산서 처리가 진행 중입니다.", "INVOICE_ALREADY_PROCESSING")
        invoice_id = existing["id"]              # FAILED → 재사용
        mgt_key = existing.get("mgt_key") or mgt_key

    total = int(payment.get("total_amount") or 0)
    refund_amount = int(refund.get("amount") or 0)
    cumulative = int(refund.get("cumulative_refunded") or 0)
    o_supply = int(original.get("supply_cost") or 0)
    o_tax = int(original.get("tax") or 0)
    o_total = int(original.get("total_amount") or 0)
    if refund_amount == total and cumulative == total:
        modify_code = 4
        neg_supply, neg_vat, neg_total = -o_supply, -o_tax, -o_total
    else:
        modify_code = 2
        refund_supply = round(refund_amount * o_supply / o_total) if o_total else 0
        refund_vat = refund_amount - refund_supply
        neg_supply, neg_vat, neg_total = -refund_supply, -refund_vat, -refund_amount

    reason_date = _kst_yyyymmdd(refund.get("created_at"))
    invoicee = _resolve_modified_invoicee(sb, refund["payment_id"], original)
    org_nts = original["nts_confirm_num"]
    item_name = payment.get("product_type") or "TAI Safe 서비스"

    _assert_invoice_live(refund["payment_id"], "TAX_INVOICE", "MODIFY", created_by)  # 423 no mutation
    conf = _popbill_conf()
    if not conf["corp_num"]:
        raise InvoiceError(501, "공급자(TAI) 사업자번호(TAI_CORP_NUM)가 설정되지 않았습니다.")

    if invoice_id:
        _update_invoice(invoice_id, {"status": "PENDING", "supply_cost": neg_supply, "tax": neg_vat,
                                     "total_amount": neg_total, "modify_code": modify_code, "updated_at": now_iso()})
    else:
        invoice_id = _insert_invoice({
            "payment_id": refund["payment_id"], "company_id": original.get("company_id") or payment.get("company_id"),
            "doc_type": "TAX_INVOICE", "invoice_kind": "MODIFIED", "mgt_key": mgt_key,
            "parent_invoice_id": original["id"], "modify_code": modify_code,
            "org_nts_confirm_num": org_nts, "refund_ref": refund["id"],
            "adjustment_reason": refund.get("reason_text"), "invoicee_type": "사업자",
            "supply_cost": neg_supply, "tax": neg_vat, "total_amount": neg_total,
            "status": "PENDING", "created_by": created_by, "created_at": now_iso(),
        })

    try:
        pr = _popbill_issue_modified_tax(conf, mgt_key=mgt_key, write_date=reason_date, modify_code=modify_code,
                                         org_nts=org_nts, supply=neg_supply, vat=neg_vat, total=neg_total,
                                         invoicee=invoicee, item_name=item_name)
        _update_invoice(invoice_id, {
            "status": "ISSUED", "nts_confirm_num": pr["nts"], "issued_at": now_iso(),
            "popbill_raw": {"code": pr.get("code"), "message": pr.get("message"), "ntsConfirmNum": pr["nts"]},
        })
        audit_svc.record("INVOICE_MODIFY", "payment", entity_id=refund["payment_id"], actor_id=created_by,
                         after={"invoice_id": invoice_id, "modify_code": modify_code, "refund_ref": refund["id"],
                                "org_nts": org_nts, "amount": neg_total})
        return {"outcome": "ISSUED", "modified_invoice_id": invoice_id, "modify_code": modify_code, "status": "ISSUED"}
    except InvoiceError:
        _update_invoice(invoice_id, {"status": "FAILED"})
        raise
    except Exception as e:  # noqa: BLE001
        _update_invoice(invoice_id, {"status": "FAILED", "popbill_raw": {"error": str(e)}})
        audit_svc.record("INVOICE_MODIFY", "payment", entity_id=refund["payment_id"], actor_id=created_by,
                         after={"invoice_id": invoice_id, "status": "FAILED", "error": str(e)})
        raise InvoiceError(400, f"수정세금계산서 발행 실패: {e}", "MODIFIED_ISSUE_FAILED") from e


# ── 취소 (변경없음) ──
def cancel(invoice_id: str, reason: str = "", created_by: Optional[str] = None) -> dict:
    res = get_supabase().table("tax_invoices").select("*").eq("id", invoice_id).limit(1).execute()
    if not res.data:
        raise InvoiceError(404, "발행 건을 찾을 수 없습니다.")
    inv = res.data[0]
    if inv["status"] != "ISSUED":
        raise InvoiceError(400, "발행완료(ISSUED) 건만 취소할 수 있습니다.")
    _assert_invoice_live(inv.get("payment_id"), inv.get("doc_type", ""), "CANCEL", created_by)
    conf = _popbill_conf()
    try:
        if inv["doc_type"] == "TAX_INVOICE":
            svc = _tax_service(conf)
            svc.cancelIssue(conf["corp_num"], "SELL", inv["mgt_key"], reason or "발행취소", UserID=conf["user_id"] or None)
        else:
            svc = _cash_service(conf)
            svc.revokeRegistIssue(conf["corp_num"], inv["mgt_key"], conf["corp_num"], UserID=conf["user_id"] or None)
        _update_invoice(invoice_id, {"status": "CANCELLED"})
        audit_svc.record("INVOICE_CANCEL", "payment", entity_id=inv.get("payment_id"), actor_id=created_by,
                         before={"status": "ISSUED"}, after={"invoice_id": invoice_id, "reason": reason})
        return {"invoice_id": invoice_id, "status": "CANCELLED"}
    except InvoiceError:
        raise
    except Exception as e:  # noqa: BLE001
        raise InvoiceError(400, f"발행취소 실패: {e}") from e


def status(payment_id: str) -> List[Dict[str, Any]]:
    res = (
        get_supabase().table("tax_invoices")
        .select("id, doc_type, status, nts_confirm_num, total_amount, issued_at, created_at")
        .eq("payment_id", payment_id).order("created_at", desc=True).execute()
    )
    return res.data or []


def handle_webhook(payload: Dict[str, Any]) -> None:
    try:
        mgt_key = payload.get("MgtKey") or payload.get("mgtKey")
        state_code = payload.get("stateCode") or payload.get("StateCode")
        if not mgt_key:
            return
        patch: Dict[str, Any] = {"popbill_raw": payload}
        if state_code is not None:
            sc = int(state_code)
            if sc >= 600:
                patch["status"] = "CANCELLED"
            elif sc >= 300:
                patch["status"] = "ISSUED"
        get_supabase().table("tax_invoices").update(patch).eq("mgt_key", mgt_key).execute()
    except Exception as e:  # noqa: BLE001
        log.warning("[INVOICE] webhook 처리 실패(best-effort): %s", e)
