"""이니시스 결제 비즈니스 로직 (HTTP 제외).

규칙: docs/DEV_RULES_SERVICE_LAYER.md STEP 3
"""
from __future__ import annotations

import base64 as _base64
import logging
import os
from typing import Any, Dict, Optional

import requests as _requests

from db.supabase_client import get_supabase
from schemas.payment import PrepareBody
from services.payment_helpers import (
    DEFAULT_CLOSE_URL,
    DEFAULT_RETURN_URL,
    INICIS_KEY_PASSWORD,
    INICIS_KEY_PATH,
    INICIS_MID,
    SAAS_PRODUCT_TYPES,
    make_order_id,
    now_iso,
    sha256,
    split_supply_vat,
    ts_ms,
)

log = logging.getLogger(__name__)


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


def call_pay_auth(auth_token: str, auth_url: str, sign_key: str) -> Dict[str, Any]:
    timestamp = ts_ms()
    sig_data = f"authToken={auth_token}&timestamp={timestamp}"
    veri_data = f"authToken={auth_token}&signKey={sign_key}&timestamp={timestamp}"
    signature = sha256(sig_data)
    verification = sha256(veri_data)
    params: Dict[str, str] = {
        "mid": INICIS_MID,
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
    price_str = str(body.amount)
    m_key = sha256(sign_key)
    sig_data = f"oid={order_id}&price={price_str}&timestamp={timestamp}"
    veri_data = f"oid={order_id}&price={price_str}&signKey={sign_key}&timestamp={timestamp}"
    signature = sha256(sig_data)
    verification = sha256(veri_data)
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
            "returnUrl": DEFAULT_RETURN_URL,
            "closeUrl": DEFAULT_CLOSE_URL,
            "charset": "UTF-8",
            "gopaymethod": "Card",
        },
    }
