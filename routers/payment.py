"""
이니시스 INIStdPay 표준결제 라우터 — v4.1.0

v4.1.0 (2026-04-27)
  [FEAT] /payments/billing/pay — 빌링 결제 전용 페이지 추가
         SaaS 페이지에서 이 URL로 리다이렉트하면 inilitepay.inicis.com 빌키발급 시작

v4.0.0 (2026-04-27)
  매뉴얼 기반 전면 재작성
"""
from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from db.supabase_client import get_supabase
from schemas.payment import (
    DiagnosisVbankPrepareBody,
    PartialRefundBody,
    PrepareBody,
    RefundBody,
    VbankPrepareBody,
)
from services.payment_svc import (
    PaymentPrepareError,
    call_pay_auth,
    create_vbank_record,
    load_sign_key,
    process_auth_failure,
    process_card_success,
    process_vbank_deposit,
    process_vbank_issued,
    run_inicis_prepare,
    run_partial_refund,
    run_refund,
)
from services.payment_helpers import FRONT_RETURN_URL, load_template, now_iso as _now_iso

log = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["결제"])


# ── HTML 페이지 ────────────────────────────────────────────────────────

@router.get("/pricing", response_class=HTMLResponse, include_in_schema=True)
def payment_pricing_page():
    return HTMLResponse(content=load_template("pricing.html"), status_code=200)


@router.get("/result", response_class=HTMLResponse, include_in_schema=True)
def payment_result_page():
    return HTMLResponse(content=load_template("result.html"), status_code=200)


@router.get("/billing/terms", response_class=HTMLResponse, include_in_schema=True)
def payment_billing_terms_page():
    """구독 이용 안내 페이지 — 이니시스 정기결제 심사용"""
    return HTMLResponse(content=load_template("billing_terms.html"), status_code=200)


@router.get("/billing/pay", response_class=HTMLResponse, include_in_schema=True)
def payment_billing_pay_page():
    """빌링 결제 전용 페이지 — SaaS 구독 결제 시작점.

    사용법: SaaS 페이지에서 아래 URL로 리다이렉트
    https://api.taieng.co.kr/payments/billing/pay
      ?user_id={userId}
      &amount={amount}
      &product_type=SAAS_FACILITY
      &goodname=TAI Safe 산업 STARTER
      &plan_code=IND_STARTER
      &company_id={companyId}
      &buyername={name}
      &buyertel={tel}
      &buyeremail={email}

    이 페이지가 /payments/inicis/billing/prepare API를 호출하고,
    응답 파라미터로 inilitepay.inicis.com 빌키발급 폼을 자동 제출합니다.
    """
    return HTMLResponse(content=load_template("billing_pay.html"), status_code=200)


# ── 단건결제 ───────────────────────────────────────────────────────────

@router.post("/inicis/prepare")
def inicis_prepare(body: PrepareBody):
    """결제 준비 — STEP1 (user_id, product_type 필수)"""
    try:
        return run_inicis_prepare(body)
    except PaymentPrepareError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e


