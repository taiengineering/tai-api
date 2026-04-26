"""payment 모듈 순수 유틸·상수 (HTTP·DB 없음).

규칙: docs/DEV_RULES_SERVICE_LAYER.md STEP 1
"""
from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timezone
from typing import List
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


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def ts_ms() -> str:
    return str(int(time.time() * 1000))


def make_order_id() -> str:
    return f"TAI{datetime.now():%Y%m%d%H%M%S}{uuid4().hex[:6].upper()}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def calc_expired_at(paid_at_iso: str, period_months: int) -> str:
    base = datetime.fromisoformat(paid_at_iso.replace("Z", "+00:00"))
    return (base + relativedelta(months=period_months)).isoformat()


def split_supply_vat(total_amount: int) -> tuple[int, int]:
    """부가세 포함 총액 → 공급가액, 부가세 (10%)."""
    supply = round(total_amount / 1.1)
    vat = total_amount - supply
    return supply, vat


def service_status_after_card_pay(contract_id: str | None) -> str:
    """결제 성공 직후 service_status: 계약 연결 시 ACTIVE, 아니면 PAID."""
    return "ACTIVE" if contract_id else "PAID"
