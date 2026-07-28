"""환불 서비스 (WO-1 RefundService) — 이니시스 INIAPI 취소/환불 실연동.

Goal: G-ms4je4z3-33eada
규격: docs/INICIS_INTEGRATION_SPEC.md §4 (전체취소/부분취소)
- URL/키/IP는 payment_helpers의 env 상수만 참조 (R-008 하드코딩 금지)
- 모든 성공/실패는 refunds 대장에 기록 (사유 필수, 누적환불 검증)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests as _requests

from db.supabase_client import get_supabase
from services.payment_helpers import (
    INICIS_CLIENT_IP,
    INICIS_INIAPI_KEY,
    INICIS_MID,
    REFUND_URL,
    now_iso,
    sha512,
    ts_yyyymmddhhmmss,
)
from services.payment_svc import PaymentPrepareError

log = logging.getLogger(__name__)

_OUTBOUND_PROXY_ENV = "OUTBOUND_PROXY"


def _proxies() -> Optional[Dict[str, str]]:
    """이니시스 화이트리스트 IP(iwinV 프록시) 경유. env 없으면 직접."""
    import os

    proxy = os.getenv(_OUTBOUND_PROXY_ENV, "").strip()
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


def _load_payment(payment_id: str) -> Dict[str, Any]:
    supabase = get_supabase()
    res = (
        supabase.table("payments")
        .select("id, status_code, total_amount, pg_method, payment_type, inicis_tid, product_type")
        .eq("id", payment_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise PaymentPrepareError(404, "결제 건을 찾을 수 없습니다.")
    return res.data[0]


def _paymethod(payment: Dict[str, Any]) -> str:
    """이니시스 취소 paymethod 매핑."""
    pg = (payment.get("pg_method") or payment.get("payment_type") or "").upper()
    if pg in ("VBANK", "VACCT"):
        return "Vacct"
    return "Card"


def _cumulative_done(payment_id: str) -> int:
    """이 결제의 DONE 환불 누적액."""
    supabase = get_supabase()
    res = (
        supabase.table("refunds")
        .select("amount")
        .eq("payment_id", payment_id)
        .eq("status", "DONE")
        .execute()
    )
    return sum(int(r["amount"]) for r in (res.data or []))


def _insert_refund(row: Dict[str, Any]) -> str:
    supabase = get_supabase()
    res = supabase.table("refunds").insert(row).execute()
    if not res.data:
        raise PaymentPrepareError(500, "환불 대장 생성 실패")
    return res.data[0]["id"]


def _update_refund(refund_id: str, patch: Dict[str, Any]) -> None:
    get_supabase().table("refunds").update(patch).eq("id", refund_id).execute()


def _call_inicis_refund(params: Dict[str, str]) -> Dict[str, Any]:
    """INIAPI refund 호출. 성공 판정 resultCode='00'."""
    try:
        resp = _requests.post(
            REFUND_URL,
            data=params,
            timeout=30,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
            proxies=_proxies(),
        )
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        raise PaymentPrepareError(502, f"이니시스 환불 API 호출 실패: {e}") from e
    return data


def run_refund(payment_id: str, reason: str = "", cancelled_by: Optional[str] = None) -> dict:
    """전체취소 — SHA512(INIAPIKey+type+paymethod+timestamp+clientIp+mid+tid)."""
    if not reason:
        raise PaymentPrepareError(400, "환불 사유는 필수입니다.")
    payment = _load_payment(payment_id)
    if payment["status_code"] not in ("SUCCESS", "PARTIAL_REFUNDED"):
        raise PaymentPrepareError(400, "환불 가능한 상태(SUCCESS)가 아닙니다.")
    tid = payment.get("inicis_tid")
    if not tid:
        raise PaymentPrepareError(400, "거래번호(tid)가 없어 환불할 수 없습니다.")

    total = int(payment["total_amount"] or 0)
    done = _cumulative_done(payment_id)
    remaining = total - done
    if remaining <= 0:
        raise PaymentPrepareError(409, "이미 전액 환불되었습니다.")

    paymethod = _paymethod(payment)
    refund_id = _insert_refund({
        "payment_id": payment_id,
        "refund_type": "FULL",
        "amount": remaining,
        "reason_text": reason,
        "inicis_tid": tid,
        "status": "REQUESTED",
        "processed_by": cancelled_by,
        "created_at": now_iso(),
    })

    ts = ts_yyyymmddhhmmss()
    hash_data = sha512(INICIS_INIAPI_KEY + "Refund" + paymethod + ts + INICIS_CLIENT_IP + INICIS_MID + tid)
    params = {
        "type": "Refund",
        "paymethod": paymethod,
        "timestamp": ts,
        "clientIp": INICIS_CLIENT_IP,
        "mid": INICIS_MID,
        "tid": tid,
        "msg": reason,
        "hashData": hash_data,
    }
    result = _call_inicis_refund(params)

    if str(result.get("resultCode", "")) == "00":
        _update_refund(refund_id, {
            "status": "DONE",
            "cumulative_refunded": total,
            "inicis_refund_tid": result.get("tid", ""),
            "inicis_raw": result,
        })
        get_supabase().table("payments").update(
            {"status_code": "CANCELLED", "updated_at": now_iso()}
        ).eq("id", payment_id).execute()
        return {"status": "success", "refund_id": refund_id, "amount": remaining, "inicis": result}

    _update_refund(refund_id, {"status": "FAILED", "inicis_raw": result})
    raise PaymentPrepareError(400, result.get("resultMsg", "이니시스 환불 실패"))


def run_partial_refund(payment_id: str, amount: int, reason: str = "", cancelled_by: Optional[str] = None) -> dict:
    """부분취소 — SHA512(...+tid+price+confirmPrice). price=취소금액, confirmPrice=잔여."""
    if not reason:
        raise PaymentPrepareError(400, "환불 사유는 필수입니다.")
    if not amount or int(amount) <= 0:
        raise PaymentPrepareError(400, "취소 금액이 올바르지 않습니다.")
    amount = int(amount)

    payment = _load_payment(payment_id)
    if payment["status_code"] not in ("SUCCESS", "PARTIAL_REFUNDED"):
        raise PaymentPrepareError(400, "환불 가능한 상태(SUCCESS)가 아닙니다.")
    tid = payment.get("inicis_tid")
    if not tid:
        raise PaymentPrepareError(400, "거래번호(tid)가 없어 환불할 수 없습니다.")

    total = int(payment["total_amount"] or 0)
    done = _cumulative_done(payment_id)
    if done + amount > total:
        raise PaymentPrepareError(400, f"원금을 초과할 수 없습니다. (잔여 {total - done}원)")
    confirm_price = total - done - amount  # 이번 취소 후 잔여

    paymethod = _paymethod(payment)
    refund_id = _insert_refund({
        "payment_id": payment_id,
        "refund_type": "PARTIAL",
        "amount": amount,
        "reason_text": reason,
        "inicis_tid": tid,
        "status": "REQUESTED",
        "processed_by": cancelled_by,
        "created_at": now_iso(),
    })

    ts = ts_yyyymmddhhmmss()
    hash_data = sha512(
        INICIS_INIAPI_KEY + "PartialRefund" + paymethod + ts + INICIS_CLIENT_IP
        + INICIS_MID + tid + str(amount) + str(confirm_price)
    )
    params = {
        "type": "PartialRefund",
        "paymethod": paymethod,
        "timestamp": ts,
        "clientIp": INICIS_CLIENT_IP,
        "mid": INICIS_MID,
        "tid": tid,
        "price": str(amount),
        "confirmPrice": str(confirm_price),
        "msg": reason,
        "hashData": hash_data,
    }
    result = _call_inicis_refund(params)

    if str(result.get("resultCode", "")) == "00":
        new_cumulative = done + amount
        _update_refund(refund_id, {
            "status": "DONE",
            "cumulative_refunded": new_cumulative,
            "inicis_refund_tid": result.get("tid", ""),
            "inicis_raw": result,
        })
        new_status = "CANCELLED" if new_cumulative >= total else "PARTIAL_REFUNDED"
        get_supabase().table("payments").update(
            {"status_code": new_status, "updated_at": now_iso()}
        ).eq("id", payment_id).execute()
        return {
            "status": "success",
            "refund_id": refund_id,
            "amount": amount,
            "cumulative": new_cumulative,
            "inicis": result,
        }

    _update_refund(refund_id, {"status": "FAILED", "inicis_raw": result})
    raise PaymentPrepareError(400, result.get("resultMsg", "이니시스 부분환불 실패"))
