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

from typing import Optional

from pydantic import ValidationError

import services.member_quote_svc as member_quote_svc
from schemas.saas_pricing_v2 import SaasPricingSnapshotV2
from schemas.saas_quote_v2 import SAAS_QUOTE_SCHEMA_VERSION, SaasQuoteSnapshotItemV2
from services.payment_svc import _run_inicis_prepare_exact, load_sign_key


# ── Domain Error ──────────────────────────────────────────────────────────────

class SaasPaymentV2AdapterError(Exception):
    """V2 Payment Adapter 도메인 오류.

    code values:
      QUOTE_NOT_FOUND               — quote_id 미존재
      QUOTE_NOT_OWNED               — company_id 불일치
      QUOTE_NOT_ISSUED              — status_code != ISSUED
      QUOTE_NOT_SAAS                — service_type != SAAS
      QUOTE_NOT_V2                  — items 수 != 1 또는 schema_version != SAAS_QUOTE_V2
      QUOTE_ITEM_INVALID            — SaasQuoteSnapshotItemV2 또는 SaasPricingSnapshotV2 검증 실패
      QUOTE_PAYMENT_SNAPSHOT_INVALID — quote/item/snapshot 금액 3중 불일치
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


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

    # ── Step 10: INICIS Prepare Core 호출 ─────────────────────────────
    sign_key = load_sign_key()
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
