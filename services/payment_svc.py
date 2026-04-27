"""이니시스 결제 비즈니스 로직 (HTTP 제외).

v4.0.0 (2026-04-27)
  매뉴얼 기반 전면 재작성 — docs/INICIS_INTEGRATION_SPEC.md 참조
  - 단건결제: RSA 서명 제거, acceptmethod 응답 추가
  - 빌링: 3가지 키 체계 (SignKey/INILiteKey/INIAPIKey) 적용
  - 빌키발급: SHA512 + inilitepay.inicis.com 사용
  - 빌링승인: SHA512 + iniapi.inicis.com NVP 형식
  - 취소/환불: iniapi.inicis.com/api/v1/refund
  - 부분취소: iniapi.inicis.com/api/v1/refund (PartialRefund)

규칙: docs/DEV_RULES_SERVICE_LAYER.md STEP 3
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from uuid import uuid4

import requests as _requests
from dateutil.relativedelta import relativedelta

from db.supabase_client import get_supabase
from schemas.payment import PrepareBody, VbankPrepareBody
from services.payment_helpers import (
    BILLING_CHARGE_URL,
    BILLING_ISSUE_URL,
    BILLING_RETURN_URL,
    DEFAULT_CLOSE_URL,
    DEFAULT_RETURN_URL,
    INICIS_INIAPI_KEY,
    INICIS_INILITE_KEY,
    INICIS_BILLING_MID,
    INICIS_KEY_PASSWORD,
    INICIS_KEY_PATH,
    INICIS_MID,
    REFUND_URL,
    SAAS_PRODUCT_TYPES,
    calc_expired_at,
    decrypt_billkey,
    get_server_ip,
    make_order_id,
    now_iso,
    service_status_after_card_pay,
    sha256,
    sha512,
    split_supply_vat,
    ts_ms,
    ts_yyyymmddhhmmss,
)

log = logging.getLogger(__name__)


class PaymentPrepareError(Exception):
    """결제 준비 단계 비즈니스 오류 (라우터에서 HTTPException으로 변환)."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# ════════════════════════════════════════════════════════════════════════
# 단건결제 (PC 웹표준 INIStdPay)
# 매뉴얼: https://manual.inicis.com/pay/stdpay_pc.html
# ════════════════════════════════════════════════════════════════════════

