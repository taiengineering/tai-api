"""Renewal Payment 중복 결제 방어 — 서비스 레벨 guard.

DDL 인덱스(uix_payments_quote_v3_renewal_active) 적용 전까지
Python 레벨에서 same-quote RENEWAL payment 중복을 차단한다.

패턴: saas_payment_v2_adapter._find_existing_v2_payment / _validate_pending_reuse 재활용.
"""
from __future__ import annotations
import logging
from typing import Optional

log = logging.getLogger(__name__)

_ACTIVE_STATUSES = frozenset({"PENDING", "PAID", "SUCCESS"})
_PAID_STATUSES = frozenset({"PAID", "SUCCESS"})
_RENEWAL_SELECT = (
    "id,user_id,company_id,quote_id,product_type,payment_type,"
    "status_code,total_amount,period_months,inicis_order_id,created_at"
)


class RenewalPaymentGuardError(Exception):
    def __init__(self, code: str, message: str = "", http_status: int = 422) -> None:
        self.code = code
        self.message = message or code
        self.http_status = http_status
        super().__init__(self.message)


def _find_existing_renewal_payment(supabase, quote_id: str) -> Optional[dict]:
    """PENDING/PAID/SUCCESS 상태인 기존 RENEWAL 결제 행 조회 (최신 1건)."""
    res = (
        supabase.table("payments")
        .select(_RENEWAL_SELECT)
        .eq("quote_id", quote_id)
        .eq("product_type", "SAAS")
        .eq("payment_type", "RENEWAL")
        .in_("status_code", list(_ACTIVE_STATUSES))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def check_existing_renewal_payment(
    supabase,
    *,
    quote_id: str,
    company_id: str,
    user_id: str,
) -> None:
    """기존 RENEWAL 결제 상태 검사.

    Returns: None — 신규 결제 진행 가능

    Raises:
      RenewalPaymentGuardError:
        QUOTE_ALREADY_PAID    — 이미 결제 완료
        QUOTE_PAYMENT_PENDING — 결제 진행 중 (동일/다른 사용자 모두 409)
        QUOTE_PAYMENT_STATE_CONFLICT — 상태 불일치
    """
    existing = _find_existing_renewal_payment(supabase, quote_id)
    if not existing:
        return None  # 신규 진행 가능

    status = (existing.get("status_code") or "").upper()

    if status in _PAID_STATUSES:
        raise RenewalPaymentGuardError(
            "QUOTE_ALREADY_PAID", "이미 결제 완료된 견적입니다.", 409
        )

    if status == "PENDING":
        log.info(
            "[RENEWAL_GUARD] quote=%s PENDING — blocking new attempt (user=%s existing_user=%s)",
            quote_id, user_id, existing.get("user_id"),
        )
        raise RenewalPaymentGuardError(
            "QUOTE_PAYMENT_PENDING", "이 견적에 대해 진행 중인 결제가 있습니다.", 409
        )

    raise RenewalPaymentGuardError(
        "QUOTE_PAYMENT_STATE_CONFLICT", "결제 상태 불일치.", 409
    )


def is_renewal_unique_violation(exc: Exception) -> bool:
    """PostgreSQL 23505 unique violation이 uix_payments_quote_v3_renewal_active인지 판정."""
    msg = str(exc)
    return "23505" in msg and "uix_payments_quote_v3_renewal_active" in msg
