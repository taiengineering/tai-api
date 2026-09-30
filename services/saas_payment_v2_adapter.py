"""TAI Safe SaaS Payment V2 Adapter — Quote V2 → Existing INICIS Prepare Core.

역할:
  Quote V2 Frozen Snapshot → 소유권/상태/스키마 검증 → 금액 3중 정합성 → 기존 INICIS Prepare Core 호출

금지:
  - 가격 계산 (add_vat / split_supply_vat / × 0.1 / × 1.1)
  - Server Repricing (price_master / pricing_resolver / pricing_composer / preview)
  - Client 금액 입력 신뢰
  - Contract / Commercial V2 / Subscription 생성
  - Runtime endpoint 노출 (routers/* import 0)
  - Production DB Mutation (Fake Supabase 전용 검증)

Payment Amount SSOT: Frozen Quote V2 Snapshot (quotes.items[0].pricing_snapshot)
"""
from __future__ import annotations

import logging
from typing import Optional

from pydantic import ValidationError

import services.member_quote_svc as member_quote_svc
from schemas.saas_pricing_v2 import SaasPricingSnapshotV2
from schemas.saas_quote_v2 import SAAS_QUOTE_SCHEMA_VERSION, SaasQuoteSnapshotItemV2
from services.payment_svc import (
    _build_inicis_prepare_response_exact,
    _run_inicis_prepare_exact,
    load_sign_key,
)

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = ("PENDING", "PAID", "SUCCESS")
_PAID_STATUSES = ("PAID", "SUCCESS")


# ── Domain Error ──────────────────────────────────────────────────────────────

