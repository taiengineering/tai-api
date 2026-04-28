"""
이니시스 빌링(정기결제) 라우터 — v1.0.0 (2026-04-23)

payments.py(단건결제)와는 별도 파일로 분리. 동일한 prefix="/payments"를
사용하므로 FastAPI에서 include_router 하면 하나의 태그로 합쳐진다.

이니시스 매뉴얼 기준 구현:
  - 빌링키 발급(STEP3)      : SHA256 + SignKey   (단건결제와 동일)
  - 빌링승인(Billing API)   : SHA512 + INIAPIKey (단건과 다름!)
  - timestamp 포맷          : STEP3는 밀리초, 빌링승인은 YYYYMMDDhhmmss

4 엔드포인트:
  POST /payments/inicis/billing/prepare    — 빌링키 발급 준비
  POST /payments/inicis/billing/return     — 이니시스 콜백 (내부 첫 결제 포함)
  POST /payments/inicis/billing/charge     — 수동/cron 정기 청구
  POST /payments/subscriptions/{id}/cancel — 구독 해지

관련 DB:
  subscriptions  : 구독 상태 관리 (PENDING → ACTIVE → CANCELLED/PAUSED/FAILED)
  billing_keys   : 이니시스 빌링키 저장 (ACTIVE / REVOKED)
  payments       : 회차별 결제 기록 (subscription_id, charge_cycle로 FK)

관련 환경변수 (Railway):
  INICIS_BILLING_MID          — 정기결제용 상점 ID
  INICIS_BILLING_SIGN_KEY     — STEP3(SHA256)용
  INICIS_BILLING_INIAPI_KEY   — Billing API(SHA512)용
  INICIS_CLIENT_IP            — 이니시스 API 호출 시 clientIp 파라미터
"""
from __future__ import annotations

import hashlib
import logging
import os
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

import requests as _requests
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, field_validator, model_validator

from db.direct_sql import (
    find_subscription_by_oid,
    insert_subscription,
    update_subscription_by_oid,
)
from db.supabase_client import get_supabase

from services.payment_helpers import (
    DEFAULT_CLOSE_URL,
    FRONT_RETURN_URL,
    SAAS_PRODUCT_TYPES,
    calc_expired_at as _calc_expired_at,
    now_iso as _now_iso,
    sha256 as _sha256,
    ts_ms as _ts_ms,
)
from services.payment_svc import call_pay_auth as _call_pay_auth

log = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["결제"])


# ── 환경변수 로더 ──────────────────────────────────────────────────────
INICIS_BILLING_API_URL     = "https://iniapi.inicis.com/api/v1/billing"
DEFAULT_BILLING_RETURN_URL = "https://api.taieng.co.kr/payments/inicis/billing/return"


def _require_env(name: str) -> str:
    """
    정기결제 관련 환경변수는 폴백 없이 엄격하게 요구.
    미설정 시 503 — 운영자가 Railway에 이니시스 정기결제 키를 등록해야 함을
    명확하게 드러내기 위함(잘못된 단건 MID 폴백으로 인한 혼란 방지).
    """
    v = (os.getenv(name) or "").strip()
    if not v:
        raise HTTPException(
            status_code=503,
            detail=(
                f"정기결제 환경변수 미설정: {name}. "
                f"이니시스 정기결제 심사 완료 후 Railway에 등록 필요."
            ),
        )
    return v


def _load_billing_mid() -> str:
    """정기결제용 MID — 단건 MID로 폴백하지 않음."""
    return _require_env("INICIS_BILLING_MID")


def _load_billing_sign_key() -> str:
    """빌링키 발급(STEP3)용 SignKey — SHA256 대상."""
    return _require_env("INICIS_BILLING_SIGN_KEY")


def _load_billing_iniapi_key() -> str:
    """빌링승인용 INIAPIKey — SHA512 대상."""
    return _require_env("INICIS_BILLING_INIAPI_KEY")


def _load_client_ip() -> str:
    """가맹점 서버 IP — 이니시스 방화벽 등록된 고정IP."""
    return _require_env("INICIS_CLIENT_IP")




# ── 유틸 ──────────────────────────────────────────────────────────────

def _sha512(data: str) -> str:
    return hashlib.sha512(data.encode("utf-8")).hexdigest()