def load_sign_key() -> str:
    """단건결제용 Sign Key 로드."""
    env_key = os.getenv("INICIS_SIGN_KEY", "").strip()
    if env_key:
        return env_key
    try:
        with open(os.path.join(INICIS_KEY_PATH, "keypass.enc"), "r", encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    except Exception as e:
        log.warning(f"[INICIS] keypass.enc 로드 실패: {e}")
    return INICIS_KEY_PASSWORD


def call_pay_auth(auth_token: str, auth_url: str, sign_key: str) -> Dict[str, Any]:
    """단건 STEP3 승인요청 — server-to-server POST to authUrl.

    매뉴얼 STEP3:
      signature    = SHA256("authToken={authToken}&timestamp={timestamp}")
      verification = SHA256("authToken={authToken}&signKey={signKey}&timestamp={timestamp}")
    """
    timestamp = ts_ms()
    signature = sha256(f"authToken={auth_token}&timestamp={timestamp}")
    verification = sha256(f"authToken={auth_token}&signKey={sign_key}&timestamp={timestamp}")

    params: Dict[str, str] = {
        "mid": INICIS_MID,
        "authToken": auth_token,
        "timestamp": timestamp,
        "signature": signature,
        "verification": verification,
        "charset": "UTF-8",
        "format": "JSON",
    }

    try:
        resp = _requests.post(
            auth_url,
            data=params,
            timeout=30,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        result = resp.json()
        log.info(
            f"[INICIS STEP3] resultCode={result.get('resultCode')} "
            f"resultMsg={result.get('resultMsg')}"
        )
        return result
    except Exception as e:
        log.error(f"[INICIS] 승인 API 실패: {e}")
        raise


def run_inicis_prepare(body: PrepareBody) -> dict:
    """단건 STEP1 결제 준비 — DB insert + 서명 파라미터.

    매뉴얼 STEP1:
      signature    = SHA256("oid={oid}&price={price}&timestamp={timestamp}")
      verification = SHA256("oid={oid}&price={price}&signKey={signKey}&timestamp={timestamp}")
      mKey         = SHA256(signKey)
    """
    if body.product_type in SAAS_PRODUCT_TYPES and not body.period_months:
        raise PaymentPrepareError(400, "SaaS 상품은 period_months가 필수입니다.")

    supabase = get_supabase()
    sign_key = load_sign_key()
    order_id = make_order_id()
    timestamp = ts_ms()
    price_str = str(body.amount)
    m_key = sha256(sign_key)
    signature = sha256(f"oid={order_id}&price={price_str}&timestamp={timestamp}")
    verification = sha256(f"oid={order_id}&price={price_str}&signKey={sign_key}&timestamp={timestamp}")

    log.info(f"[INICIS STEP1] oid={order_id} user={body.user_id} product={body.product_type}")

    supply_amount, vat_amount = split_supply_vat(body.amount)
    now = now_iso()

    row: dict = {
        "user_id": body.user_id,
        "product_type": body.product_type,
        "payment_method": "INICIS",
        "payment_type": body.payment_type or "CARD",
        "supply_amount": supply_amount,
        "vat_amount": vat_amount,
        "total_amount": body.amount,
        "inicis_order_id": order_id,
        "status_code": "PENDING",
        "service_status": None,
        "created_at": now,
        "updated_at": now,
    }
    if body.company_id:
        row["company_id"] = body.company_id
    if body.contract_id:
        row["contract_id"] = body.contract_id
    if body.quote_id:
        row["quote_id"] = body.quote_id
    if body.plan_code:
        row["plan_code"] = body.plan_code
    if body.period_months:
        row["period_months"] = body.period_months

    res = supabase.table("payments").insert(row).execute()
    if not res.data:
        raise PaymentPrepareError(500, "결제 레코드 생성 실패")

    return {
        "status": "success",
        "data": {
            "payment_id": res.data[0]["id"],
            "mid": INICIS_MID,
            "mKey": m_key,
            "oid": order_id,
            "price": price_str,
            "goodname": body.goodname,
            "buyername": body.buyername or "고객",
            "buyertel": body.buyertel or "00000000000",
            "buyeremail": body.buyeremail or "",
            "timestamp": timestamp,
            "signature": signature,
            "verification": verification,
            "use_chkfake": "Y",
            "returnUrl": body.return_url or DEFAULT_RETURN_URL,
            "closeUrl": body.close_url or DEFAULT_CLOSE_URL,
            "charset": "UTF-8",
            "gopaymethod": "Card",
            "acceptmethod": "centerCd(Y)",
        },
    }


def process_auth_failure(payment_id: str, fail_msg: str, auth_result: dict) -> None:
    """승인 실패 또는 승인 API 오류 — payments FAILED 업데이트."""
    supabase = get_supabase()
    row: Dict[str, Any] = {
        "status_code": "FAILED",
        "fail_reason": fail_msg,
        "updated_at": now_iso(),
    }
    if auth_result:
        row["inicis_raw"] = auth_result
    supabase.table("payments").update(row).eq("id", payment_id).execute()


def process_vbank_issued(
    payment_id: str,
    order_id: str,
    auth_result: dict,
    *,
    goodname: str,
    price: str,
) -> dict[str, Any]:
    """가상계좌 발급 완료(입금 전) — DB UPDATE 후 프론트 리다이렉트용 쿼리."""
    supabase = get_supabase()
    now = now_iso()
    vbank_number = auth_result.get("vbankNum", "")
    vbank_bank = auth_result.get("vbankBankName", "")
    vbank_expire = auth_result.get("vbankExpireDate", "")

    supabase.table("payments").update(
        {
            "status_code": "PENDING",
            "pg_method": "VBANK",
            "vbank_number": vbank_number,
            "vbank_bank": vbank_bank,
            "inicis_order_id": order_id,
            "inicis_raw": auth_result,
            "memo": f"가상계좌 발급완료 | {vbank_bank} {vbank_number}",
            "updated_at": now,
        }
    ).eq("id", payment_id).execute()

    return {
        "qs_params": {
            "resultCode": "00",
            "oid": order_id,
            "goodname": goodname,
            "price": price,
            "paymethod": "VBANK",
            "vbank_number": vbank_number,
            "vbank_bank": vbank_bank,
            "vbank_expire": vbank_expire,
            "payment_id": payment_id,
        }
    }


def process_card_success(
    payment: dict,
    auth_result: dict,
    paymethod: str,
    *,
    order_id: str,
    goodname: str,
    price: str,
    with_redirect_qs: bool = True,
) -> Optional[dict[str, Any]]:
    """카드 등 승인 성공 — payments UPDATE + 계약 활성화."""
    supabase = get_supabase()
    now = now_iso()
    payment_id = payment["id"]
    contract_id = payment.get("contract_id")
    product_type = payment.get("product_type", "")
    period_months = payment.get("period_months")
    apply_num = auth_result.get("applNum", "")

    expired_at: Optional[str] = None
    if product_type in SAAS_PRODUCT_TYPES and period_months:
        expired_at = calc_expired_at(now, period_months)

    service_status = service_status_after_card_pay(contract_id)

    update_row: dict[str, Any] = {
        "status_code": "SUCCESS",
        "service_status": service_status,
        "pg_method": paymethod,
        "inicis_tid": auth_result.get("tid", ""),
        "inicis_auth_code": apply_num,
        "inicis_card_name": auth_result.get("P_FN_NM") or auth_result.get("CARD_Num", ""),
        "inicis_raw": auth_result,
        "paid_at": now,
        "updated_at": now,
    }
    if expired_at:
        update_row["expired_at"] = expired_at

    supabase.table("payments").update(update_row).eq("id", payment_id).execute()

    if contract_id:
        supabase.table("contracts").update({"is_active": True, "updated_at": now}).eq("id", contract_id).execute()

    if not with_redirect_qs:
        return None

    return {
        "qs_params": {
            "resultCode": "00",
            "oid": order_id,
            "goodname": auth_result.get("goodName", goodname),
            "price": auth_result.get("TotPrice", price),
            "paymethod": paymethod,
            "applnum": apply_num,
            "payment_id": payment_id,
            "expired_at": expired_at or "",
        }
    }


# ════════════════════════════════════════════════════════════════════════
# VBANK (가상계좌) 결제 — 연결 서비스 전용
# ════════════════════════════════════════════════════════════════════════

def create_vbank_record(body: VbankPrepareBody, sign_key: str) -> dict:
    """vbank_prepare — DB INSERT + 서명 파라미터 + matching_contracts 연결."""
    if body.product_type != "DIAGNOSIS" and not body.matching_contract_id:
        raise PaymentPrepareError(400, "matching_contract_id는 연결 서비스 결제 시 필수입니다.")
    if body.product_type == "DIAGNOSIS" and not (body.user_id or body.auth_token or body.public_token):
        raise PaymentPrepareError(400, "DIAGNOSIS는 user_id 또는 auth_token/public_token 중 하나가 필요합니다.")

    supabase = get_supabase()
    order_id = make_order_id()
    timestamp = ts_ms()
    price_str = str(body.amount)
    m_key = sha256(sign_key)
    signature = sha256(f"oid={order_id}&price={price_str}&timestamp={timestamp}")
    verification = sha256(f"oid={order_id}&price={price_str}&signKey={sign_key}&timestamp={timestamp}")

    supply_amount, vat_amount = split_supply_vat(body.amount)
    now = now_iso()

    vbank_expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=body.vbank_expire_min)
    ).isoformat()

    row: dict[str, Any] = {
        "user_id": body.user_id,
        "product_type": body.product_type,
        "payment_method": "INICIS",
        "pg_method": "VBANK",
        "payment_type": "VBANK",
        "supply_amount": supply_amount,
        "vat_amount": vat_amount,
        "total_amount": body.amount,
        "inicis_order_id": order_id,
        "status_code": "PENDING",
        "service_status": "PAID",
        "vbank_expires_at": vbank_expires_at,
        "created_at": now,
        "updated_at": now,
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
        raise PaymentPrepareError(500, "결제 레코드 생성 실패")

    payment_id = res.data[0]["id"]

    if body.matching_contract_id:
        supabase.table("matching_contracts").update(
            {"payment_id": payment_id, "updated_at": now}
        ).eq("id", body.matching_contract_id).execute()

    log.info(f"[VBANK PREPARE] oid={order_id} product={body.product_type}")

    return {
        "status": "success",
        "data": {
            "payment_id": payment_id,
            "mid": INICIS_MID,
            "mKey": m_key,
            "oid": order_id,
            "price": price_str,
            "goodname": body.goodname,
            "buyername": body.buyername or "고객",
            "buyertel": body.buyertel or "00000000000",
            "buyeremail": body.buyeremail or "",
            "timestamp": timestamp,
            "verification": verification,
            "signature": signature,
            "use_chkfake": "Y",
            "returnUrl": DEFAULT_RETURN_URL,
            "closeUrl": DEFAULT_CLOSE_URL,
            "charset": "UTF-8",
            "gopaymethod": "Vbank",
            "vbankexpire": body.vbank_expire_min,
        },
    }


def process_vbank_deposit(
    order_id: str,
    result_code: str,
    depositor: str,
    raw_data: dict,
) -> str:
    """VBANK 입금 노티 — payments / matching_contracts / matching_requests / notifications."""
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

    payment = pay_res.data[0]
    payment_id = payment["id"]
    matching_contract_id = payment.get("matching_contract_id")

    if payment["status_code"] == "SUCCESS":
        return "OK"

    if result_code not in ("", "00", "0000"):
        log.info(f"[VBANK NOTI] 입금 취소: resultCode={result_code}")
        supabase.table("payments").update(
            {
                "status_code": "FAILED",
                "fail_reason": f"VBANK 입금 취소 (resultCode={result_code})",
                "updated_at": now_iso(),
            }
        ).eq("id", payment_id).execute()
        return "OK"

    now = now_iso()
    supabase.table("payments").update(
        {
            "status_code": "SUCCESS",
            "service_status": "ACTIVE",
            "vbank_depositor": depositor,
            "vbank_confirmed_at": now,
            "paid_at": now,
            "inicis_raw": raw_data,
            "updated_at": now,
        }
    ).eq("id", payment_id).execute()
    log.info(f"[VBANK NOTI] 입금 확인 — payment_id={payment_id}")

    if matching_contract_id:
        supabase.table("matching_contracts").update(
            {"paid_confirmed_at": now, "status": "ACTIVE", "updated_at": now}
        ).eq("id", matching_contract_id).execute()

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
                        "status": "IN_PROGRESS", "at": now,
                        "by": "system", "memo": "가상계좌 입금 확인 → 서비스 시작",
                    })
                    supabase.table("matching_requests").update(
                        {"status": "IN_PROGRESS", "status_history": history, "updated_at": now}
                    ).eq("id", request_id).execute()

    if payment.get("user_id"):
        supabase.table("notifications").insert({
            "user_id": payment["user_id"],
            "title": "계약금 입금 확인",
            "body": f"계약금 {int(payment['total_amount']):,}원 입금이 확인되었습니다.",
            "type": "PAYMENT",
            "is_read": False,
            "created_at": now,
        }).execute()

    return "OK"


