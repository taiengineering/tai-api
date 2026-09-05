"""이니시스 결제 비즈니스 로직 (HTTP 제외).

규칙: docs/DEV_RULES_SERVICE_LAYER.md STEP 3

PROOF-TYPE-WRITER (2026-09-05):
  - run_inicis_prepare / create_vbank_record: INSERT 시 body.proof_type 저장.
  - process_card_success: 실제 paymethod가 canonical CARD 면 proof_type=CARD_RECEIPT (그 외 미설정->prepare값 보존).
  - run_billing_charge: CardBilling payment INSERT 에 proof_type=CARD_RECEIPT.
  - process_vbank_deposit: proof_type 미변경.
"""
from __future__ import annotations

import base64 as _base64
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from uuid import uuid4

import requests as _requests

from db.supabase_client import get_supabase
from schemas.payment import PrepareBody, VbankPrepareBody
from services.payment_helpers import (
    DEFAULT_CLOSE_URL,
    DEFAULT_RETURN_URL,
    INICIS_KEY_PASSWORD,
    INICIS_KEY_PATH,
    INICIS_MID,
    SAAS_PRODUCT_TYPES,
    add_vat,
    calc_expired_at,
    make_order_id,
    now_iso,
    service_status_after_card_pay,
    sha256,
    split_supply_vat,
    ts_ms,
)
from services.time import now_kst

log = logging.getLogger(__name__)


def _sector_from_plan_code(plan_code: Optional[str]) -> str:
    """plan_code 앞부분에서 진단 sector 파생.

    예: 'INDUSTRY_STARTER' -> 'INDUSTRY', 'BUILDING_V2' -> 'BUILDING',
        'CONSTRUCTION_STANDARD' -> 'CONSTRUCTION'.
    free-diagnosis 프론트가 ?paid=<sector> 로 소비하여 결제 후 상세입력(공정·설비)로
    바로 진입하게 하기 위한 routing 값이다. 결제 권한/정산과 무관.
    매칭 실패 시 빈 문자열(프론트는 기존 흐름 유지).
    """
    if not plan_code:
        return ""
    head = str(plan_code).strip().upper().split("_")[0]
    return head if head in {"BUILDING", "INDUSTRY", "CONSTRUCTION"} else ""


