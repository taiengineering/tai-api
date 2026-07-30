"""세금계산서·현금영수증 발행 서비스 (WO-4 InvoiceService) — 팝빌 API 실연동.

Goal: G-ms4je4z3-33eada (게이트 보강 G-ms5pdquz-9e76e5)
- 팝빌(링크허브) 세금계산서 registIssue/cancelIssue, 현금영수증 registIssue/revoke.
- 팝빌 SDK는 지연 import (미설치 시 501, 배포 `/health` 안전).
- LinkID/SecretKey·공급자(TAI) 정보는 env 상수만 참조 (R-008 하드코딩 금지).
- tax_invoices 원장 기록(PENDING→ISSUED/FAILED/CANCELLED), 발행/취소 audit.
- doc_type: TAX_INVOICE(세금계산서) | CASH_RECEIPT(현금영수증).

[2026-07-30 실호출 게이트 A-2] INVOICE_LIVE(기본 off):
  운영 정책상 실발행(팝빌 실 registIssue)은 사람 게이트 완료 전까지 실호출을 막는다.
  플래그가 꺼져 있으면 검증까지만 수행하고, 원장 오염 없이 423으로 차단하며 감사만 남긴다.
  발행취소(cancel)도 동일 게이트 — 실호출이 잠긴 상태에서는 실 취소도 나가지 않는다.
  허용 소스: 배포 ENV(INVOICE_LIVE=on) 또는 어드민 실행게이트(ops_feature_gate, 준비완료 통과 후 활성화).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase
from services import audit_svc
from services.payment_helpers import now_iso, split_supply_vat

log = logging.getLogger(__name__)

_INVOICE_LIVE_ENV = "INVOICE_LIVE"


class InvoiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def invoice_live() -> bool:
    """실발행 실호출 허용 여부. 기본 off.

    ENV(INVOICE_LIVE=on) 또는 어드민 실행게이트(ops_feature_gate) 활성 시 허용.
    게이트 서비스 오류 시 보수적으로 ENV 만 본다.
    """
    try:
        from services.ops_gate_svc import is_live
        return is_live(_INVOICE_LIVE_ENV)
    except Exception:  # noqa: BLE001
        return os.getenv(_INVOICE_LIVE_ENV, "").strip().lower() in ("1", "true", "on", "yes")


def _assert_invoice_live(payment_id: Optional[str], doc_type: str, op: str,
                         created_by: Optional[str]) -> None:
    """게이트: 실호출이 잠겨 있으면 원장 기록 없이 423 차단 + 감사."""
    if invoice_live():
        return
    audit_svc.record(
        "INVOICE_GATED", "payment", entity_id=payment_id, actor_id=created_by,
        after={"doc_type": doc_type, "op": op, "gate": "INVOICE_LIVE=off"},
    )
    raise InvoiceError(
        423,
        "실발행 실호출이 운영 게이트로 잠겨 있습니다(INVOICE_LIVE 비활성). "
        "실제 팝빌 발행/취소는 나가지 않았습니다. 실행하려면 운영자가 실호출을 활성화해야 합니다.",
    )


# ── 팝빌 설정 (env 상수) ──────────────────────────────────────────────
def _popbill_conf() -> Dict[str, str]:
    link_id = os.getenv("POPBILL_LINK_ID", "").strip()
    secret_key = os.getenv("POPBILL_SECRET_KEY", "").strip()
    if not link_id or not secret_key:
        raise InvoiceError(501, "팝빌 연동정보(POPBILL_LINK_ID/SECRET_KEY)가 설정되지 않았습니다.")
    return {
        "link_id": link_id,
        "secret_key": secret_key,
        "is_test": os.getenv("POPBILL_IS_TEST", "true").lower() == "true",
        "corp_num": os.getenv("TAI_CORP_NUM", "").strip(),          # TAI 사업자번호
        "corp_name": os.getenv("TAI_CORP_NAME", "").strip(),
        "ceo_name": os.getenv("TAI_CEO_NAME", "").strip(),
        "corp_addr": os.getenv("TAI_CORP_ADDR", "").strip(),
        "biz_type": os.getenv("TAI_BIZ_TYPE", "").strip(),
        "biz_class": os.getenv("TAI_BIZ_CLASS", "").strip(),
        "user_id": os.getenv("POPBILL_USER_ID", "").strip(),
    }


def _tax_service(conf: Dict[str, Any]):
    """팝빌 세금계산서 서비스 (지연 import)."""
    try:
        from popbill import TaxinvoiceService
    except Exception as e:  # noqa: BLE001
        raise InvoiceError(501, f"팝빌 SDK 미설치: {e}") from e
    svc = TaxinvoiceService(conf["link_id"], conf["secret_key"])
    svc.IsTest = conf["is_test"]
    return svc


def _cash_service(conf: Dict[str, Any]):
    """팝빌 현금영수증 서비스 (지연 import)."""
    try:
        from popbill import CashbillService
    except Exception as e:  # noqa: BLE001
        raise InvoiceError(501, f"팝빌 SDK 미설치: {e}") from e
    svc = CashbillService(conf["link_id"], conf["secret_key"])
    svc.IsTest = conf["is_test"]
    return svc


# ── 공통 헬퍼 ────────────────────────────────────────────────────────
def _load_payment(payment_id: str) -> Dict[str, Any]:
    res = (
        get_supabase().table("payments")
        .select("id, status_code, total_amount, company_id, product_type, paid_at")
        .eq("id", payment_id).limit(1).execute()
    )
    if not res.data:
        raise InvoiceError(404, "결제 건을 찾을 수 없습니다.")
    return res.data[0]


def _make_mgt_key(payment_id: str, doc_type: str) -> str:
    """팝빌 문서번호(중복방지). 영문/숫자/-/_ 만, 24자 이내."""
    prefix = "TX" if doc_type == "TAX_INVOICE" else "CR"
    return f"{prefix}-{payment_id.replace('-', '')[:20]}"


def _insert_invoice(row: Dict[str, Any]) -> str:
    res = get_supabase().table("tax_invoices").insert(row).execute()
    if not res.data:
        raise InvoiceError(500, "발행 원장 생성 실패")
    return res.data[0]["id"]


def _update_invoice(invoice_id: str, patch: Dict[str, Any]) -> None:
    get_supabase().table("tax_invoices").update(patch).eq("id", invoice_id).execute()


# ── 세금계산서 발행 ──────────────────────────────────────────────────
def issue_tax_invoice(payment_id: str, invoicee: Dict[str, str], created_by: Optional[str] = None) -> dict:
    """매출 정발행. invoicee={corpNum, corpName, ceoName, email, addr?, bizType?, bizClass?}."""
    conf = _popbill_conf()
    if not conf["corp_num"]:
        raise InvoiceError(501, "공급자(TAI) 사업자번호(TAI_CORP_NUM)가 설정되지 않았습니다.")
    for k in ("corpNum", "corpName", "ceoName"):
        if not invoicee.get(k):
            raise InvoiceError(400, f"공급받는자 정보({k})가 필요합니다.")

    payment = _load_payment(payment_id)
    if payment["status_code"] != "SUCCESS":
        raise InvoiceError(400, "결제완료(SUCCESS) 건만 발행할 수 있습니다.")

    # 게이트: 실호출 잠금 시 원장 오염 없이 여기서 차단.
    _assert_invoice_live(payment_id, "TAX_INVOICE", "ISSUE", created_by)

    total = int(payment["total_amount"] or 0)
    supply, tax = split_supply_vat(total)
    mgt_key = _make_mgt_key(payment_id, "TAX_INVOICE")
    write_date = datetime.now().strftime("%Y%m%d")

    invoice_id = _insert_invoice({
        "payment_id": payment_id,
        "company_id": payment.get("company_id"),
        "doc_type": "TAX_INVOICE",
        "mgt_key": mgt_key,
        "invoicee_type": "사업자",
        "supply_cost": supply, "tax": tax, "total_amount": total,
        "status": "PENDING", "created_by": created_by, "created_at": now_iso(),
    })

    try:
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
            detailList=[TaxinvoiceDetail(
                serialNum=1, purchaseDT=write_date,
                itemName=payment.get("product_type") or "TAI Safe 서비스",
                supplyCost=str(supply), tax=str(tax),
            )],
        )
        result = svc.registIssue(conf["corp_num"], ti, UserID=conf["user_id"] or None)
        nts = getattr(result, "ntsConfirmNum", "") or ""
        _update_invoice(invoice_id, {
            "status": "ISSUED", "nts_confirm_num": nts, "issued_at": now_iso(),
            "popbill_raw": {"code": getattr(result, "code", None), "message": getattr(result, "message", None), "ntsConfirmNum": nts},
        })
        audit_svc.record("INVOICE_ISSUE", "payment", entity_id=payment_id, actor_id=created_by,
                         after={"invoice_id": invoice_id, "doc_type": "TAX_INVOICE", "nts": nts, "amount": total})
        return {"invoice_id": invoice_id, "nts_confirm_num": nts, "status": "ISSUED"}
    except InvoiceError:
        _update_invoice(invoice_id, {"status": "FAILED"})
        raise
    except Exception as e:  # 팝빌 PopbillException 포함
        _update_invoice(invoice_id, {"status": "FAILED", "popbill_raw": {"error": str(e)}})
        audit_svc.record("INVOICE_ISSUE", "payment", entity_id=payment_id, actor_id=created_by,
                         after={"invoice_id": invoice_id, "doc_type": "TAX_INVOICE", "status": "FAILED", "error": str(e)})
        raise InvoiceError(400, f"세금계산서 발행 실패: {e}") from e


# ── 현금영수증 발행 ──────────────────────────────────────────────────
def issue_cash_receipt(payment_id: str, trade_usage: str, identity_num: str,
                       created_by: Optional[str] = None) -> dict:
    """현금영수증 발행. trade_usage='소득공제용'(개인)|'지출증빙용'(사업자), identity_num=식별번호."""
    if trade_usage not in ("소득공제용", "지출증빙용"):
        raise InvoiceError(400, "trade_usage는 소득공제용 또는 지출증빙용이어야 합니다.")
    if not identity_num:
        raise InvoiceError(400, "구매자 식별번호가 필요합니다.")
    conf = _popbill_conf()
    if not conf["corp_num"]:
        raise InvoiceError(501, "가맹점(TAI) 사업자번호(TAI_CORP_NUM)가 설정되지 않았습니다.")

    payment = _load_payment(payment_id)
    if payment["status_code"] != "SUCCESS":
        raise InvoiceError(400, "결제완료(SUCCESS) 건만 발행할 수 있습니다.")

    # 게이트: 실호출 잠금 시 원장 오염 없이 여기서 차단.
    _assert_invoice_live(payment_id, "CASH_RECEIPT", "ISSUE", created_by)

    total = int(payment["total_amount"] or 0)
    supply, tax = split_supply_vat(total)
    mgt_key = _make_mgt_key(payment_id, "CASH_RECEIPT")
    trade_dt = datetime.now().strftime("%Y%m%d%H%M%S")

    invoice_id = _insert_invoice({
        "payment_id": payment_id,
        "company_id": payment.get("company_id"),
        "doc_type": "CASH_RECEIPT",
        "mgt_key": mgt_key,
        "trade_usage": trade_usage,
        "invoicee_type": "사업자" if trade_usage == "지출증빙용" else "개인",
        "identity_num": identity_num,
        "supply_cost": supply, "tax": tax, "total_amount": total,
        "status": "PENDING", "created_by": created_by, "created_at": now_iso(),
    })

    try:
        from popbill import Cashbill
        svc = _cash_service(conf)
        cb = Cashbill(
            mgtKey=mgt_key, tradeDT=trade_dt, tradeType="승인거래",
            taxationType="과세", tradeUsage=trade_usage, tradeOpt="일반",
            supplyCost=str(supply), tax=str(tax), serviceFee="0", totalAmount=str(total),
            franchiseCorpNum=conf["corp_num"], franchiseCorpName=conf["corp_name"],
            franchiseCEOName=conf["ceo_name"], franchiseAddr=conf["corp_addr"] or None,
            identityNum=identity_num,
        )
        result = svc.registIssue(conf["corp_num"], cb, "", UserID=conf["user_id"] or None)
        nts = getattr(result, "confirmNum", "") or getattr(result, "ntsConfirmNum", "") or ""
        _update_invoice(invoice_id, {
            "status": "ISSUED", "nts_confirm_num": nts, "issued_at": now_iso(),
            "popbill_raw": {"code": getattr(result, "code", None), "message": getattr(result, "message", None), "confirmNum": nts},
        })
        audit_svc.record("INVOICE_ISSUE", "payment", entity_id=payment_id, actor_id=created_by,
                         after={"invoice_id": invoice_id, "doc_type": "CASH_RECEIPT", "trade_usage": trade_usage, "nts": nts, "amount": total})
        return {"invoice_id": invoice_id, "nts_confirm_num": nts, "status": "ISSUED"}
    except InvoiceError:
        _update_invoice(invoice_id, {"status": "FAILED"})
        raise
    except Exception as e:
        _update_invoice(invoice_id, {"status": "FAILED", "popbill_raw": {"error": str(e)}})
        audit_svc.record("INVOICE_ISSUE", "payment", entity_id=payment_id, actor_id=created_by,
                         after={"invoice_id": invoice_id, "doc_type": "CASH_RECEIPT", "status": "FAILED", "error": str(e)})
        raise InvoiceError(400, f"현금영수증 발행 실패: {e}") from e


# ── 취소 ────────────────────────────────────────────────────────────
def cancel(invoice_id: str, reason: str = "", created_by: Optional[str] = None) -> dict:
    """발행취소. 세금계산서=cancelIssue, 현금영수증=revokeRegistIssue."""
    res = get_supabase().table("tax_invoices").select("*").eq("id", invoice_id).limit(1).execute()
    if not res.data:
        raise InvoiceError(404, "발행 건을 찾을 수 없습니다.")
    inv = res.data[0]
    if inv["status"] != "ISSUED":
        raise InvoiceError(400, "발행완료(ISSUED) 건만 취소할 수 있습니다.")

    # 게이트: 실 취소도 실호출이므로 동일 차단.
    _assert_invoice_live(inv.get("payment_id"), inv.get("doc_type", ""), "CANCEL", created_by)

    conf = _popbill_conf()

    try:
        if inv["doc_type"] == "TAX_INVOICE":
            svc = _tax_service(conf)
            svc.cancelIssue(conf["corp_num"], "SELL", inv["mgt_key"], reason or "발행취소",
                            UserID=conf["user_id"] or None)
        else:
            svc = _cash_service(conf)
            svc.revokeRegistIssue(conf["corp_num"], inv["mgt_key"], conf["corp_num"],
                                  UserID=conf["user_id"] or None)
        _update_invoice(invoice_id, {"status": "CANCELLED"})
        audit_svc.record("INVOICE_CANCEL", "payment", entity_id=inv.get("payment_id"), actor_id=created_by,
                         before={"status": "ISSUED"}, after={"invoice_id": invoice_id, "reason": reason})
        return {"invoice_id": invoice_id, "status": "CANCELLED"}
    except InvoiceError:
        raise
    except Exception as e:
        raise InvoiceError(400, f"발행취소 실패: {e}") from e


# ── 상태 조회 ────────────────────────────────────────────────────────
def status(payment_id: str) -> List[Dict[str, Any]]:
    res = (
        get_supabase().table("tax_invoices")
        .select("id, doc_type, status, nts_confirm_num, total_amount, issued_at, created_at")
        .eq("payment_id", payment_id).order("created_at", desc=True).execute()
    )
    return res.data or []


# ── 웹훅 (팝빌 상태변경 PUSH) ─────────────────────────────────────────
def handle_webhook(payload: Dict[str, Any]) -> None:
    """팝빌 상태변경 수신 → tax_invoices.status 동기화 (best-effort)."""
    try:
        mgt_key = payload.get("MgtKey") or payload.get("mgtKey")
        state_code = payload.get("stateCode") or payload.get("StateCode")
        if not mgt_key:
            return
        # 상태코드 매핑 (팝빌: 3xx 발행완료 계열, 취소 계열 별도)
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