def _make_billing_oid() -> str:
    """빌링키 발급 주문번호 — TAI-BIL-YYYYMMDDhhmmss-xxxxxx"""
    return f"TAI-BIL-{datetime.now():%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"


def _make_charge_moid(subscription_id: str, cycle: int) -> str:
    """정기청구 주문번호 — TAI-SUB-<sub_id 첫8자>-<cycle>"""
    sid = (subscription_id or "").replace("-", "")[:8].upper()
    return f"TAI-SUB-{sid}-{int(cycle)}"


def _ts_yyyymmddhhmmss() -> str:
    """빌링승인 API용 timestamp — YYYYMMDDhhmmss (STEP3의 밀리초와 다름)"""
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _call_billing_charge_api(
    *,
    mid: str,
    iniapi_key: str,
    client_ip: str,
    moid: str,
    bill_key: str,
    price: int,
    goodname: str,
    buyer_name: str,
    buyer_email: str,
    buyer_tel: str,
    merchant_url: str = "https://taieng.co.kr",
) -> Dict[str, Any]:
    """
    이니시스 빌링승인 API 호출 (SHA512 + INIAPIKey).
    이니시스 매뉴얼 §빌링결제>빌링승인 기준.

    hashData = SHA512(INIAPIKey + type + paymethod + timestamp
                      + clientIp + mid + moid + price + billKey)
    반환: 이니시스 JSON (resultCode / resultMsg / tid / payAuthCode 등)
    """
    timestamp = _ts_yyyymmddhhmmss()
    paymethod = "Card"
    req_type  = "Billing"
    price_str = str(int(price))

    hash_src  = (
        iniapi_key + req_type + paymethod + timestamp
        + client_ip + mid + moid + price_str + bill_key
    )
    hash_data = _sha512(hash_src)

    form: Dict[str, str] = {
        "type":              req_type,
        "paymethod":         paymethod,
        "timestamp":         timestamp,
        "clientIp":          client_ip,
        "mid":               mid,
        "url":               merchant_url,
        "moid":              moid,
        "goodName":          goodname[:80],
        "buyerName":         (buyer_name or "고객")[:80],
        "buyerEmail":        (buyer_email or "")[:60],
        "buyerTel":          (buyer_tel or "")[:40],
        "price":             price_str,
        "billKey":           bill_key,
        "authentification":  "00",
        "hashData":          hash_data,
    }

    log.info(f"[BILLING CHARGE] moid={moid} mid={mid} price={price_str}")
    try:
        resp = _requests.post(
            INICIS_BILLING_API_URL,
            data=form,
            timeout=30,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
        )
    except Exception as e:
        log.error(f"[BILLING CHARGE] 네트워크 오류: {e}")
        raise HTTPException(status_code=502, detail=f"이니시스 빌링 API 호출 실패: {e}")

    try:
        result = resp.json()
    except Exception:
        log.error(f"[BILLING CHARGE] 응답 파싱 실패 status={resp.status_code} body={resp.text[:500]}")
        raise HTTPException(status_code=502, detail="이니시스 빌링승인 응답 파싱 실패")

    log.info(
        f"[BILLING CHARGE] resultCode={result.get('resultCode')} "
        f"resultMsg={result.get('resultMsg')}"
    )
    return result


# ── Pydantic 모델 ──────────────────────────────────────────────────────

class BillingPrepareBody(BaseModel):
    """빌링키 발급 준비 Body"""
    user_id:      str
    product_type: str
    plan_code:    str
    plan_name:    Optional[str] = None
    goodname:     Optional[str] = None
    amount:       int
    company_id:   Optional[str] = None
    buyername:    Optional[str] = "고객"
    buyertel:     Optional[str] = "00000000000"
    buyeremail:   Optional[str] = None
    return_url:   Optional[str] = None
    close_url:    Optional[str] = None

    @field_validator("user_id")
    @classmethod
    def user_id_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("user_id는 필수값입니다. 로그인 후 결제해주세요.")
        return v.strip()

    @field_validator("product_type")
    @classmethod
    def must_be_saas(cls, v: str) -> str:
        if v not in SAAS_PRODUCT_TYPES:
            raise ValueError(f"정기결제는 SaaS 상품에만 가능합니다: {SAAS_PRODUCT_TYPES}")
        return v

    @model_validator(mode="after")
    def normalize_plan_name(self):
        if not self.plan_name and self.goodname:
            self.plan_name = self.goodname
        return self