# ════════════════════════════════════════════════════════════════════════
# 빌링(구독결제) — 매뉴얼 기반 전면 재작성
# 매뉴얼: https://manual.inicis.com/pay/bill.html
#
# 키 체계 (매뉴얼 기준):
#   빌키발급: INILite Key + SHA512 → inilitepay.inicis.com
#   빌링승인: INIAPI Key + SHA512 → iniapi.inicis.com
#   취소/환불: INIAPI Key + SHA512 → iniapi.inicis.com
# ════════════════════════════════════════════════════════════════════════

def run_billing_prepare(body) -> Dict[str, Any]:
    """빌링키 발급 준비 — STEP1.

    프론트에서 이 응답의 파라미터를 form에 세팅하고
    BILLING_ISSUE_URL(inilitepay.inicis.com/pay/card/billing)로 POST.

    매뉴얼 STEP1:
      hashData = SHA512(price + mid + orderId + timestamp + INILiteKey)
      timestamp = YYYYMMDDhhmmss (millis 아님!)
    """
    mid = INICIS_BILLING_MID
    inilite_key = INICIS_INILITE_KEY
    if not mid:
        raise PaymentPrepareError(500, "INICIS_BILLING_MID 환경변수가 설정되지 않았습니다.")
    if not inilite_key:
        raise PaymentPrepareError(500, "INICIS_INILITE_KEY 환경변수가 설정되지 않았습니다.")

    supabase = get_supabase()
    now = now_iso()
    order_id = f"TAI-BIL-{datetime.now():%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"
    timestamp = ts_yyyymmddhhmmss()  # YYYYMMDDhhmmss 형식
    price_str = str(body.amount)

    # SHA512(price + mid + orderId + timestamp + INILiteKey)
    hash_data = sha512(price_str + mid + order_id + timestamp + inilite_key)

    supply, vat = split_supply_vat(body.amount)
    row: Dict[str, Any] = {
        "user_id": body.user_id,
        "product_type": body.product_type,
        "plan_code": body.plan_code or "",
        "plan_name": body.goodname,
        "amount": body.amount,
        "supply_amount": supply,
        "vat_amount": vat,
        "billing_cycle": "monthly",
        "status": "PENDING",
        "inicis_order_id": order_id,
        "created_at": now,
        "updated_at": now,
    }
    if body.company_id:
        row["company_id"] = body.company_id
    if hasattr(body, "factory_id") and body.factory_id:
        row["factory_id"] = body.factory_id

    ins = supabase.table("subscriptions").insert(row).execute()
    if not ins.data:
        raise PaymentPrepareError(500, "구독 생성 실패")
    sub = ins.data[0]

    log.info(f"[BILLING PREPARE] orderId={order_id} sub={sub['id']} mid={mid}")

    return {
        "status": "success",
        "data": {
            "subscription_id": sub["id"],
            "billing_issue_url": BILLING_ISSUE_URL,
            "mid": mid,
            "orderId": order_id,
            "price": price_str,
            "timestamp": timestamp,
            "hashData": hash_data,
            "goodName": body.goodname,
            "buyerName": body.buyername or "고객",
            "buyerTel": body.buyertel or "00000000000",
            "buyerEmail": body.buyeremail or "",
            "returnUrl": BILLING_RETURN_URL,
        },
    }