class PaymentPrepareError(Exception):
    """결제 준비 단계 비즈니스 오류 (라우터에서 HTTPException으로 변환)."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def load_sign_key() -> str:
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


def load_mpriv_pem() -> Optional[bytes]:
    b64 = os.getenv("INICIS_MPRIV_PEM_B64", "").strip()
    if b64:
        try:
            return _base64.b64decode(b64)
        except Exception as e:
            log.error(f"[INICIS] INICIS_MPRIV_PEM_B64 디코딩 실패: {e}")
    try:
        with open(os.path.join(INICIS_KEY_PATH, "mpriv.pem"), "rb") as f:
            return f.read()
    except Exception as e:
        log.warning(f"[INICIS] mpriv.pem 로드 실패: {e}")
        return None


def rsa_sign_sha256(data: str, pem_bytes: bytes, password: str) -> Optional[str]:
    try:
        from Crypto.Hash import SHA256 as _SHA256
        from Crypto.PublicKey import RSA
        from Crypto.Signature import pkcs1_15

        key = RSA.import_key(pem_bytes, passphrase=password)
        h = _SHA256.new(data.encode("utf-8"))
        sig = pkcs1_15.new(key).sign(h)
        return _base64.b64encode(sig).decode("utf-8")
    except Exception as e:
        log.error(f"[INICIS] RSA 서명 실패: {e}")
        return None


def call_pay_auth(auth_token: str, auth_url: str, sign_key: str, *, mid: str = "") -> Dict[str, Any]:
    """STEP3 승인 요청. mid 미지정 시 단건결제 INICIS_MID 사용."""
    actual_mid = mid or INICIS_MID
    timestamp = ts_ms()
    sig_data = f"authToken={auth_token}&timestamp={timestamp}"
    veri_data = f"authToken={auth_token}&signKey={sign_key}&timestamp={timestamp}"
    signature = sha256(sig_data)
    verification = sha256(veri_data)
    params: Dict[str, str] = {
        "mid": actual_mid,
        "authToken": auth_token,
        "timestamp": timestamp,
        "signature": signature,
        "verification": verification,
        "charset": "UTF-8",
        "format": "JSON",
    }
    pem = load_mpriv_pem()
    if pem:
        rsa_sig = rsa_sign_sha256(auth_token, pem, INICIS_KEY_PASSWORD)
        if rsa_sig:
            params["signData"] = rsa_sig
    try:
        resp = _requests.post(
            auth_url,
            data=params,
            timeout=30,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        result = resp.json()
        log.info(
            f"[INICIS STEP3] resultCode={result.get('resultCode')} resultMsg={result.get('resultMsg')}"
        )
        return result
    except Exception as e:
        log.error(f"[INICIS] 승인 API 실패: {e}")
        raise


def run_inicis_prepare(body: PrepareBody) -> dict:
    """단건 INICIS 결제 준비 — DB insert + 서명 파라미터."""
    if body.product_type in SAAS_PRODUCT_TYPES and not body.period_months:
        raise PaymentPrepareError(400, "SaaS 상품은 period_months가 필수입니다.")

    supabase = get_supabase()
    sign_key = load_sign_key()
    order_id = make_order_id()
    timestamp = ts_ms()
    total_with_vat = add_vat(body.amount)
    price_str = str(total_with_vat)
    m_key = sha256(sign_key)
    sig_data = f"oid={order_id}&price={price_str}&timestamp={timestamp}"
    veri_data = f"oid={order_id}&price={price_str}&signKey={sign_key}&timestamp={timestamp}"
    signature = sha256(sig_data)
    verification = sha256(veri_data)
    log.info(f"[INICIS STEP1] oid={order_id} user={body.user_id} product={body.product_type}")

    supply_amount = body.amount
    vat_amount = total_with_vat - supply_amount
    now = now_iso()

    row: dict = {
        "user_id": body.user_id,
        "product_type": body.product_type,
        "payment_method": "INICIS",
        "payment_type": body.payment_type or "CARD",
        "supply_amount": supply_amount,
        "vat_amount": vat_amount,
        "total_amount": total_with_vat,
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
    # PROOF-TYPE-WRITER: 클라이언트 증빙선택(TAX_INVOICE/CASH_RECEIPT/NONE). 미지정은 NULL 유지.
    if getattr(body, "proof_type", None):
        row["proof_type"] = body.proof_type

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
            "returnUrl": DEFAULT_RETURN_URL,
            "closeUrl": DEFAULT_CLOSE_URL,
            "charset": "UTF-8",
            "gopaymethod": "",
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
    plan_code: Optional[str] = None,
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

    qs: dict[str, Any] = {
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
    _sector = _sector_from_plan_code(plan_code)
    if _sector:
        qs["sector"] = _sector

    return {"qs_params": qs}


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
    """카드 등 승인 성공 — payments UPDATE + 계약 활성화. inicis_return 시 리다이렉트 쿼리 dict."""
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

    # PROOF-TYPE-WRITER: 실제 승인 method가 canonical CARD 면 서버가 CARD_RECEIPT 확정.
    # DirectBank/VBank/UNKNOWN 은 설정하지 않아 prepare 시점 선택값을 보존한다.
    from services.tax_invoice_request_svc import canonical_payment_instrument
    if canonical_payment_instrument(paymethod) == "CARD":
        update_row["proof_type"] = "CARD_RECEIPT"

    supabase.table("payments").update(update_row).eq("id", payment_id).execute()

    try:
        from services.payment_post_process import on_payment_success_sync
        on_payment_success_sync(str(payment_id))
    except Exception as e:
        log.error("Payment post-process failed: %s", e)

    if contract_id:
        supabase.table("contracts").update({"is_active": True, "updated_at": now}).eq("id", contract_id).execute()

    if not with_redirect_qs:
        return None

    qs: dict[str, Any] = {
        "resultCode": "00",
        "oid": order_id,
        "goodname": auth_result.get("goodName", goodname),
        "price": auth_result.get("TotPrice", price),
        "paymethod": paymethod,
        "applnum": apply_num,
        "payment_id": payment_id,
        "expired_at": expired_at or "",
    }
    _sector = _sector_from_plan_code(payment.get("plan_code"))
    if _sector:
        qs["sector"] = _sector

    return {"qs_params": qs}


def create_vbank_record(body: VbankPrepareBody, sign_key: str) -> dict:
    """vbank_prepare — DB INSERT + 서명 파라미터 + matching_contracts 연결."""
    if body.product_type != "DIAGNOSIS" and not body.matching_contract_id:
        raise PaymentPrepareError(400, "matching_contract_id는 연결 서비스 결제 시 필수입니다.")
    if body.product_type == "DIAGNOSIS" and not (body.user_id or body.auth_token or body.public_token):
        raise PaymentPrepareError(400, "DIAGNOSIS는 user_id 또는 auth_token/public_token 중 하나가 필요합니다.")

    supabase = get_supabase()
    order_id = make_order_id()
    timestamp = ts_ms()
    total_with_vat = add_vat(body.amount)
    price_str = str(total_with_vat)
    m_key = sha256(sign_key)
    sig_data = f"oid={order_id}&price={price_str}&timestamp={timestamp}"
    veri_data = f"oid={order_id}&price={price_str}&signKey={sign_key}&timestamp={timestamp}"
    signature = sha256(sig_data)
    verification = sha256(veri_data)

    supply_amount = body.amount
    vat_amount = total_with_vat - supply_amount
    now = now_iso()

    vbank_expires_at = (
        now_kst() + timedelta(minutes=body.vbank_expire_min)
    ).isoformat()

    row: dict[str, Any] = {
        "user_id": body.user_id,
        "product_type": body.product_type,
        "payment_method": "INICIS",
        "pg_method": "VBANK",
        "payment_type": "VBANK",
        "supply_amount": supply_amount,
        "vat_amount": vat_amount,
        "total_amount": total_with_vat,
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
    _plan_code = getattr(body, "plan_code", None)
    if _plan_code:
        row["plan_code"] = _plan_code
    # PROOF-TYPE-WRITER: VBANK 발급 시점이 writer. 클라이언트 증빙선택 그대로 저장.
    if getattr(body, "proof_type", None):
        row["proof_type"] = body.proof_type
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

    log.info(f"[VBANK PREPARE] oid={order_id} product={body.product_type} contract={body.matching_contract_id}")

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
    """VBANK 입금 노티 — payments / matching_contracts / matching_requests / notifications.

    PROOF-TYPE-WRITER: 이 경로에서 proof_type 를 다시 건드리지 않는다(발급 시점에 확정).
    """
    supabase = get_supabase()

    pay_res = (
        supabase.table("payments")
        .select(
            "id, status_code, user_id, company_id, total_amount, product_type, matching_contract_id"
        )
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

    try:
        from services.payment_post_process import on_payment_success_sync
        on_payment_success_sync(str(payment_id))
    except Exception as e:
        log.error("Payment post-process failed: %s", e)

    if matching_contract_id:
        supabase.table("matching_contracts").update(
            {
                "paid_confirmed_at": now,
                "status": "ACTIVE",
                "updated_at": now,
            }
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
                    history.append(
                        {
                            "status": "IN_PROGRESS",
                            "at": now,
                            "by": "system",
                            "memo": "가상계좌 입금 확인 → 서비스 시작",
                        }
                    )
                    supabase.table("matching_requests").update(
                        {
                            "status": "IN_PROGRESS",
                            "status_history": history,
                            "updated_at": now,
                        }
                    ).eq("id", request_id).execute()
                    log.info(f"[VBANK NOTI] 매칭 → IN_PROGRESS request_id={request_id}")

    if payment.get("user_id"):
        supabase.table("notifications").insert(
            {
                "user_id": payment["user_id"],
                "title": "계약금 입금 확인",
                "body": f"계약금 {int(payment['total_amount']):,}원 입금이 확인되었습니다. 서비스가 시작됩니다.",
                "type": "PAYMENT",
                "is_read": False,
                "created_at": now,
            }
        ).execute()

    return "OK"


@dataclass(frozen=True)
class BillingConfig:
    mid: str
    sign_key: str
    api_url: str


def _load_billing_config() -> BillingConfig:
    mid = os.getenv("INICIS_BILLING_MID", "").strip()
    sign_key = os.getenv("INICIS_BILLING_SIGN_KEY", "").strip()
    api_url = os.getenv("INICIS_BILLING_API_URL", "https://api.inicis.com/api/v1/billing").strip()
    if not mid:
        raise PaymentPrepareError(500, "INICIS_BILLING_MID 환경변수 필수")
    if not sign_key:
        raise PaymentPrepareError(500, "INICIS_BILLING_SIGN_KEY 환경변수 필수")
    return BillingConfig(mid=mid, sign_key=sign_key, api_url=api_url.rstrip("/"))


def _billing_api_post(path: str, payload: Dict[str, Any], cfg: BillingConfig) -> Dict[str, Any]:
    url = f"{cfg.api_url}/{path.lstrip('/')}"
    try:
        res = _requests.post(url, json=payload, timeout=30)
        data = res.json()
    except Exception as e:
        raise PaymentPrepareError(502, f"빌링 API 호출 실패: {e}") from e
    if str(data.get("resultCode", "")) not in {"0000", "00"}:
        raise PaymentPrepareError(400, data.get("resultMsg", "빌링 API 실패"))
    return data


def run_billing_prepare(body) -> Dict[str, Any]:
    cfg = _load_billing_config()
    supabase = get_supabase()
    now = now_iso()
    oid = f"TAI-BIL-{now_kst():%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"
    timestamp = ts_ms()
    total_with_vat = add_vat(body.amount)
    price_str = str(total_with_vat)
    signature = sha256(f"oid={oid}&price={price_str}&timestamp={timestamp}")
    verification = sha256(f"oid={oid}&price={price_str}&signKey={cfg.sign_key}&timestamp={timestamp}")

    row: Dict[str, Any] = {
        "user_id": body.user_id,
        "company_id": body.company_id,
        "plan_code": body.plan_code,
        "product_type": body.product_type,
        "status": "PENDING",
        "period_months": body.period_months,
        "price": total_with_vat,
        "currency": "WON",
        "inicis_order_id": oid,
        "created_at": now,
        "updated_at": now,
    }
    ins = supabase.table("subscriptions").insert(row).execute()
    if not ins.data:
        raise PaymentPrepareError(500, "구독 생성 실패")
    sub = ins.data[0]

    return {
        "status": "success",
        "data": {
            "subscription_id": sub["id"],
            "mid": cfg.mid,
            "mKey": sha256(cfg.sign_key),
            "oid": oid,
            "price": price_str,
            "goodname": body.goodname,
            "buyername": body.buyername or "고객",
            "buyertel": body.buyertel or "00000000000",
            "buyeremail": body.buyeremail or "",
            "timestamp": timestamp,
            "signature": signature,
            "verification": verification,
            "gopaymethod": "CardBilling",
        },
    }


def run_billing_return(body) -> Dict[str, Any]:
    cfg = _load_billing_config()
    supabase = get_supabase()
    if body.resultCode and body.resultCode not in {"0000", "00"}:
        raise PaymentPrepareError(400, body.resultMsg or "빌링 인증 실패")

    sub_res = (
        supabase.table("subscriptions")
        .select("*")
        .eq("inicis_order_id", body.oid)
        .limit(1)
        .execute()
    )
    if not sub_res.data:
        raise PaymentPrepareError(404, "구독 주문번호를 찾을 수 없습니다.")
    subscription = sub_res.data[0]
    now = now_iso()

    auth_payload = {
        "mid": cfg.mid,
        "authToken": body.authToken,
        "timestamp": ts_ms(),
        "signature": sha256(f"authToken={body.authToken}&timestamp={ts_ms()}"),
        "charset": "UTF-8",
        "format": "JSON",
    }
    auth_result = _billing_api_post("billkey", auth_payload, cfg)
    bill_key = auth_result.get("billKey") or auth_result.get("BILL_KEY") or ""
    if not bill_key:
        raise PaymentPrepareError(400, "빌링키 발급 실패")

    supabase.table("billing_keys").insert(
        {
            "subscription_id": subscription["id"],
            "user_id": subscription.get("user_id"),
            "company_id": subscription.get("company_id"),
            "inicis_order_id": body.oid,
            "bill_key": bill_key,
            "status": "ACTIVE",
            "failure_count": 0,
            "card_number_masked": body.cardNumber,
            "card_code": body.cardCode,
            "raw_data": auth_result,
            "created_at": now,
            "updated_at": now,
        }
    ).execute()
    supabase.table("subscriptions").update({"status": "ACTIVE", "updated_at": now}).eq("id", subscription["id"]).execute()

    charge_body = type("obj", (), {"subscription_id": subscription["id"], "amount": None, "goodname": None})
    charge_res = run_billing_charge(charge_body)
    return {"status": "success", "data": {"subscription_id": subscription["id"], "bill_key_issued": True, "first_charge": charge_res.get("data")}}


def run_billing_charge(body) -> Dict[str, Any]:
    cfg = _load_billing_config()
    supabase = get_supabase()
    now = now_iso()
    sub_res = supabase.table("subscriptions").select("*").eq("id", body.subscription_id).limit(1).execute()
    if not sub_res.data:
        raise PaymentPrepareError(404, "구독을 찾을 수 없습니다.")
    sub = sub_res.data[0]
    key_res = (
        supabase.table("billing_keys")
        .select("*")
        .eq("subscription_id", body.subscription_id)
        .eq("status", "ACTIVE")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not key_res.data:
        raise PaymentPrepareError(404, "활성 빌링키가 없습니다.")
    key_row = key_res.data[0]

    amount = int(body.amount or sub.get("price") or 0)
    if amount <= 0:
        raise PaymentPrepareError(400, "청구 금액이 올바르지 않습니다.")
    oid = f"TAI-BIL-CHG-{now_kst():%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"
    payload = {
        "mid": cfg.mid,
        "billKey": key_row["bill_key"],
        "oid": oid,
        "price": str(amount),
        "goodName": body.goodname or sub.get("product_type") or "TAI Safe 정기결제",
        "timestamp": ts_ms(),
    }
    try:
        result = _billing_api_post("payment", payload, cfg)
    except PaymentPrepareError as e:
        fc = int(key_row.get("failure_count") or 0) + 1
        key_update = {"failure_count": fc, "updated_at": now}
        sub_update = {"updated_at": now}
        if fc >= 3:
            key_update["status"] = "PAUSED"
            sub_update["status"] = "PAUSED"
        supabase.table("billing_keys").update(key_update).eq("id", key_row["id"]).execute()
        supabase.table("subscriptions").update(sub_update).eq("id", sub["id"]).execute()
        raise e

    supabase.table("payments").insert(
        {
            "user_id": sub.get("user_id"),
            "company_id": sub.get("company_id"),
            "product_type": sub.get("product_type"),
            "plan_code": sub.get("plan_code"),
            "payment_method": "INICIS_BILLING",
            "payment_type": "BILLING",
            "pg_method": "CardBilling",
            "proof_type": "CARD_RECEIPT",
            "total_amount": amount,
            "supply_amount": split_supply_vat(amount)[0],
            "vat_amount": split_supply_vat(amount)[1],
            "inicis_order_id": oid,
            "status_code": "SUCCESS",
            "service_status": "ACTIVE",
            "inicis_tid": result.get("tid", ""),
            "inicis_raw": result,
            "paid_at": now,
            "created_at": now,
            "updated_at": now,
        }
    ).execute()
    supabase.table("billing_keys").update({"failure_count": 0, "updated_at": now}).eq("id", key_row["id"]).execute()
    supabase.table("subscriptions").update({"status": "ACTIVE", "updated_at": now}).eq("id", sub["id"]).execute()
    return {"status": "success", "data": {"subscription_id": sub["id"], "charged_amount": amount, "oid": oid}}


def run_billing_cancel(subscription_id: str, reason: str = "사용자 요청", cancelled_by: Optional[str] = None) -> Dict[str, Any]:
    cfg = _load_billing_config()
    supabase = get_supabase()
    now = now_iso()
    sub_res = supabase.table("subscriptions").select("*").eq("id", subscription_id).limit(1).execute()
    if not sub_res.data:
        raise PaymentPrepareError(404, "구독을 찾을 수 없습니다.")
    key_res = (
        supabase.table("billing_keys")
        .select("*")
        .eq("subscription_id", subscription_id)
        .eq("status", "ACTIVE")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not key_res.data:
        raise PaymentPrepareError(404, "활성 빌링키가 없습니다.")
    key_row = key_res.data[0]

    payload = {"mid": cfg.mid, "billKey": key_row["bill_key"], "reason": reason, "timestamp": ts_ms()}
    _billing_api_post("billkey/revoke", payload, cfg)

    supabase.table("billing_keys").update(
        {"status": "REVOKED", "revoked_at": now, "revoke_reason": reason, "updated_at": now}
    ).eq("id", key_row["id"]).execute()
    supabase.table("subscriptions").update(
        {"status": "CANCELLED", "cancelled_at": now, "cancelled_by": cancelled_by, "updated_at": now}
    ).eq("id", subscription_id).execute()
    return {"status": "success", "data": {"subscription_id": subscription_id, "status": "CANCELLED"}}


def run_partial_refund(payment_id: str, amount: int, reason: str = "", cancelled_by: Optional[str] = None) -> dict:
    """부분 환불 — WO-1 refund_svc 위임 (이니시스 INIAPI 실연동)."""
    from services.refund_svc import run_partial_refund as _impl
    return _impl(payment_id, amount, reason, cancelled_by)


def run_refund(payment_id: str, reason: str = "", cancelled_by: Optional[str] = None) -> dict:
    """전체 환불 — WO-1 refund_svc 위임 (이니시스 INIAPI 실연동)."""
    from services.refund_svc import run_refund as _impl
    return _impl(payment_id, reason, cancelled_by)


from services.health_registry import register_probe


async def _probe_payment():
    mid = os.environ.get("INICIS_MID", "")
    if not mid:
        return {"status": "warn", "detail": "INICIS_MID 미설정"}
    return {"inicis_mid": mid[:4] + "****"}


register_probe(
    "payment",
    _probe_payment,
    critical=True,
    desc_ko="결제 시스템",
    meta={
        "impacts": [
            {"name": "법령진단 결제", "url": "https://taieng.co.kr/service/diagnosis.html"},
            {"name": "SaaS 구독", "url": "https://taieng.co.kr/service/saas.html"},
        ],
        "fix_links": [
            {"name": "Railway 환경변수", "url": "https://railway.com/project/7c3ab53b-feb6-40a4-a4f0-7ade3f6e524b/variables"},
            {"name": "KG이니시스 관리자", "url": "https://iniweb.inicis.com"},
        ],
        "api": "POST /payments/prepare, POST /payments/verify",
        "code": "services/payment_svc.py",
    },
)