class BillingChargeBody(BaseModel):
    """수동/cron 청구 Body"""
    subscription_id: str
    charge_cycle:    Optional[int] = None

    @field_validator("subscription_id")
    @classmethod
    def sub_id_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("subscription_id는 필수값입니다.")
        return v.strip()


class SubscriptionCancelBody(BaseModel):
    """구독 해지 Body"""
    reason:       Optional[str] = "사용자 요청"
    cancelled_by: Optional[str] = None


# ── 내부 함수 ─────────────────────────────────────────────────────────

def _charge_subscription_once(
    supabase,
    *,
    subscription: Dict[str, Any],
    billing_key_row: Dict[str, Any],
    charge_cycle: int,
    is_recurring: bool,
    buyer_name: str = "고객",
    buyer_email: str = "",
    buyer_tel: str = "",
) -> Dict[str, Any]:
    """
    한 주기 청구 실행. payments INSERT → 이니시스 호출 → 결과 반영.
    반환: {"success": bool, "payment_id": str, "result": dict}
    """
    now             = _now_iso()
    subscription_id = subscription["id"]
    user_id         = subscription["user_id"]
    company_id      = subscription.get("company_id")
    product_type    = subscription["product_type"]
    plan_code       = subscription.get("plan_code")
    plan_name       = subscription.get("plan_name", "TAI Safe")
    amount          = int(subscription["amount"])
    supply          = int(subscription["supply_amount"])
    vat             = int(subscription["vat_amount"])
    bill_key        = billing_key_row["bill_key"]
    billing_key_id  = billing_key_row["id"]
    mid             = billing_key_row.get("mid") or _load_billing_mid()

    moid = _make_charge_moid(subscription_id, charge_cycle)

    # 0) 환경변수 선로드 — 미설정 시 503. payments INSERT 전에 체크해서
    #    쓰레기 PENDING 레코드가 생기지 않도록 한다.
    iniapi_key = _load_billing_iniapi_key()
    client_ip  = _load_client_ip()

    # 1) payments PENDING INSERT (UNIQUE 제약으로 중복방지)
    payment_row: Dict[str, Any] = {
        "user_id":         user_id,
        "product_type":    product_type,
        "payment_method":  "INICIS",
        "payment_type":    "CARD",
        "pg_method":       "CardBilling",
        "supply_amount":   supply,
        "vat_amount":      vat,
        "total_amount":    amount,
        "inicis_order_id": moid,
        "status_code":     "PENDING",
        "service_status":  None,
        "subscription_id": subscription_id,
        "billing_key_id":  billing_key_id,
        "charge_cycle":    charge_cycle,
        "is_recurring":    is_recurring,
        "plan_code":       plan_code,
        "period_months":   1,
        "created_at":      now,
        "updated_at":      now,
    }
    if company_id:
        payment_row["company_id"] = company_id

    try:
        ins = supabase.table("payments").insert(payment_row).execute()
    except Exception as e:
        # UNIQUE 위반(이미 같은 subscription_id + cycle 존재) 등
        log.error(f"[BILLING] payments INSERT 실패 sub={subscription_id} cycle={charge_cycle}: {e}")
        raise HTTPException(status_code=409, detail=f"결제 레코드 생성 실패 (중복 가능): {e}")

    if not ins.data:
        raise HTTPException(status_code=500, detail="결제 레코드 생성 실패")
    payment_id = ins.data[0]["id"]

    # 2) 이니시스 빌링승인 호출 (환경변수는 위에서 선로드됨)

    try:
        result = _call_billing_charge_api(
            mid=mid,
            iniapi_key=iniapi_key,
            client_ip=client_ip,
            moid=moid,
            bill_key=bill_key,
            price=amount,
            goodname=plan_name,
            buyer_name=buyer_name,
            buyer_email=buyer_email,
            buyer_tel=buyer_tel,
        )
    except HTTPException:
        # _call_billing_charge_api 내부에서 이미 업스트림 처리
        fail_reason = "이니시스 빌링승인 호출 실패"
        supabase.table("payments").update({
            "status_code": "FAILED",
            "fail_reason": fail_reason,
            "updated_at":  _now_iso(),
        }).eq("id", payment_id).execute()
        _apply_failure_to_subscription(supabase, subscription_id, fail_reason)
        return {"success": False, "payment_id": payment_id, "result": {"error": fail_reason}}
    except Exception as e:
        log.error(f"[BILLING] charge 예외 sub={subscription_id} cycle={charge_cycle}: {e}")
        fail_reason = f"빌링승인 API 호출 실패: {e}"
        supabase.table("payments").update({
            "status_code": "FAILED",
            "fail_reason": fail_reason[:500],
            "updated_at":  _now_iso(),
        }).eq("id", payment_id).execute()
        _apply_failure_to_subscription(supabase, subscription_id, fail_reason)
        return {"success": False, "payment_id": payment_id, "result": {"error": str(e)}}

    # 3) 결과 반영
    is_ok = str(result.get("resultCode", "")) == "00"
    now2  = _now_iso()

    if is_ok:
        paid_at    = now2
        expired_at = _calc_expired_at(paid_at, 1)   # 1개월

        supabase.table("payments").update({
            "status_code":      "SUCCESS",
            "service_status":   "ACTIVE",
            "inicis_tid":       result.get("tid", ""),
            "inicis_auth_code": result.get("payAuthCode", ""),
            "inicis_raw":       result,
            "paid_at":          paid_at,
            "expired_at":       expired_at,
            "updated_at":       now2,
        }).eq("id", payment_id).execute()

        supabase.table("subscriptions").update({
            "last_billed_at":      paid_at,
            "next_billing_at":     expired_at,
            "failure_count":       0,
            "last_failure_at":     None,
            "last_failure_reason": None,
            "updated_at":          now2,
        }).eq("id", subscription_id).execute()

        return {"success": True, "payment_id": payment_id, "result": result}

    # 실패
    fail_reason = result.get("resultMsg") or f"resultCode={result.get('resultCode')}"
    supabase.table("payments").update({
        "status_code": "FAILED",
        "fail_reason": fail_reason[:500] if fail_reason else None,
        "inicis_raw":  result,
        "updated_at":  now2,
    }).eq("id", payment_id).execute()
    _apply_failure_to_subscription(supabase, subscription_id, fail_reason or "청구 실패")
    return {"success": False, "payment_id": payment_id, "result": result}