def run_billing_return(body) -> Dict[str, Any]:
    """빌링키 발급 결과 처리 — STEP2.

    이니시스가 returnUrl로 POST한 결과:
      resultCode = "SUCCESS" (단건의 "0000"과 다름!)
      billkey = AES256 암호화 → INILiteKey로 복호화 필요
    """
    if body.resultCode != "SUCCESS":
        raise PaymentPrepareError(400, body.resultMessage or "빌링키 발급 실패")

    if not body.billkey:
        raise PaymentPrepareError(400, "billkey가 응답에 없습니다.")

    inilite_key = INICIS_INILITE_KEY
    if not inilite_key:
        raise PaymentPrepareError(500, "INICIS_INILITE_KEY 미설정")

    # AES256 복호화
    bill_key = decrypt_billkey(body.billkey, inilite_key)
    if not bill_key:
        # 복호화 실패 시 원본 그대로 사용 시도 (이니시스 테스트 환경은 평문일 수 있음)
        log.warning("[BILLING RETURN] billkey 복호화 실패, 원본 사용 시도")
        bill_key = body.billkey

    supabase = get_supabase()
    now = now_iso()
    mid = body.mid or INICIS_BILLING_MID

    # billing_keys 저장
    key_ins = supabase.table("billing_keys").insert({
        "user_id": None,  # subscriptions에서 추출 예정
        "bill_key": bill_key,
        "mid": mid,
        "inicis_tid": body.tid or "",
        "card_name": body.cardCompanyName or "",
        "card_num_masked": body.cardNumber or "",
        "card_issuer_code": body.cardCode or "",
        "status": "ACTIVE",
        "inicis_raw": {
            "resultCode": body.resultCode,
            "orderId": body.orderId,
            "tid": body.tid,
            "cardNumber": body.cardNumber,
            "cardCode": body.cardCode,
            "cardCompanyName": body.cardCompanyName,
            "cardType": body.cardType,
            "cardKind": body.cardKind,
        },
        "created_at": now,
        "updated_at": now,
    }).execute()

    if not key_ins.data:
        raise PaymentPrepareError(500, "빌링키 저장 실패")

    billing_key_id = key_ins.data[0]["id"]

    # subscriptions 연결 (orderId로 찾기)
    sub_id = None
    if body.orderId:
        sub_res = (
            supabase.table("subscriptions")
            .select("id, user_id, company_id")
            .eq("inicis_order_id", body.orderId)
            .limit(1)
            .execute()
        )
        if sub_res.data:
            sub = sub_res.data[0]
            sub_id = sub["id"]

            # billing_keys에 user_id, subscription_id 연결
            supabase.table("billing_keys").update({
                "user_id": sub.get("user_id"),
                "subscription_id": sub_id,
                "updated_at": now,
            }).eq("id", billing_key_id).execute()

            # subscriptions 활성화
            supabase.table("subscriptions").update({
                "billing_key_id": billing_key_id,
                "status": "ACTIVE",
                "started_at": now,
                "updated_at": now,
            }).eq("id", sub_id).execute()

    log.info(f"[BILLING RETURN] billkey 저장 완료. key_id={billing_key_id} sub={sub_id}")

    return {
        "status": "success",
        "data": {
            "billing_key_id": billing_key_id,
            "subscription_id": sub_id,
            "card_name": body.cardCompanyName,
            "card_number": body.cardNumber,
        },
    }


