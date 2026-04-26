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
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from db.supabase_client import get_supabase
from schemas.payment import (
    CancelBody,
    DiagnosisVbankPrepareBody,
    ManualConfirmBody,
    PrepareBody,
    VbankPrepareBody,
)
from services.payment_svc import (
    PaymentPrepareError,
    call_pay_auth,
    load_sign_key,
    run_inicis_prepare,
)
from services.payment_helpers import (
    SAAS_PRODUCT_TYPES,
    INICIS_MID,
    DEFAULT_CLOSE_URL,
    DEFAULT_RETURN_URL,
    FRONT_RETURN_URL,
    calc_expired_at as _calc_expired_at,
    load_template,
    make_order_id as _make_order_id,
    now_iso as _now_iso,
    sha256 as _sha256,
    service_status_after_card_pay,
    split_supply_vat,
    ts_ms as _ts_ms,
)

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

    payment       = pay_res.data[0]
    payment_id    = payment["id"]
    contract_id   = payment.get("contract_id")
    product_type  = payment.get("product_type", "")
    period_months = payment.get("period_months")

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
        supabase.table("payments").update({
            "status_code": "FAILED", "fail_reason": f"승인 API 실패: {e}", "updated_at": _now_iso(),
        }).eq("id", payment_id).execute()
        return RedirectResponse(f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=승인API오류&oid={order_id}", status_code=302)

    is_ok = str(auth_result.get("resultCode", "")) == "0000"

    if is_ok:
        now       = _now_iso()
        apply_num = auth_result.get("applNum", "")
        pg_method = auth_result.get("payMethod", paymethod) or paymethod

        # ── VBANK: 가상계좌 발급 완료 (아직 입금 전) ─────────────────
        if pg_method == "Vbank" or pg_method == "VBANK":
            vbank_number = auth_result.get("vbankNum", "")
            vbank_bank   = auth_result.get("vbankBankName", "")
            vbank_expire = auth_result.get("vbankExpireDate", "")

            supabase.table("payments").update({
                "status_code":     "PENDING",    # 입금 전이므로 PENDING 유지
                "pg_method":       "VBANK",
                "vbank_number":    vbank_number,
                "vbank_bank":      vbank_bank,
                "inicis_order_id": order_id,
                "inicis_raw":      auth_result,
                "memo":            f"가상계좌 발급완료 | {vbank_bank} {vbank_number}",
                "updated_at":      now,
            }).eq("id", payment_id).execute()

            qs = urllib.parse.urlencode({
                "resultCode":    "00",
                "oid":           order_id,
                "goodname":      goodname,
                "price":         price,
                "paymethod":     "VBANK",
                "vbank_number":  vbank_number,
                "vbank_bank":    vbank_bank,
                "vbank_expire":  vbank_expire,
                "payment_id":    payment_id,
            })
            return RedirectResponse(f"{FRONT_RETURN_URL}?{qs}", status_code=302)

        # ── 카드/기타: 기존 로직 ───────────────────────────────────────

        expired_at = None
        if product_type in SAAS_PRODUCT_TYPES and period_months:
            expired_at = _calc_expired_at(now, period_months)

        service_status = service_status_after_card_pay(contract_id)

        update_row: dict = {
            "status_code":      "SUCCESS",
            "service_status":   service_status,
            "pg_method":        pg_method,
            "inicis_tid":       auth_result.get("tid", ""),
            "inicis_auth_code": apply_num,
            "inicis_card_name": auth_result.get("P_FN_NM") or auth_result.get("CARD_Num", ""),
            "inicis_raw":       auth_result,
            "paid_at":          now,
            "updated_at":       now,
        }
        if expired_at:
            update_row["expired_at"] = expired_at

        supabase.table("payments").update(update_row).eq("id", payment_id).execute()

        if contract_id:
            supabase.table("contracts").update({"is_active": True, "updated_at": now}).eq("id", contract_id).execute()

        qs = urllib.parse.urlencode({
            "resultCode":  "00",
            "oid":         order_id,
            "goodname":    auth_result.get("goodName", goodname),
            "price":       auth_result.get("TotPrice", price),
            "paymethod":   pg_method,
            "applnum":     apply_num,
            "payment_id":  payment_id,
            "expired_at":  expired_at or "",
        })
        return RedirectResponse(f"{FRONT_RETURN_URL}?{qs}", status_code=302)
    else:
        fail_msg = auth_result.get("resultMsg", "승인 실패")
        supabase.table("payments").update({
            "status_code": "FAILED", "fail_reason": fail_msg,
            "inicis_raw": auth_result, "updated_at": _now_iso(),
        }).eq("id", payment_id).execute()
        return RedirectResponse(
            f"{FRONT_RETURN_URL}?resultCode=FAIL&msg={urllib.parse.quote(fail_msg)}&oid={order_id}",
            status_code=302
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
        now = _now_iso()
        pg_method  = auth_result.get("payMethod", paymethod) or paymethod
        expired_at = None
        if product_type in SAAS_PRODUCT_TYPES and period_months:
            expired_at = _calc_expired_at(now, period_months)
        service_status = service_status_after_card_pay(contract_id)

        update_row: dict = {
            "status_code": "SUCCESS",
            "service_status": service_status,
            "pg_method": pg_method,
            "inicis_tid": auth_result.get("tid", ""),
            "inicis_auth_code": auth_result.get("applNum", ""),
            "inicis_card_name": auth_result.get("P_FN_NM", ""),
            "inicis_raw": auth_result,
            "paid_at": now,
            "updated_at": now,
        }
        if expired_at:
            update_row["expired_at"] = expired_at

        supabase.table("payments").update(update_row).eq("id", payment_id).execute()
        if contract_id:
            supabase.table("contracts").update({"is_active": True, "updated_at": now}).eq("id", contract_id).execute()
    return "OK"


@router.get("")
def list_payments(
    user_id:        Optional[str] = Query(None),
    company_id:     Optional[str] = Query(None),
    status_code:    Optional[str] = Query(None),
    service_status: Optional[str] = Query(None),
    product_type:   Optional[str] = Query(None),
    plan_code:      Optional[str] = Query(None),
    pg_method:      Optional[str] = Query(None),
    keyword:        Optional[str] = Query(None, description="회원명 또는 회사명 검색"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """
    결제 목록 조회 — v_payments_list 뷰 사용
    (user_name, company_name, user_email 포함)
    """
    supabase = get_supabase()
    q = supabase.table("v_payments_list").select("*", count="exact")

    if user_id:        q = q.eq("user_id",        user_id)
    if company_id:     q = q.eq("company_id",      company_id)
    if status_code:    q = q.eq("status_code",     status_code)
    if service_status: q = q.eq("service_status",  service_status)
    if product_type:   q = q.eq("product_type",    product_type)
    if plan_code:      q = q.eq("plan_code",        plan_code)
    if pg_method:      q = q.eq("pg_method",        pg_method)

    # keyword: user_name OR company_name (Supabase는 OR 필터를 지원)
    if keyword:
        q = q.or_(f"user_name.ilike.%{keyword}%,company_name.ilike.%{keyword}%")

    offset = (page - 1) * size
    res    = q.order("created_at", desc=True).range(offset, offset + size - 1).execute()
    total  = res.count or 0
    return {
        "status": "success",
        "data": {
            "items":       res.data or [],
            "total":       total,
            "page":        page,
            "size":        size,
            "total_pages": (total + size - 1) // size if total else 0,
        },
    }


@router.get("/expiring")
def list_expiring_payments(
    days: int = Query(30, ge=1, le=90),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """SaaS 만료 임박 목록 — 어드민 관제용"""
    supabase = get_supabase()
    now      = datetime.now(timezone.utc)
    deadline = (now + timedelta(days=days)).isoformat()
    q = supabase.table("v_payments_list").select(
        "id, user_id, user_name, company_name, product_type, plan_code, "
        "period_months, total_amount, status_code, service_status, paid_at, expired_at",
        count="exact"
    ).eq("status_code", "SUCCESS").lte("expired_at", deadline).gte("expired_at", now.isoformat())
    offset = (page - 1) * size
    res    = q.order("expired_at", desc=False).range(offset, offset + size - 1).execute()
    total  = res.count or 0
    return {
        "status": "success",
        "data": {
            "items":          res.data or [],
            "total":          total,
            "page":           page,
            "size":           size,
            "days_threshold": days,
        },
    }


@router.post("/manual/confirm")
def manual_confirm(body: ManualConfirmBody):
    """수동 활성화 — 계좌이체 입금 확인 또는 webhook 실패 복구"""
    supabase = get_supabase()
    now = _now_iso()
    pay_res = supabase.table("payments").select(
        "id, status_code, product_type, period_months"
    ).eq("id", body.payment_id).limit(1).execute()
    if not pay_res.data:
        raise HTTPException(status_code=404, detail="결제 레코드를 찾을 수 없습니다.")
    payment = pay_res.data[0]
    if payment["status_code"] == "SUCCESS":
        raise HTTPException(status_code=409, detail="이미 성공 처리된 결제입니다.")

    update_row: dict = {
        "status_code":    "SUCCESS",
        "service_status": "ACTIVE",   # 수동 활성화 → 서비스중
        "paid_at":        now,
        "memo":           "수동 활성화 처리",
        "updated_at":     now,
    }
    product_type  = payment.get("product_type", "")
    period_months = payment.get("period_months")
    if product_type in SAAS_PRODUCT_TYPES and period_months:
        update_row["expired_at"] = _calc_expired_at(now, period_months)

    supabase.table("payments").update(update_row).eq("id", body.payment_id).execute()
    supabase.table("contracts").update({"is_active": True, "updated_at": now}).eq("id", body.contract_id).execute()

    return {
        "status":  "success",
        "message": "수동 활성화 완료",
        "data":    {"payment_id": body.payment_id, "contract_id": body.contract_id},
    }


@router.post("/{payment_id}/cancel")
def cancel_payment(payment_id: str, body: CancelBody):
    """결제 취소 — 이니시스 실결제 취소는 별도 PG 취소 API 연동 필요"""
    supabase = get_supabase()
    now = _now_iso()
    pay_res = supabase.table("payments").select(
        "id, status_code, contract_id"
    ).eq("id", payment_id).limit(1).execute()
    if not pay_res.data:
        raise HTTPException(status_code=404, detail="결제 레코드를 찾을 수 없습니다.")
    payment = pay_res.data[0]
    if payment["status_code"] == "CANCELLED":
        raise HTTPException(status_code=409, detail="이미 취소된 결제입니다.")

    supabase.table("payments").update({
        "status_code":    "CANCELLED",
        "service_status": "ENDED",    # 취소 → 계약종결
        "cancel_reason":  body.reason,
        "cancelled_at":   now,
        "expired_at":     None,       # 만료일 초기화
        "updated_at":     now,
    }).eq("id", payment_id).execute()

    contract_id = payment.get("contract_id")
    if contract_id:
        supabase.table("contracts").update({"is_active": False, "updated_at": now}).eq("id", contract_id).execute()

    return {
        "status":  "success",
        "message": "취소 처리되었습니다.",
        "data":    {"payment_id": payment_id, "status_code": "CANCELLED"},
    }


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
    supabase  = get_supabase()
    sign_key  = load_sign_key()
    order_id  = _make_order_id()
    timestamp = _ts_ms()
    price_str = str(body.amount)
    mKey      = _sha256(sign_key)

    sig_data   = f"oid={order_id}&price={price_str}&timestamp={timestamp}"
    veri_data  = f"oid={order_id}&price={price_str}&signKey={sign_key}&timestamp={timestamp}"
    signature    = _sha256(sig_data)
    verification = _sha256(veri_data)

    supply_amount, vat_amount = split_supply_vat(body.amount)
    now           = _now_iso()

    vbank_expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=body.vbank_expire_min)
    ).isoformat()

    if body.product_type != "DIAGNOSIS" and not body.matching_contract_id:
        raise HTTPException(status_code=400, detail="matching_contract_id는 연결 서비스 결제 시 필수입니다.")
    if body.product_type == "DIAGNOSIS" and not (body.user_id or body.auth_token or body.public_token):
        raise HTTPException(status_code=400, detail="DIAGNOSIS는 user_id 또는 auth_token/public_token 중 하나가 필요합니다.")

    row: dict = {
        "user_id":              body.user_id,
        "product_type":         body.product_type,
        "payment_method":       "INICIS",
        "pg_method":            "VBANK",
        "payment_type":         "VBANK",
        "supply_amount":        supply_amount,
        "vat_amount":           vat_amount,
        "total_amount":         body.amount,
        "inicis_order_id":      order_id,
        "status_code":          "PENDING",       # 입금 전
        "service_status":       "PAID",
        "vbank_expires_at":     vbank_expires_at,
        "created_at":           now,
        "updated_at":           now,
    }
    if body.matching_contract_id:
        row["matching_contract_id"] = body.matching_contract_id
    if body.company_id:
        row["company_id"] = body.company_id
    if body.auth_token or body.public_token:
        row["memo"] = (
            f"diag_auth_token={body.auth_token or ''} "
            f"diag_public_token={body.public_token or ''}"
        ).strip()

    res = supabase.table("payments").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="결제 레코드 생성 실패")

    payment_id = res.data[0]["id"]

    # 연결 서비스인 경우 matching_contracts에 payment_id 연결
    if body.matching_contract_id:
        supabase.table("matching_contracts").update({
            "payment_id": payment_id,
            "updated_at": now,
        }).eq("id", body.matching_contract_id).execute()

    log.info(f"[VBANK PREPARE] oid={order_id} product={body.product_type} contract={body.matching_contract_id}")

    return {
        "status": "success",
        "data": {
            "payment_id":    payment_id,
            "mid":           INICIS_MID,
            "mKey":          mKey,
            "oid":           order_id,
            "price":         price_str,
            "goodname":      body.goodname,
            "buyername":     body.buyername or "고객",
            "buyertel":      body.buyertel  or "00000000000",
            "buyeremail":    body.buyeremail or "",
            "timestamp":     timestamp,
            "verification":  verification,
            "signature":     signature,
            "use_chkfake":   "Y",
            "returnUrl":     DEFAULT_RETURN_URL,
            "closeUrl":      DEFAULT_CLOSE_URL,
            "charset":       "UTF-8",
            "gopaymethod":   "Vbank",
            "vbankexpire":   body.vbank_expire_min,
        },
    }


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

    order_id    = data.get("orderNumber") or data.get("oid", "")
    result_code = data.get("resultCode", "")
    depositor   = data.get("vbankInputName", "")   # 실제 입금자명

    log.info(f"[VBANK NOTI] oid={order_id} resultCode={result_code}")

    supabase = get_supabase()

    pay_res = (
        supabase.table("payments")
        .select("id, status_code, user_id, company_id, total_amount, product_type, matching_contract_id")
        .eq("inicis_order_id", order_id)
        .limit(1)
        .execute()
    )
    if not pay_res.data:
        log.warning(f"[VBANK NOTI] 주문번호 미확인: {order_id}")
        return "OK"

    payment              = pay_res.data[0]
    payment_id           = payment["id"]
    matching_contract_id = payment.get("matching_contract_id")

    # 이미 처리된 경우 스킵 (멱등성)
    if payment["status_code"] == "SUCCESS":
        return "OK"

    # 입금 취소/실패
    if result_code not in ("", "00", "0000"):
        log.info(f"[VBANK NOTI] 입금 취소: resultCode={result_code}")
        supabase.table("payments").update({
            "status_code": "FAILED",
            "fail_reason": f"VBANK 입금 취소 (resultCode={result_code})",
            "updated_at":  _now_iso(),
        }).eq("id", payment_id).execute()
        return "OK"

    # ── 입금 성공 처리 ──────────────────────────────────────────────
    now = _now_iso()

    # 1. payments → SUCCESS
    supabase.table("payments").update({
        "status_code":        "SUCCESS",
        "service_status":     "ACTIVE",
        "vbank_depositor":    depositor,
        "vbank_confirmed_at": now,
        "paid_at":            now,
        "inicis_raw":         data,
        "updated_at":         now,
    }).eq("id", payment_id).execute()
    log.info(f"[VBANK NOTI] 입금 확인 — payment_id={payment_id}")

    # 2. matching_contracts → paid_confirmed_at / ACTIVE
    if matching_contract_id:
        supabase.table("matching_contracts").update({
            "paid_confirmed_at": now,
            "status":            "ACTIVE",
            "updated_at":        now,
        }).eq("id", matching_contract_id).execute()

        # 3. matching_requests → CONTRACTED → IN_PROGRESS 자동 전이
        contract_res = (
            supabase.table("matching_contracts")
            .select("request_id")
            .eq("id", matching_contract_id)
            .limit(1)
            .execute()
        )
        if contract_res.data:
            request_id = contract_res.data[0].get("request_id")
            if request_id:
                req_res = (
                    supabase.table("matching_requests")
                    .select("id, status, status_history")
                    .eq("id", request_id)
                    .limit(1)
                    .execute()
                )
                if req_res.data and req_res.data[0]["status"] == "CONTRACTED":
                    history = req_res.data[0].get("status_history") or []
                    history.append({
                        "status": "IN_PROGRESS",
                        "at":     now,
                        "by":     "system",
                        "memo":   "가상계좌 입금 확인 → 서비스 시작",
                    })
                    supabase.table("matching_requests").update({
                        "status":         "IN_PROGRESS",
                        "status_history": history,
                        "updated_at":     now,
                    }).eq("id", request_id).execute()
                    log.info(f"[VBANK NOTI] 매칭 → IN_PROGRESS request_id={request_id}")

    # 4. 신청자 알림 발송
    if payment.get("user_id"):
        supabase.table("notifications").insert({
            "user_id":    payment["user_id"],
            "title":      "계약금 입금 확인",
            "body":       f"계약금 {int(payment['total_amount']):,}원 입금이 확인되었습니다. 서비스가 시작됩니다.",
            "type":       "PAYMENT",
            "is_read":    False,
            "created_at": now,
        }).execute()

    return "OK"


@router.get("/{payment_id}/vbank-status")
def get_vbank_status(payment_id: str):
    """
    VBANK 입금 대기 현황 조회
    GET /payments/{payment_id}/vbank-status

    프론트 결제 완료 화면에서 폴링 또는 현황 확인용.
    """
    supabase = get_supabase()
    res = (
        supabase.table("payments")
        .select(
            "id, status_code, total_amount, "
            "vbank_number, vbank_bank, vbank_expires_at, "
            "vbank_depositor, vbank_confirmed_at, paid_at"
        )
        .eq("id", payment_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="결제 정보를 찾을 수 없습니다.")

    p = res.data[0]
    return {
        "status": "success",
        "data": {
            "payment_id":       payment_id,
            "status_code":      p["status_code"],
            "is_paid":          p["status_code"] == "SUCCESS",
            "total_amount":     p["total_amount"],
            "vbank_number":     p.get("vbank_number"),
            "vbank_bank":       p.get("vbank_bank"),
            "vbank_expires_at": p.get("vbank_expires_at"),
            "vbank_depositor":  p.get("vbank_depositor"),
            "confirmed_at":     p.get("vbank_confirmed_at"),
        },
    }


# 구독 이용 안내 HTML: templates/payment/billing_terms.html

@router.get("/billing/terms", response_class=HTMLResponse, include_in_schema=True)
def payment_billing_terms_page():
    """구독 이용 안내 페이지 — 이니시스 정기결제 심사용 공개 페이지"""
    return HTMLResponse(content=load_template("billing_terms.html"), status_code=200)