def _apply_failure_to_subscription(supabase, subscription_id: str, reason: str) -> None:
    """실패 카운트 증가 + 3회 이상 시 PAUSED."""
    now = _now_iso()
    cur = (
        supabase.table("subscriptions")
        .select("failure_count, status")
        .eq("id", subscription_id)
        .limit(1)
        .execute()
    )
    if not cur.data:
        return
    current_count = int(cur.data[0].get("failure_count") or 0)
    new_count     = current_count + 1
    upd: Dict[str, Any] = {
        "failure_count":       new_count,
        "last_failure_at":     now,
        "last_failure_reason": (reason or "")[:500] if reason else None,
        "updated_at":          now,
    }
    if new_count >= 3 and cur.data[0].get("status") == "ACTIVE":
        upd["status"] = "PAUSED"
        log.warning(f"[BILLING] subscription {subscription_id} PAUSED (failure_count={new_count})")
    supabase.table("subscriptions").update(upd).eq("id", subscription_id).execute()


def _fail_subscription_by_oid(supabase, oid: str, reason: str) -> None:
    """prepare/return 단계에서 실패한 구독을 FAILED로 마킹."""
    if not oid:
        return
    update_subscription_by_oid(oid, {
        "status":              "FAILED",
        "last_failure_at":     _now_iso(),
        "last_failure_reason": (reason or "")[:500],
        "updated_at":          _now_iso(),
    })


# ── 엔드포인트 ────────────────────────────────────────────────────────

