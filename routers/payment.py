"""
이니시스 INIStdPay 표준결제 라우터 — v3.4.0

v3.4.0 (2026-04-23)
  [FEAT] /payments/billing/terms — 구독 이용 안내 페이지 추가 (이니시스 심사용)
         - 공개 HTML 페이지 (로그인 불필요)
         - 결제 주기/해지 방법/환불 정책/문의처 명시
         - /payments/pricing?type=billing 배너에서 링크

v3.3.0 (2026-04-23)
  [FEAT] /payments/pricing 에 단건/정기 토글 추가 (?type=billing)
         - 기본은 단건결제 (기존과 동일)
         - ?type=billing 또는 상단 탭 선택 시 /inicis/billing/prepare 호출
         - 정기결제 UI 안내 문구, /월 단위 표시, 버튼 라벨 분기
         - 이니시스 form 파라미터 분기:
           단건: gopaymethod=Card,    acceptmethod=CARDONLY:CARDPOINT:centerCd(Y)
           정기: gopaymethod=(빈값),  acceptmethod=centerCd(Y):BILLAUTH(Card)

v3.2.0 (2026-04-12)
  [FEAT] VBANK(가상계좌) 결제 지원 — 연결 서비스 전용
         - POST /payments/vbank/prepare   : 가상계좌 발급
         - POST /payments/vbank/noti      : 입금 확인 웹훅
         - GET  /payments/{id}/vbank-status : 입금 현황 조회
         - /inicis/return VBANK 분기 처리 추가
         - matching_contracts.paid_confirmed_at / 상태 자동 업데이트
         - matching_requests IN_PROGRESS 자동 전이

v3.1.0 (2026-04-12)
  [FEAT] service_status 추가 — PAID / ACTIVE / ENDED
  [FEAT] list_payments → v_payments_list 뷰 사용

v3.0.0 (2026-04-12)
  [FEAT] user_id 필수값, product_type 필수값, expired_at(SaaS), pg_method
"""
from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from db.supabase_client import get_supabase
from schemas.payment import (
    BillingCancelBody,
    BillingChargeBody,
    BillingPrepareBody,
    BillingReturnBody,
    DiagnosisVbankPrepareBody,
    PrepareBody,
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
    run_billing_cancel,
    run_billing_charge,
    run_billing_prepare,
    run_billing_return,
    run_inicis_prepare,
)
from services.payment_helpers import FRONT_RETURN_URL, load_template, now_iso as _now_iso

log = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["결제"])


# HTML: templates/payment/*.html — services.payment_helpers.load_template

# ── 라우터 ────────────────────────────────────────────────────────────

@router.get("/pricing", response_class=HTMLResponse, include_in_schema=True)
def payment_pricing_page():
    return HTMLResponse(content=load_template("pricing.html"), status_code=200)


@router.get("/result", response_class=HTMLResponse, include_in_schema=True)
def payment_result_page():
    return HTMLResponse(content=load_template("result.html"), status_code=200)


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

        if pg_method == "Vbank" or pg_method == "VBANK":
            out = process_vbank_issued(
                payment_id,
                order_id,
                auth_result,
                goodname=goodname,
                price=price,
            )
            qs = urllib.parse.urlencode(out["qs_params"])
            return RedirectResponse(f"{FRONT_RETURN_URL}?{qs}", status_code=302)

        out = process_card_success(
            payment,
            auth_result,
            pg_method,
            order_id=order_id,
            goodname=goodname,
            price=price,
        )
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

    payment       = pay_res.data[0]
    payment_id    = payment["id"]
    contract_id   = payment.get("contract_id")
    product_type  = payment.get("product_type", "")
    period_months = payment.get("period_months")

    if payment["status_code"] == "SUCCESS" or not auth_url:
        return "OK"

    try:
        auth_result = call_pay_auth(auth_token, auth_url, sign_key)
    except Exception:
        return "OK"

    if auth_result.get("resultCode") == "0000":
        pg_method = auth_result.get("payMethod", paymethod) or paymethod
        process_card_success(
            payment,
            auth_result,
            pg_method,
            order_id="",
            goodname="",
            price="",
            with_redirect_qs=False,
        )
    return "OK"


# ════════════════════════════════════════════════════════════════════════
# VBANK (가상계좌) 결제 — 연결 서비스 전용  (v3.2.0)
# ════════════════════════════════════════════════════════════════════════

@router.post("/vbank/prepare")
def vbank_prepare(body: VbankPrepareBody):
    """
    연결 서비스 가상계좌 발급
    POST /payments/vbank/prepare

    이니시스 INIStdPay gopaymethod="Vbank"
    발급 즉시 가상계좌번호를 반환 → 고객에게 입금 안내.

    ⚠️ 이니시스 카드심사 완료 후 실제 가동 (현재는 구조 완성)
    """
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

    # 세금계산서 요청 정보는 diagnosis_purchases에 별도 기록 (best-effort)
    if body.invoice_requested and (body.invoice_biz_no or body.invoice_email):
        try:
            supabase = get_supabase()
            payment_id = (result.get("data") or {}).get("payment_id")
            if payment_id:
                supabase.table("diagnosis_purchases").insert(
                    {
                        "payment_ref": payment_id,
                        "invoice_requested": True,
                        "invoice_biz_no": body.invoice_biz_no,
                        "invoice_email": body.invoice_email,
                        "created_at": _now_iso(),
                    }
                ).execute()
        except Exception as e:
            log.warning("[diagnosis vbank] invoice save failed: %s", e)

    return result


@router.post("/vbank/noti", include_in_schema=True)
async def vbank_noti(request: Request):
    """
    이니시스 VBANK 입금 확인 노티 (웹훅)
    POST /payments/vbank/noti

    고객 입금 → 이니시스 → 이 URL로 POST.
    처리 순서:
      1. payments → SUCCESS 업데이트
      2. matching_contracts → paid_confirmed_at / ACTIVE
      3. matching_requests → IN_PROGRESS 자동 전이
      4. 신청자 알림 발송

    이니시스 설정에 등록 필요:
      https://api.taieng.co.kr/payments/vbank/noti
    """
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


# 구독 이용 안내 HTML: templates/payment/billing_terms.html

@router.get("/billing/terms", response_class=HTMLResponse, include_in_schema=True)
def payment_billing_terms_page():
    """구독 이용 안내 페이지 — 이니시스 정기결제 심사용 공개 페이지"""
    return HTMLResponse(content=load_template("billing_terms.html"), status_code=200)


@router.post("/inicis/billing/prepare")
def billing_prepare(body: BillingPrepareBody):
    try:
        return run_billing_prepare(body)
    except PaymentPrepareError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e


@router.post("/inicis/billing/return")
def billing_return(body: BillingReturnBody):
    try:
        return run_billing_return(body)
    except PaymentPrepareError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e


@router.post("/inicis/billing/charge")
def billing_charge(body: BillingChargeBody):
    try:
        return run_billing_charge(body)
    except PaymentPrepareError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e


@router.post("/subscriptions/{subscription_id}/cancel")
def cancel_subscription(subscription_id: str, body: BillingCancelBody):
    try:
        return run_billing_cancel(subscription_id, body.reason or "사용자 요청", body.cancelled_by)
    except PaymentPrepareError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e