def run_billing_charge(body) -> Dict[str, Any]:
    """빌링 승인(과금) — iniapi.inicis.com/api/v1/billing.

    매뉴얼:
      URL: https://iniapi.inicis.com/api/v1/billing
      Content-Type: application/x-www-form-urlencoded;charset=utf-8
      hashData = SHA512(INIAPIKey + type + paymethod + timestamp + clientIp
                        + mid + moid + price + billKey)
    """
    iniapi_key = INICIS_INIAPI_KEY
    mid = INICIS_BILLING_MID
    if not iniapi_key:
        raise PaymentPrepareError(500, "INICIS_INIAPI_KEY 미설정")
    if not mid:
        raise PaymentPrepareError(500, "INICIS_BILLING_MID 미설정")

    supabase = get_supabase()
    now = now_iso()

    # subscription 조회
    sub_res = supabase.table("subscriptions").select("*").eq("id", body.subscription_id).limit(1).execute()
    if not sub_res.data:
        raise PaymentPrepareError(404, "구독을 찾을 수 없습니다.")
    sub = sub_res.data[0]

    # billing_key 조회
    key_res = (
        supabase.table("billing_keys")
        .select("*")
        .eq("id", sub.get("billing_key_id"))
        .eq("status", "ACTIVE")
        .limit(1)
        .execute()
    )
    if not key_res.data:
        raise PaymentPrepareError(404, "활성 빌링키가 없습니다.")
    key_row = key_res.data[0]

    amount = int(body.amount or sub.get("amount") or 0)
    if amount <= 0:
        raise PaymentPrepareError(400, "청구 금액이 올바르지 않습니다.")

    moid = f"TAI-BIL-CHG-{datetime.now():%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"
    timestamp = ts_yyyymmddhhmmss()
    client_ip = get_server_ip()
    price_str = str(amount)

    # SHA512(INIAPIKey + type + paymethod + timestamp + clientIp + mid + moid + price + billKey)
    hash_str = iniapi_key + "Billing" + "Card" + timestamp + client_ip + mid + moid + price_str + key_row["bill_key"]
    hash_data = sha512(hash_str)

    payload = {
        "type": "Billing",
        "paymethod": "Card",
        "timestamp": timestamp,
        "clientIp": client_ip,
        "mid": mid,
        "url": "https://taieng.co.kr",
        "moid": moid,
        "goodName": body.goodname or sub.get("plan_name", "TAI Safe 정기결제"),
        "buyerName": "고객",
        "buyerEmail": "",
        "price": price_str,
        "billKey": key_row["bill_key"],
        "authentification": "00",
        "hashData": hash_data,
    }

    log.info(f"[BILLING CHARGE] moid={moid} amount={amount} mid={mid}")

    try:
        resp = _requests.post(
            BILLING_CHARGE_URL,
            data=payload,
            timeout=30,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
        )
        result = resp.json()
    except Exception as e:
        log.error(f"[BILLING CHARGE] API 호출 실패: {e}")
        raise PaymentPrepareError(502, f"빌링 승인 API 호출 실패: {e}")

    if str(result.get("resultCode", "")) != "00":
        # 실패 처리
        fc = int(sub.get("failure_count", 0)) + 1
        sub_update: Dict[str, Any] = {
            "failure_count": fc,
            "last_failure_at": now,
            "last_failure_reason": result.get("resultMsg", ""),
            "updated_at": now,
        }
        if fc >= 3:
            sub_update["status"] = "PAUSED"
        supabase.table("subscriptions").update(sub_update).eq("id", sub["id"]).execute()
        raise PaymentPrepareError(400, result.get("resultMsg", "빌링 승인 실패"))

    # 성공: payments 기록
    supply, vat = split_supply_vat(amount)
    supabase.table("payments").insert({
        "user_id": sub.get("user_id"),
        "company_id": sub.get("company_id"),
        "product_type": sub["product_type"],
        "plan_code": sub.get("plan_code"),
        "payment_method": "INICIS_BILLING",
        "payment_type": "BILLING",
        "total_amount": amount,
        "supply_amount": supply,
        "vat_amount": vat,
        "inicis_order_id": moid,
        "inicis_tid": result.get("tid", ""),
        "inicis_auth_code": result.get("payAuthCode", ""),
        "status_code": "SUCCESS",
        "service_status": "ACTIVE",
        "inicis_raw": result,
        "paid_at": now,
        "subscription_id": sub["id"],
        "billing_key_id": key_row["id"],
        "is_recurring": True,
        "created_at": now,
        "updated_at": now,
    }).execute()

    # subscription 갱신
    next_dt = datetime.now(timezone.utc) + relativedelta(months=1)
    supabase.table("subscriptions").update({
        "status": "ACTIVE",
        "failure_count": 0,
        "last_billed_at": now,
        "next_billing_at": next_dt.isoformat(),
        "updated_at": now,
    }).eq("id", sub["id"]).execute()

    log.info(f"[BILLING CHARGE] 성공 tid={result.get('tid')} amount={amount}")

    return {
        "status": "success",
        "data": {
            "subscription_id": sub["id"],
            "charged_amount": amount,
            "tid": result.get("tid"),
            "moid": moid,
        },
    }