@router.post("/inicis/billing/prepare")
def billing_prepare(body: BillingPrepareBody):
    """
    정기결제 빌링키 발급 준비 (STEP1).
    subscriptions PENDING 행을 만들고, 클라이언트에 INIStdPay 파라미터를 반환.
    """
    supabase  = get_supabase()
    mid       = _load_billing_mid()
    sign_key  = _load_billing_sign_key()
    oid       = _make_billing_oid()
    timestamp = _ts_ms()
    price_str = str(body.amount)
    mKey      = _sha256(sign_key)

    sig_data     = f"oid={oid}&price={price_str}&timestamp={timestamp}"
    veri_data    = f"oid={oid}&price={price_str}&signKey={sign_key}&timestamp={timestamp}"
    signature    = _sha256(sig_data)
    verification = _sha256(veri_data)

    supply_amount = round(body.amount / 1.1)
    vat_amount    = body.amount - supply_amount
    now           = _now_iso()

    sub_row: Dict[str, Any] = {
        "user_id":         body.user_id,
        "product_type":    body.product_type,
        "plan_code":       body.plan_code,
        "plan_name":       body.plan_name,
        "amount":          body.amount,
        "supply_amount":   supply_amount,
        "vat_amount":      vat_amount,
        "billing_cycle":   "monthly",
        "status":          "PENDING",
        "inicis_order_id": oid,
        "created_at":      now,
        "updated_at":      now,
    }
    if body.company_id:
        sub_row["company_id"] = body.company_id

    created_sub = insert_subscription(sub_row)
    if not created_sub:
        raise HTTPException(status_code=500, detail="구독 레코드 생성 실패")

    subscription_id = created_sub["id"]
    log.info(f"[BILLING PREPARE] oid={oid} subscription_id={subscription_id} user={body.user_id}")

    return {
        "status": "success",
        "data": {
            "subscription_id": subscription_id,
            "mid":             mid,
            "mKey":            mKey,
            "oid":             oid,
            "price":           price_str,
            "goodname":        body.plan_name,
            "buyername":       body.buyername or "고객",
            "buyertel":        body.buyertel  or "00000000000",
            "buyeremail":      body.buyeremail or "",
            "timestamp":       timestamp,
            "signature":       signature,
            "verification":    verification,
            "use_chkfake":     "Y",
            "returnUrl":       body.return_url or DEFAULT_BILLING_RETURN_URL,
            "closeUrl":        body.close_url  or DEFAULT_CLOSE_URL,
            "charset":         "UTF-8",
            "gopaymethod":     "",                                # 빌링은 빈값 고정
            "acceptmethod":    "centerCd(Y):BILLAUTH(Card)",      # 빌링키 발급 옵션
        },
    }


