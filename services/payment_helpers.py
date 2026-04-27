"""payment 모듈 순수 유틸·상수 (HTTP·DB 없음).

v2.3 (2026-04-27)
  [FIX] returnUrl → api.taieng.co.kr 직접 (프록시 불필요)
        결제 페이지를 api.taieng.co.kr/payments/checkout 에서 서비스하므로
        returnUrl도 api.taieng.co.kr로 통일 — 도메인 일치
"""
from __future__ import annotations

import hashlib
import os
import time
from base64 import b64decode
from datetime import datetime, timezone
from functools import lru_cache
from typing import List, Optional
from urllib.parse import unquote
from uuid import uuid4

from dateutil.relativedelta import relativedelta

SAAS_PRODUCT_TYPES: List[str] = [
    "SAAS_CONSTRUCTION",
    "SAAS_FACILITY",
    "SAAS_BUILDING",
]

INICIS_MID = os.getenv("INICIS_MID", "taieng4350")
INICIS_KEY_PATH = os.getenv("INICIS_KEY_PATH", "/app/key/taieng4350")
INICIS_KEY_PASSWORD = os.getenv("INICIS_KEY_PASSWORD", "1111")

INICIS_BILLING_MID = os.getenv("INICIS_BILLING_MID", "")
INICIS_INILITE_KEY = os.getenv("INICIS_INILITE_KEY", "")
INICIS_INIAPI_KEY = os.getenv("INICIS_INIAPI_KEY", "")

INICIS_CLIENT_IP = os.getenv("INICIS_CLIENT_IP", "115.68.227.222")

BILLING_ISSUE_URL = "https://inilitepay.inicis.com/pay/card/billing"
BILLING_CHARGE_URL = os.getenv(
    "INICIS_BILLING_CHARGE_URL",
    "https://iniapi.inicis.com/api/v1/billing",
)
REFUND_URL = os.getenv(
    "INICIS_REFUND_URL",
    "https://iniapi.inicis.com/api/v1/refund",
)

# ── Return/Close URL ──────────────────────────────────────────────────
# 결제 페이지(checkout.html)가 api.taieng.co.kr에서 서비스되므로
# returnUrl도 api.taieng.co.kr로 통일 → 도메인 일치
DEFAULT_RETURN_URL = os.getenv(
    "INICIS_DEFAULT_RETURN_URL",
    "https://api.taieng.co.kr/payments/inicis/return",
)
DEFAULT_CLOSE_URL = os.getenv(
    "INICIS_DEFAULT_CLOSE_URL",
    "https://api.taieng.co.kr/payments/result?resultCode=CLOSE",
)
FRONT_RETURN_URL = os.getenv(
    "INICIS_FRONT_RETURN_URL",
    "https://api.taieng.co.kr/payments/result",
)
BILLING_RETURN_URL = os.getenv(
    "INICIS_BILLING_RETURN_URL",
    "https://api.taieng.co.kr/payments/inicis/billing/return",
)

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates", "payment")


@lru_cache(maxsize=8)
def load_template(name: str) -> str:
    path = os.path.join(_TEMPLATE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def sha512(data: str) -> str:
    return hashlib.sha512(data.encode("utf-8")).hexdigest()


def ts_ms() -> str:
    return str(int(time.time() * 1000))


def ts_yyyymmddhhmmss() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def make_order_id() -> str:
    return f"TAI{datetime.now():%Y%m%d%H%M%S}{uuid4().hex[:6].upper()}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def calc_expired_at(paid_at_iso: str, period_months: int) -> str:
    base = datetime.fromisoformat(paid_at_iso.replace("Z", "+00:00"))
    return (base + relativedelta(months=period_months)).isoformat()


def split_supply_vat(total_amount: int) -> tuple[int, int]:
    supply = round(total_amount / 1.1)
    vat = total_amount - supply
    return supply, vat


def service_status_after_card_pay(contract_id: str | None) -> str:
    return "ACTIVE" if contract_id else "PAID"


def decrypt_billkey(encrypted: str, inilite_key: str) -> Optional[str]:
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad

        decoded = unquote(encrypted)
        raw = b64decode(decoded)
        key_bytes = inilite_key.encode("utf-8")[:32].ljust(32, b"\0")
        iv = key_bytes[:16]
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(raw), AES.block_size)
        return decrypted.decode("utf-8")
    except Exception:
        return None


def get_server_ip() -> str:
    return INICIS_CLIENT_IP