def run_billing_cancel(
    subscription_id: str,
    reason: str = "사용자 요청",
    cancelled_by: Optional[str] = None,
) -> Dict[str, Any]:
    """구독 해지 — 빌링키 폐기 + 구독 상태 변경.

    ※ 이니시스에는 별도의 빌키 폐기 API가 없음.
    빌키를 DB에서 REVOKED 처리하고 더 이상 과금하지 않으면 됨.
    """
    supabase = get_supabase()
    now = now_iso()

    sub_res = supabase.table("subscriptions").select("*").eq("id", subscription_id).limit(1).execute()
    if not sub_res.data:
        raise PaymentPrepareError(404, "구독을 찾을 수 없습니다.")
    sub = sub_res.data[0]

    # 빌링키 REVOKED 처리
    if sub.get("billing_key_id"):
        supabase.table("billing_keys").update({
            "status": "REVOKED",
            "revoked_at": now,
            "revoke_reason": reason,
            "updated_at": now,
        }).eq("id", sub["billing_key_id"]).execute()

    # 구독 CANCELLED
    supabase.table("subscriptions").update({
        "status": "CANCELLED",
        "cancelled_at": now,
        "cancel_reason": reason,
        "updated_at": now,
    }).eq("id", subscription_id).execute()

    log.info(f"[BILLING CANCEL] sub={subscription_id} reason={reason}")

    return {
        "status": "success",
        "data": {"subscription_id": subscription_id, "status": "CANCELLED"},
    }