@router.post("/inicis/billing/return", include_in_schema=True)
async def billing_return(request: Request):
    """
    빌링키 발급 콜백 (STEP2 → STEP3 → BillKey 저장 → 첫 결제).
    성공 시 /payments/result 로 RedirectResponse.
    """
    try:
        form = await request.form()
        data: Dict[str, Any] = dict(form)
    except Exception:
        try:
            data = await request.json()
        except Exception:
            return RedirectResponse(
                f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=파싱실패",
                status_code=302,
            )

    result_code = data.get("resultCode", "")
    result_msg  = data.get("resultMsg", "")
    auth_token  = data.get("authToken", "")
    auth_url    = data.get("authUrl", "")
    order_id    = data.get("orderNumber") or data.get("oid", "")
    log.info(f"[BILLING RETURN] resultCode={result_code} oid={order_id}")

    supabase = get_supabase()

    if result_code and result_code != "0000":
        _fail_subscription_by_oid(supabase, order_id, result_msg or "인증 실패")
        return RedirectResponse(
            f"{FRONT_RETURN_URL}?resultCode=FAIL&msg={urllib.parse.quote(result_msg or '인증 실패')}&oid={order_id}",
            status_code=302,
        )

    # 구독 조회
    subscription = find_subscription_by_oid(order_id)
    if not subscription:
        return RedirectResponse(
            f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=구독정보없음&oid={order_id}",
            status_code=302,
        )
    subscription_id = subscription["id"]

    # 멱등: 이미 처리됨
    if subscription.get("status") == "ACTIVE":
        return RedirectResponse(
            f"{FRONT_RETURN_URL}?resultCode=00&oid={order_id}&subscription_id={subscription_id}",
            status_code=302,
        )

    if not auth_url:
        _fail_subscription_by_oid(supabase, order_id, "authUrl 없음")
        return RedirectResponse(
            f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=authUrl없음&oid={order_id}",
            status_code=302,
        )

    # STEP3: BillKey 발급 요청 (SHA256 + signKey — 빌링 MID 사용)
    sign_key = _load_billing_sign_key()
    billing_mid = _load_billing_mid()
    try:
        auth_result = _call_pay_auth(auth_token, auth_url, sign_key, mid=billing_mid)
    except Exception as e:
        _fail_subscription_by_oid(supabase, order_id, f"STEP3 호출 실패: {e}")
        return RedirectResponse(
            f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=STEP3오류&oid={order_id}",
            status_code=302,
        )

    if str(auth_result.get("resultCode", "")) != "0000":
        fail = auth_result.get("resultMsg", "빌링키 발급 실패")
        _fail_subscription_by_oid(supabase, order_id, fail)
        return RedirectResponse(
            f"{FRONT_RETURN_URL}?resultCode=FAIL&msg={urllib.parse.quote(fail)}&oid={order_id}",
            status_code=302,
        )

    # ── BillKey 저장 ───────────────────────────────────────────────
    bill_key = auth_result.get("CARD_BillKey", "")
    if not bill_key:
        _fail_subscription_by_oid(supabase, order_id, "CARD_BillKey 응답 없음")
        return RedirectResponse(
            f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=빌링키없음&oid={order_id}",
            status_code=302,
        )

    now              = _now_iso()
    mid_used         = _load_billing_mid()
    card_num_masked  = auth_result.get("CARD_Num", "")
    card_issuer_code = auth_result.get("CARD_Code", "")
    card_name        = auth_result.get("P_FN_NM") or auth_result.get("CARD_BankCode", "")

    bk_ins = supabase.table("billing_keys").insert({
        "user_id":          subscription["user_id"],
        "company_id":       subscription.get("company_id"),
        "bill_key":         bill_key,
        "mid":              mid_used,
        "inicis_tid":       auth_result.get("tid", ""),
        "card_name":        card_name,
        "card_num_masked":  card_num_masked,
        "card_issuer_code": card_issuer_code,
        "status":           "ACTIVE",
        "issued_at":        now,
        "inicis_raw":       auth_result,
        "created_at":       now,
        "updated_at":       now,
    }).execute()
    if not bk_ins.data:
        _fail_subscription_by_oid(supabase, order_id, "billing_keys 저장 실패")
        return RedirectResponse(
            f"{FRONT_RETURN_URL}?resultCode=FAIL&msg=빌링키저장실패&oid={order_id}",
            status_code=302,
        )
    billing_key_row = bk_ins.data[0]
    billing_key_id  = billing_key_row["id"]

    # ── subscription ACTIVE 전환 ───────────────────────────────────
    supabase.table("subscriptions").update({
        "billing_key_id":  billing_key_id,
        "status":          "ACTIVE",
        "started_at":      now,
        "next_billing_at": _calc_expired_at(now, 1),
        "updated_at":      now,
    }).eq("id", subscription_id).execute()

    # 업데이트 반영된 subscription 재조회
    sub_cur = (
        supabase.table("subscriptions")
        .select("*")
        .eq("id", subscription_id)
        .limit(1)
        .execute()
    )
    subscription = sub_cur.data[0] if sub_cur.data else subscription

    # ── 첫 결제 (cycle=1, is_recurring=False) ──────────────────────
    charge_res = _charge_subscription_once(
        supabase,
        subscription=subscription,
        billing_key_row=billing_key_row,
        charge_cycle=1,
        is_recurring=False,
        buyer_name=auth_result.get("buyerName", "고객"),
        buyer_email=auth_result.get("buyerEmail", ""),
        buyer_tel=auth_result.get("buyerTel", ""),
    )

    if charge_res.get("success"):
        qs = urllib.parse.urlencode({
            "resultCode":      "00",
            "oid":             order_id,
            "goodname":        subscription.get("plan_name", "TAI Safe"),
            "price":           str(int(subscription["amount"])),
            "paymethod":       "CardBilling",
            "applnum":         charge_res["result"].get("payAuthCode", ""),
            "payment_id":      charge_res["payment_id"],
            "subscription_id": subscription_id,
            "expired_at":      subscription.get("next_billing_at") or "",
        })
        return RedirectResponse(f"{FRONT_RETURN_URL}?{qs}", status_code=302)

    fail_msg = charge_res.get("result", {}).get("resultMsg", "첫 결제 실패")
    return RedirectResponse(
        f"{FRONT_RETURN_URL}?resultCode=FAIL&msg={urllib.parse.quote(str(fail_msg))}&oid={order_id}",
        status_code=302,
    )


