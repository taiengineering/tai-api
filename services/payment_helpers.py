"""payment 모듈 순수 유틸·상수 (HTTP·DB 없음).

규칙: docs/DEV_RULES_SERVICE_LAYER.md STEP 1

v2.1 (2026-04-27)
  [FIX] returnUrl/closeUrl → new.taieng.co.kr/_api 프록시 경유
        이니시스 V023 에러 방지: 결제요청 페이지와 returnUrl 동일 도메인 필수
        Cloudflare Pages Function: functions/_api/[[path]].js → api.taieng.co.kr 프록시

v2.0 (2026-04-27)
  매뉴얼 기반 전면 재정리
"""
from __future__ import annotations

import hashlib
import os
import socket
import time
from base64 import b64decode
from datetime import datetime, timezone
from functools import lru_cache
from typing import List, Optional
from urllib.parse import unquote
from uuid import uuid4

from dateutil.relativedelta import relativedelta

# ── 상품 유형 ──────────────────────────────────────────────────────────

SAAS_PRODUCT_TYPES: List[str] = [
    "SAAS_CONSTRUCTION",
    "SAAS_FACILITY",
    "SAAS_BUILDING",
]

# ── 키 체계 (docs/INICIS_INTEGRATION_SPEC.md §1) ─────────────────────
INICIS_MID = os.getenv("INICIS_MID", "taieng4350")
INICIS_KEY_PATH = os.getenv("INICIS_KEY_PATH", "/app/key/taieng4350")
INICIS_KEY_PASSWORD = os.getenv("INICIS_KEY_PASSWORD", "1111")

INICIS_BILLING_MID = os.getenv("INICIS_BILLING_MID", "")
INICIS_INILITE_KEY = os.getenv("INICIS_INILITE_KEY", "")
INICIS_INIAPI_KEY = os.getenv("INICIS_INIAPI_KEY", "")

# ── API URL ────────────────────────────────────────────────────────────
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
# ⚠️ 이니시스 V023: returnUrl은 결제요청 페이지(new.taieng.co.kr)와 동일 도메인 필수
# Cloudflare Pages Function: new.taieng.co.kr/_api/* → api.taieng.co.kr/* 프록시
DEFAULT_RETURN_URL = os.getenv(
    "INICIS_DEFAULT_RETURN_URL",
    "https://new.taieng.co.kr/_api/payments/inicis/return",
)
DEFAULT_CLOSE_URL = os.getenv(
    "INICIS_DEFAULT_CLOSE_URL",
    "https://new.taieng.co.kr/_api/payments/result?resultCode=CLOSE",
)
# 프론트 결과 페이지 (승인 성공/실패 후 리다이렉트 대상)
FRONT_RETURN_URL = os.getenv(
    "INICIS_FRONT_RETURN_URL",
    "https://new.taieng.co.kr/_api/payments/result",
)
BILLING_RETURN_URL = os.getenv(
    "INICIS_BILLING_RETURN_URL",
    "https://new.taieng.co.kr/_api/payments/inicis/billing/return",
)

# ── 템플릿 ─────────────────────────────────────────────────────────────
_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates", "payment")


@lru_cache(maxsize=8)
def load_template(name: str) -> str:
    """templates/payment/{name} 파일을 읽어 문자열로 반환."""
    path = os.path.join(_TEMPLATE_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ── 해시 유틸 ──────────────────────────────────────────────────────────

def sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def sha512(data: str) -> str:
    return hashlib.sha512(data.encode("utf-8")).hexdigest()


# ── 타임스탬프 ─────────────────────────────────────────────────────────

def ts_ms() -> str:
    return str(int(time.time() * 1000))


def ts_yyyymmddhhmmss() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


# ── 주문번호 ───────────────────────────────────────────────────────────

def make_order_id() -> str:
    return f"TAI{datetime.now():%Y%m%d%H%M%S}{uuid4().hex[:6].upper()}"


# ── 시간 유틸 ──────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def calc_expired_at(paid_at_iso: str, period_months: int) -> str:
    base = datetime.fromisoformat(paid_at_iso.replace("Z", "+00:00"))
    return (base + relativedelta(months=period_months)).isoformat()


# ── 금액 유틸 ──────────────────────────────────────────────────────────

def split_supply_vat(total_amount: int) -> tuple[int, int]:
    supply = round(total_amount / 1.1)
    vat = total_amount - supply
    return supply, vat


# ── 서비스 상태 ────────────────────────────────────────────────────────

def service_status_after_card_pay(contract_id: str | None) -> str:
    return "ACTIVE" if contract_id else "PAID"


# ── AES256 빌링키 복호화 ───────────────────────────────────────────────

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


# ── 서버 IP ────────────────────────────────────────────────────────────

def get_server_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