class SaasPaymentV2AdapterError(Exception):
    """V2 Payment Adapter 도메인 오류.

    code values:
      QUOTE_NOT_FOUND                — quote_id 미존재
      QUOTE_NOT_OWNED                — company_id 불일치
      QUOTE_NOT_ISSUED               — status_code != ISSUED
      QUOTE_NOT_SAAS                 — service_type != SAAS
      QUOTE_NOT_V2                   — items 수 != 1 또는 schema_version != SAAS_QUOTE_V2
      QUOTE_ITEM_INVALID             — SaasQuoteSnapshotItemV2 또는 SaasPricingSnapshotV2 검증 실패
      QUOTE_PAYMENT_SNAPSHOT_INVALID — quote/item/snapshot 금액 3중 불일치
      QUOTE_PAYMENT_PENDING          — 다른 사용자의 PENDING 결제 존재
      QUOTE_ALREADY_PAID             — PAID/SUCCESS 결제 이미 존재
      QUOTE_PAYMENT_STATE_CONFLICT   — 경쟁 삽입 후 재조회 불일치
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# ── Guard Helpers ─────────────────────────────────────────────────────────────

_V2_PAYMENT_SELECT = (
    "id,user_id,company_id,quote_id,status_code,inicis_order_id,"
    "product_type,payment_type,plan_code,period_months,"
    "supply_amount,vat_amount,total_amount"
)


def _find_existing_v2_payment(supabase, quote_id: str) -> Optional[dict]:
    """PENDING/PAID/SUCCESS 상태인 기존 V2 결제 행 조회 (최신 1건).

    FAILED-only 상태이거나 결제 이력 없으면 None 반환.
    goodname/buyername/buyertel/buyeremail은 payments 컬럼이 아님 — SELECT 금지.
    """
    res = (
        supabase.table("payments")
        .select(_V2_PAYMENT_SELECT)
        .eq("quote_id", quote_id)
        .eq("product_type", "SAAS")
        .eq("payment_type", "CARD")
        .in_("status_code", list(_ACTIVE_STATUSES))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def _validate_pending_reuse(
    existing: dict,
    user_id: str,
    company_id: str,
    quote_id: str,
    snap: SaasPricingSnapshotV2,
    sign_key: str,
    goodname: str,
    *,
    buyername: Optional[str] = None,
    buyertel: Optional[str] = None,
    buyeremail: Optional[str] = None,
) -> dict:
    """기존 결제 행 분기: PAID/SUCCESS → ALREADY_PAID, other-user PENDING → PENDING,
    same-user PENDING → 9-field state contract 검증 후 reuse 응답.

    goodname: Frozen Quote item.display_name (DB row에서 읽지 않음).
    buyername/buyertel/buyeremail: 현재 request 값 (DB row에서 읽지 않음).
    """
    status = (existing.get("status_code") or "").upper()
    if status in _PAID_STATUSES:
        raise SaasPaymentV2AdapterError("QUOTE_ALREADY_PAID", "이미 결제 완료된 견적입니다.")

    # PENDING: other-user check — provider fields 노출 0
    if str(existing.get("user_id")) != str(user_id):
        raise SaasPaymentV2AdapterError("QUOTE_PAYMENT_PENDING", "이 견적에 대해 진행 중인 결제가 있습니다.")

    # Same-user PENDING: 9-field state contract
    def _conflict(reason: str) -> SaasPaymentV2AdapterError:
        logger.warning("[V2_ADAPTER] PENDING state conflict: %s payment=%s", reason, existing.get("id"))
        return SaasPaymentV2AdapterError("QUOTE_PAYMENT_STATE_CONFLICT", f"PENDING 결제 상태 불일치: {reason}")

    if str(existing.get("company_id")) != str(company_id):
        raise _conflict("company_id")
    if str(existing.get("quote_id")) != str(quote_id):
        raise _conflict("quote_id")
    if existing.get("product_type") != "SAAS":
        raise _conflict("product_type")
    if existing.get("payment_type") != "CARD":
        raise _conflict("payment_type")
    if existing.get("plan_code") is not None:
        raise _conflict("plan_code non-null")
    if int(existing.get("period_months") or 0) != snap.payment_months:
        raise _conflict("period_months")
    if int(existing.get("supply_amount") or 0) != snap.prepaid_supply_amount:
        raise _conflict("supply_amount")
    if int(existing.get("vat_amount") or 0) != snap.vat_amount:
        raise _conflict("vat_amount")
    if int(existing.get("total_amount") or 0) != snap.total_amount:
        raise _conflict("total_amount")

    payment_id = str(existing.get("id") or "")
    order_id = str(existing.get("inicis_order_id") or "")
    if not payment_id or not order_id:
        raise _conflict("missing payment_id or inicis_order_id")

    logger.info("[V2_ADAPTER] quote=%s user=%s PENDING reuse payment=%s", quote_id, user_id, payment_id)
    return _build_inicis_prepare_response_exact(
        sign_key,
        payment_id=payment_id,
        order_id=order_id,
        total_amount=snap.total_amount,
        goodname=goodname,
        buyername=buyername,
        buyertel=buyertel,
        buyeremail=buyeremail,
    )


def _is_quote_v2_unique_violation(exc: Exception) -> bool:
    """PostgreSQL 23505 unique violation이 uix_payments_quote_v2_initial_active 인지 판정."""
    msg = str(exc)
    return "23505" in msg and "uix_payments_quote_v2_initial_active" in msg


def _handle_race_recovery(
    supabase,
    quote_id: str,
    user_id: str,
    company_id: str,
    snap: SaasPricingSnapshotV2,
    sign_key: str,
    goodname: str,
    *,
    buyername: Optional[str] = None,
    buyertel: Optional[str] = None,
    buyeremail: Optional[str] = None,
) -> dict:
    """경쟁 INSERT 실패(23505) 후 재조회 → 동일 라우팅 적용."""
    existing = _find_existing_v2_payment(supabase, quote_id)
    if not existing:
        raise SaasPaymentV2AdapterError(
            "QUOTE_PAYMENT_STATE_CONFLICT",
            "결제 중복 감지 후 기존 결제를 확인할 수 없습니다.",
        )
    return _validate_pending_reuse(
        existing, user_id, company_id, quote_id, snap, sign_key, goodname,
        buyername=buyername, buyertel=buyertel, buyeremail=buyeremail,
    )


# ── Entry Point ───────────────────────────────────────────────────────────────

def prepare_saas_v2_payment_from_quote(
    supabase,
    quote_id: str,
    user_id: str,
    company_id: str,
    *,
    proof_type: Optional[str] = None,
    buyername: Optional[str] = None,
    buyertel: Optional[str] = None,
    buyeremail: Optional[str] = None,
) -> dict:
    """Quote V2 기반 INICIS 결제 준비.

    DB Read: quotes (via get_member_quote)
    DB Write: payments (1 row, via _run_inicis_prepare_exact)
    Contract: 0. Commercial V2: 0. Subscription: 0.
    """
    # ── Step 1: Quote 조회 ────────────────────────────────────────────
    quote = member_quote_svc.get_member_quote(supabase, quote_id)
    if not quote:
        raise SaasPaymentV2AdapterError(
            "QUOTE_NOT_FOUND",
            "견적을 찾을 수 없습니다.",
        )

    # ── Step 2: 소유권 ────────────────────────────────────────────────
    if str(quote.get("company_id")) != str(company_id):
        raise SaasPaymentV2AdapterError(
            "QUOTE_NOT_OWNED",
            "견적 소유권이 없습니다.",
        )

    # ── Step 3: 발행 상태 ─────────────────────────────────────────────
    if quote.get("status_code") != "ISSUED":
        raise SaasPaymentV2AdapterError(
            "QUOTE_NOT_ISSUED",
            "발행(ISSUED) 상태 견적만 결제할 수 있습니다.",
        )

    # ── Step 4: SAAS 서비스 ───────────────────────────────────────────
    if quote.get("service_type") != "SAAS":
        raise SaasPaymentV2AdapterError(
            "QUOTE_NOT_SAAS",
            "SaaS 견적만 이 경로로 결제할 수 있습니다.",
        )

    # ── Step 5: Item 수 ───────────────────────────────────────────────
    items = quote.get("items") or []
    if len(items) != 1:
        raise SaasPaymentV2AdapterError(
            "QUOTE_NOT_V2",
            f"V2 견적은 정확히 1개의 item을 가져야 합니다. (실제: {len(items)})",
        )

    # ── Step 6: Schema Version ────────────────────────────────────────
    raw_item = items[0]
    if raw_item.get("quote_schema_version") != SAAS_QUOTE_SCHEMA_VERSION:
        raise SaasPaymentV2AdapterError(
            "QUOTE_NOT_V2",
            f"SAAS_QUOTE_V2 스키마가 아닙니다: {raw_item.get('quote_schema_version')}",
        )

    # ── Step 7: Item typed validation ────────────────────────────────
    try:
        item = SaasQuoteSnapshotItemV2.model_validate(raw_item)
    except (ValidationError, Exception) as exc:
        raise SaasPaymentV2AdapterError("QUOTE_ITEM_INVALID", str(exc)) from exc

    # ── Step 8: Pricing Snapshot typed validation ─────────────────────
    try:
        snap = SaasPricingSnapshotV2.model_validate(item.pricing_snapshot)
    except (ValidationError, Exception) as exc:
        raise SaasPaymentV2AdapterError("QUOTE_ITEM_INVALID", str(exc)) from exc

    # ── Step 9: 금액 3중 정합성 ──────────────────────────────────────
    q_supply = int(quote.get("supply_amount") or 0)
    q_vat = int(quote.get("vat_amount") or 0)
    q_total = int(quote.get("total_amount") or 0)

    if q_supply != item.supply_amount or item.supply_amount != snap.prepaid_supply_amount:
        raise SaasPaymentV2AdapterError(
            "QUOTE_PAYMENT_SNAPSHOT_INVALID",
            f"supply_amount 불일치: quote={q_supply}, item={item.supply_amount}, snap={snap.prepaid_supply_amount}",
        )
    if q_vat != item.vat_amount or item.vat_amount != snap.vat_amount:
        raise SaasPaymentV2AdapterError(
            "QUOTE_PAYMENT_SNAPSHOT_INVALID",
            f"vat_amount 불일치: quote={q_vat}, item={item.vat_amount}, snap={snap.vat_amount}",
        )
    if q_total != item.total_amount or item.total_amount != snap.total_amount:
        raise SaasPaymentV2AdapterError(
            "QUOTE_PAYMENT_SNAPSHOT_INVALID",
            f"total_amount 불일치: quote={q_total}, item={item.total_amount}, snap={snap.total_amount}",
        )

    sign_key = load_sign_key()

    # ── Step 10: Duplicate Guard ──────────────────────────────────────
    existing = _find_existing_v2_payment(supabase, quote_id)
    if existing:
        return _validate_pending_reuse(
            existing, user_id, company_id, quote_id, snap, sign_key, item.display_name,
            buyername=buyername, buyertel=buyertel, buyeremail=buyeremail,
        )

    # ── Step 11: INICIS Prepare Core 호출 ────────────────────────────
    try:
        return _run_inicis_prepare_exact(
            supabase,
            sign_key,
            supply_amount=snap.prepaid_supply_amount,
            vat_amount=snap.vat_amount,
            total_amount=snap.total_amount,
            product_type="SAAS",
            goodname=item.display_name,
            user_id=user_id,
            company_id=company_id,
            quote_id=quote_id,
            plan_code=None,
            period_months=snap.payment_months,
            payment_type="CARD",
            proof_type=proof_type,
            buyername=buyername,
            buyertel=buyertel,
            buyeremail=buyeremail,
        )
    except Exception as exc:
        if _is_quote_v2_unique_violation(exc):
            logger.info("[V2_ADAPTER] quote=%s race-INSERT 23505 → recovery", quote_id)
            return _handle_race_recovery(
                supabase, quote_id, user_id, company_id, snap, sign_key, item.display_name,
                buyername=buyername, buyertel=buyertel, buyeremail=buyeremail,
            )
        raise