# ════════════════════════════════════════════════════════════════════════
# 취소/환불 — iniapi.inicis.com/api/v1/refund
# 매뉴얼: https://manual.inicis.com/pay/cancel.html
# ════════════════════════════════════════════════════════════════════════

def run_refund(
    payment_id: str,
    reason: str = "사용자 요청",
    cancelled_by: Optional[str] = None,
) -> Dict[str, Any]:
    """전체 취소 — iniapi.inicis.com/api/v1/refund.

    매뉴얼:
      hashData = SHA512(INIAPIKey + type + paymethod + timestamp + clientIp + mid + tid)
    """
    iniapi_key = INICIS_INIAPI_KEY
    if not iniapi_key:
        raise PaymentPrepareError(500, "INICIS_INIAPI_KEY 미설정")

    supabase = get_supabase()
    pay_res = supabase.table("payments").select("*").eq("id", payment_id).limit(1).execute()
    if not pay_res.data:
        raise PaymentPrepareError(404, "결제 내역을 찾을 수 없습니다.")

    payment = pay_res.data[0]
    tid = payment.get("inicis_tid")
    if not tid:
        raise PaymentPrepareError(400, "이니시스 거래번호(TID)가 없습니다.")

    if payment["status_code"] != "SUCCESS":
        raise PaymentPrepareError(400, f"취소 불가 상태: {payment['status_code']}")

    # 결제수단 결정
    pg_method = payment.get("pg_method", "Card")
    paymethod_map = {"Card": "Card", "CARD": "Card", "VBANK": "Vacct", "Vbank": "Vacct"}
    paymethod = paymethod_map.get(pg_method, "Card")

    mid = payment.get("inicis_raw", {}).get("mid", INICIS_MID)
    timestamp = ts_yyyymmddhhmmss()
    client_ip = get_server_ip()

    hash_str = iniapi_key + "Refund" + paymethod + timestamp + client_ip + mid + tid
    hash_data = sha512(hash_str)

    payload = {
        "type": "Refund",
        "paymethod": paymethod,
        "timestamp": timestamp,
        "clientIp": client_ip,
        "mid": mid,
        "tid": tid,
        "msg": reason,
        "hashData": hash_data,
    }

    log.info(f"[REFUND] payment_id={payment_id} tid={tid} mid={mid}")

    try:
        resp = _requests.post(
            REFUND_URL,
            data=payload,
            timeout=30,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
        )
        result = resp.json()
    except Exception as e:
        raise PaymentPrepareError(502, f"취소 API 호출 실패: {e}")

    if str(result.get("resultCode", "")) != "00":
        raise PaymentPrepareError(400, result.get("resultMsg", "취소 실패"))

    now = now_iso()
    supabase.table("payments").update({
        "status_code": "CANCELLED",
        "service_status": "ENDED",
        "cancelled_at": now,
        "cancel_reason": reason,
        "inicis_raw": result,
        "updated_at": now,
    }).eq("id", payment_id).execute()

    log.info(f"[REFUND] 성공 payment_id={payment_id}")

    return {"status": "success", "data": result}