@router.post("/inicis/billing/charge")
def billing_charge(body: BillingChargeBody):
    """
    정기청구 수동/cron 실행.
    charge_cycle 생략 시 기존 payments 건수 + 1로 자동 계산.
    """
    supabase = get_supabase()

    sub_res = (
        supabase.table("subscriptions")
        .select("*")
        .eq("id", body.subscription_id)
        .limit(1)
        .execute()
    )
    if not sub_res.data:
        raise HTTPException(status_code=404, detail="구독을 찾을 수 없습니다.")
    subscription = sub_res.data[0]

    if subscription.get("status") != "ACTIVE":
        raise HTTPException(
            status_code=409,
            detail=f"ACTIVE 상태에서만 청구 가능합니다. (현재 status={subscription.get('status')})",
        )

    billing_key_id = subscription.get("billing_key_id")
    if not billing_key_id:
        raise HTTPException(status_code=409, detail="구독에 연결된 빌링키가 없습니다.")

    bk_res = (
        supabase.table("billing_keys")
        .select("*")
        .eq("id", billing_key_id)
        .limit(1)
        .execute()
    )
    if not bk_res.data:
        raise HTTPException(status_code=404, detail="빌링키를 찾을 수 없습니다.")
    billing_key_row = bk_res.data[0]
    if billing_key_row.get("status") != "ACTIVE":
        raise HTTPException(
            status_code=409,
            detail=f"빌링키가 ACTIVE 상태가 아닙니다. (status={billing_key_row.get('status')})",
        )

    # charge_cycle 자동 계산
    cycle = body.charge_cycle
    if cycle is None:
        cnt_res = (
            supabase.table("payments")
            .select("id", count="exact")
            .eq("subscription_id", body.subscription_id)
            .execute()
        )
        cycle = (cnt_res.count or 0) + 1

    result = _charge_subscription_once(
        supabase,
        subscription=subscription,
        billing_key_row=billing_key_row,
        charge_cycle=cycle,
        is_recurring=True,
    )

    return {
        "status":   "success" if result.get("success") else "failed",
        "data": {
            "subscription_id": body.subscription_id,
            "payment_id":      result.get("payment_id"),
            "charge_cycle":    cycle,
            "inicis_result":   result.get("result"),
        },
    }


@router.post("/subscriptions/{subscription_id}/cancel")
def cancel_subscription(subscription_id: str, body: SubscriptionCancelBody):
    """
    구독 해지.
    - subscriptions.status = CANCELLED
    - billing_keys.status  = REVOKED (DB 기록)
    - 이니시스 BillKey 자체 폐기 API는 호출하지 않음 (매뉴얼상 별도 API 없음).
      다음 주기 청구를 멈추기만 하면 충분. 기존 결제분 환불은 별도 기능.
    """
    supabase = get_supabase()
    now      = _now_iso()

    sub_res = (
        supabase.table("subscriptions")
        .select("*")
        .eq("id", subscription_id)
        .limit(1)
        .execute()
    )
    if not sub_res.data:
        raise HTTPException(status_code=404, detail="구독을 찾을 수 없습니다.")
    subscription = sub_res.data[0]

    if subscription.get("status") == "CANCELLED":
        raise HTTPException(status_code=409, detail="이미 해지된 구독입니다.")

    supabase.table("subscriptions").update({
        "status":          "CANCELLED",
        "cancelled_at":    now,
        "cancel_reason":   body.reason or "사용자 요청",
        "next_billing_at": None,
        "ended_at":        now,
        "updated_at":      now,
    }).eq("id", subscription_id).execute()

    billing_key_id = subscription.get("billing_key_id")
    if billing_key_id:
        supabase.table("billing_keys").update({
            "status":        "REVOKED",
            "revoked_at":    now,
            "revoke_reason": body.reason or "사용자 요청",
            "updated_at":    now,
        }).eq("id", billing_key_id).execute()

    log.info(f"[BILLING CANCEL] subscription_id={subscription_id} reason={body.reason}")

    return {
        "status":  "success",
        "message": "구독이 해지되었습니다.",
        "data": {
            "subscription_id": subscription_id,
            "status":          "CANCELLED",
            "cancelled_at":    now,
        },
    }