@router.post("/inicis/return", include_in_schema=True)
async def inicis_return(request: Request):
    """결제 인증 콜백 — STEP2→STEP3"""
    try:
        form = await request.form()
        data: Dict[str, Any] = dict(form)
    except Exception:
        try:
            data = await request.json()
        except Exception:
            return RedirectResponse(f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=파싱실패", status_code=302)

    result_code = data.get("resultCode", "")
    auth_token  = data.get("authToken", "")
    auth_url    = data.get("authUrl", "")
    idc_name    = data.get("idc_name", "")
    order_id    = data.get("orderNumber") or data.get("oid", "")
    goodname    = data.get("goodname", "TAI Safe")
    price       = data.get("price", "")
    paymethod   = data.get("paymethod", "")
    log.info(f"[INICIS STEP2] resultCode={result_code} oid={order_id} paymethod={paymethod}")

    supabase = get_supabase()

    if result_code and result_code != "0000":
        result_msg = data.get("resultMsg", "인증 실패")
        return RedirectResponse(
            f"{FRONT_RETURN_URL}?resultCode=FAIL&msg={urllib.parse.quote(result_msg)}&oid={order_id}",
            status_code=302
        )

    pay_res = supabase.table("payments").select("*").eq("inicis_order_id", order_id).limit(1).execute()
    if not pay_res.data:
        return RedirectResponse(f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=주문번호미확인&oid={order_id}", status_code=302)

    payment    = pay_res.data[0]
    payment_id = payment["id"]

    if not auth_url:
        return RedirectResponse(f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=authUrl없음&oid={order_id}", status_code=302)

    supabase.table("payments").update({
        "memo": f"authToken_prefix={auth_token[:32]} idc={idc_name} authUrl={auth_url[:50]}",
        "updated_at": _now_iso(),
    }).eq("id", payment_id).execute()

    sign_key = load_sign_key()
    try:
        auth_result = call_pay_auth(auth_token, auth_url, sign_key)
    except Exception as e:
        process_auth_failure(payment_id, f"승인 API 실패: {e}", {})
        return RedirectResponse(f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=승인API오류&oid={order_id}", status_code=302)

    is_ok = str(auth_result.get("resultCode", "")) == "0000"

    if is_ok:
        pg_method = auth_result.get("payMethod", paymethod) or paymethod

        if pg_method in ("Vbank", "VBANK"):
            out = process_vbank_issued(payment_id, order_id, auth_result, goodname=goodname, price=price)
            qs = urllib.parse.urlencode(out["qs_params"])
            return RedirectResponse(f"{FRONT_RETURN_URL}?{qs}", status_code=302)

        # 후처리(계약 생성·알림): process_card_success → on_payment_success_sync
        out = process_card_success(payment, auth_result, pg_method, order_id=order_id, goodname=goodname, price=price)
        qs = urllib.parse.urlencode(out["qs_params"])
        return RedirectResponse(f"{FRONT_RETURN_URL}?{qs}", status_code=302)

    fail_msg = auth_result.get("resultMsg", "승인 실패")
    process_auth_failure(payment_id, fail_msg, auth_result)
    return RedirectResponse(
        f"{FRONT_RETURN_URL}?resultCode=FAIL&msg={urllib.parse.quote(fail_msg)}&oid={order_id}",
        status_code=302,
    )


@router.post("/inicis/noti", include_in_schema=True)
async def inicis_noti(request: Request):
    """이니시스 서버 노티 — STEP2 백업"""
    try:
        form = await request.form()
        data: Dict[str, Any] = dict(form)
    except Exception:
        try:
            data = await request.json()
        except Exception:
            return "OK"

    auth_token   = data.get("authToken", "")
    auth_url     = data.get("authUrl", "")
    order_id     = data.get("orderNumber") or data.get("oid", "")
    paymethod    = data.get("paymethod", "")
    supabase     = get_supabase()
    sign_key     = load_sign_key()

    pay_res = supabase.table("payments").select(
        "id, status_code, contract_id, product_type, period_months"
    ).eq("inicis_order_id", order_id).limit(1).execute()
    if not pay_res.data:
        return "OK"

    payment = pay_res.data[0]
    if payment["status_code"] == "SUCCESS" or not auth_url:
        return "OK"

    try:
        auth_result = call_pay_auth(auth_token, auth_url, sign_key)
    except Exception:
        return "OK"

    if auth_result.get("resultCode") == "0000":
        pg_method = auth_result.get("payMethod", paymethod) or paymethod
        process_card_success(
            payment, auth_result, pg_method,
            order_id="", goodname="", price="",
            with_redirect_qs=False,
        )
    return "OK"


# ── VBANK (가상계좌) ───────────────────────────────────────────────────

@router.post("/vbank/prepare")
def vbank_prepare(body: VbankPrepareBody):
    """연결 서비스 가상계좌 발급"""
    try:
        return create_vbank_record(body, load_sign_key())
    except PaymentPrepareError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e


@router.post("/diagnosis/vbank-prepare")
def diagnosis_vbank_prepare(body: DiagnosisVbankPrepareBody):
    """유료 진단 전용 가상계좌 발급 준비 (비회원 토큰 허용)."""
    proxy_body = VbankPrepareBody(
        user_id=None,
        auth_token=body.auth_token,
        public_token=body.public_token,
        product_type="DIAGNOSIS",
        amount=body.amount,
        goodname=body.goodname,
        matching_contract_id=None,
        buyername=body.buyername,
        buyertel=body.buyertel,
        buyeremail=body.buyeremail,
    )
    result = vbank_prepare(proxy_body)

    if body.invoice_requested and (body.invoice_biz_no or body.invoice_email):
        try:
            supabase = get_supabase()
            payment_id = (result.get("data") or {}).get("payment_id")
            if payment_id:
                supabase.table("diagnosis_purchases").insert({
                    "payment_ref": payment_id,
                    "invoice_requested": True,
                    "invoice_biz_no": body.invoice_biz_no,
                    "invoice_email": body.invoice_email,
                    "created_at": _now_iso(),
                }).execute()
        except Exception as e:
            log.warning("[diagnosis vbank] invoice save failed: %s", e)

    return result


@router.post("/vbank/noti", include_in_schema=True)
async def vbank_noti(request: Request):
    """이니시스 VBANK 입금 확인 노티 (웹훅)"""
    try:
        form = await request.form()
        data: Dict[str, Any] = dict(form)
    except Exception:
        try:
            data = await request.json()
        except Exception:
            return "OK"

    order_id = data.get("orderNumber") or data.get("oid", "")
    result_code = data.get("resultCode", "")
    depositor = data.get("vbankInputName", "")
    log.info(f"[VBANK NOTI] oid={order_id} resultCode={result_code}")

    return process_vbank_deposit(order_id, result_code, depositor, data)


# ── 취소/환불 ──────────────────────────────────────────────────────────

@router.post("/{payment_id}/refund")
def refund_payment(payment_id: str, body: RefundBody):
    """전체 취소 — iniapi.inicis.com/api/v1/refund"""
    try:
        return run_refund(payment_id, body.reason, body.cancelled_by)
    except PaymentPrepareError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e


@router.post("/{payment_id}/partial-refund")
def partial_refund_payment(payment_id: str, body: PartialRefundBody):
    """부분 취소 — iniapi.inicis.com/api/v1/refund (PartialRefund)"""
    try:
        return run_partial_refund(payment_id, body.amount, body.reason)
    except PaymentPrepareError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