def run_partial_refund(
    payment_id: str,
    cancel_amount: int,
    reason: str = "사용자 요청",
) -> Dict[str, Any]:
    """부분 취소 — iniapi.inicis.com/api/v1/refund.

    매뉴얼:
      type = "PartialRefund"
      hashData = SHA512(INIAPIKey + type + paymethod + timestamp + clientIp
                        + mid + tid + price + confirmPrice)
    """
    iniapi_key = INICIS_INIAPI_KEY
    if not iniapi_key:
        raise PaymentPrepareError(500, "INICIS_INIAPI_KEY 미설정")

    supabase = get_supabase()
    pay_res = supabase.table("payments").select("*").eq("id", payment_id).limit(1).execute()
    if not pay_res.data:
        raise PaymentPrepareError(404, "결제 내역을 찾을 수 없습니다.")

    payment = pay_res.data[0]
    tid = payment.get("inicis_tid")
    if not tid:
        raise PaymentPrepareError(400, "이니시스 거래번호(TID)가 없습니다.")

    total = int(payment["total_amount"])
    confirm_price = total - cancel_amount
    if confirm_price < 0:
        raise PaymentPrepareError(400, "취소 금액이 결제 금액을 초과합니다.")

    pg_method = payment.get("pg_method", "Card")
    paymethod_map = {"Card": "Card", "CARD": "Card", "VBANK": "Vacct"}
    paymethod = paymethod_map.get(pg_method, "Card")

    mid = payment.get("inicis_raw", {}).get("mid", INICIS_MID)
    timestamp = ts_yyyymmddhhmmss()
    client_ip = get_server_ip()
    price_str = str(cancel_amount)
    confirm_str = str(confirm_price)

    hash_str = (
        iniapi_key + "PartialRefund" + paymethod + timestamp + client_ip
        + mid + tid + price_str + confirm_str
    )
    hash_data = sha512(hash_str)

    payload = {
        "type": "PartialRefund",
        "paymethod": paymethod,
        "timestamp": timestamp,
        "clientIp": client_ip,
        "mid": mid,
        "tid": tid,
        "msg": reason,
        "price": price_str,
        "confirmPrice": confirm_str,
        "hashData": hash_data,
    }

    log.info(f"[PARTIAL REFUND] payment_id={payment_id} cancel={cancel_amount} remain={confirm_price}")

    try:
        resp = _requests.post(
            REFUND_URL,
            data=payload,
            timeout=30,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
        )
        result = resp.json()
    except Exception as e:
        raise PaymentPrepareError(502, f"부분취소 API 호출 실패: {e}")

    if str(result.get("resultCode", "")) != "00":
        raise PaymentPrepareError(400, result.get("resultMsg", "부분취소 실패"))

    now = now_iso()
    supabase.table("payments").update({
        "memo": f"부분취소 {cancel_amount}원 / 잔여 {confirm_price}원",
        "inicis_raw": result,
        "updated_at": now,
    }).eq("id", payment_id).execute()

    return {"status": "success", "data": result}


# ════════════════════════════════════════════════════════════════════════
# Health Probe
# ════════════════════════════════════════════════════════════════════════

from services.health_registry import register_probe


async def _probe_payment():
    mid = os.environ.get("INICIS_MID", "")
    billing_mid = os.environ.get("INICIS_BILLING_MID", "")
    if not mid:
        return {"status": "warn", "detail": "INICIS_MID 미설정"}
    result = {"inicis_mid": mid[:4] + "****"}
    if billing_mid:
        result["billing_mid"] = billing_mid[:4] + "****"
    return result


register_probe(
    "payment",
    _probe_payment,
    critical=True,
    desc_ko="결제 시스템",
    meta={
        "impacts": [
            {"name": "법령진단 결제", "url": "https://new.taieng.co.kr/service/diagnosis.html"},
            {"name": "SaaS 구독", "url": "https://new.taieng.co.kr/service/saas.html"},
        ],
        "fix_links": [
            {"name": "Railway 환경변수", "url": "https://railway.com/project/7c3ab53b-feb6-40a4-a4f0-7ade3f6e524b/variables"},
            {"name": "KG이니시스 관리자", "url": "https://iniweb.inicis.com"},
        ],
        "api": "POST /payments/inicis/prepare, POST /payments/inicis/billing/prepare",
        "code": "services/payment_svc.py",
    },
)
