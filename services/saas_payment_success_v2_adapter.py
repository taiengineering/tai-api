"""TAI Safe SaaS Payment Success V2 Adapter — Frozen Quote Snapshot → Contract Row Builder.

역할:
  V2 결제 성공 후 pay dict + Frozen Quote V2 Snapshot 을 받아
  contracts INSERT row 와 Commercial Storage Bundle 을 순수하게 조립한다.

금지:
  - DB I/O (contracts 0 · commercial_versions 0 · site_scopes 0 · subscriptions 0)
  - Server Repricing (price engine 0)
  - Client 금액 신뢰 (pay.amount 재신뢰 0 — Frozen Snapshot SSOT)
  - plan_code legacy fallback (V2 plan_code = None)
  - Runtime endpoint 노출 (router import 0)

Payment Success Amount SSOT: Frozen Quote V2 Snapshot
  pay.supply_amount == item.supply_amount == snapshot.prepaid_supply_amount
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from dateutil import parser as dateutil_parser
from pydantic import ValidationError

from schemas.saas_contract_commercial_v2 import SaasContractStorageBundleV2
from schemas.saas_pricing_v2 import SaasCommercialSelection, SaasPricingSnapshotV2
from schemas.saas_quote_v2 import SAAS_QUOTE_SCHEMA_VERSION, SaasQuoteSnapshotItemV2
from services.payment_post_process import (
    PAID_STATUS_CODES,
    _build_contract_row_from_payment,
)
from services.saas_contract_storage_mapper_v2 import build_standard_contract_storage_bundle_v2
from services.saas_pricing_composer_v2 import SaasPricingCalculationResult


# ── Domain Error ──────────────────────────────────────────────────────────────

class SaasPaymentSuccessV2AdapterError(Exception):
    """V2 Payment Success Adapter 도메인 오류.

    code values:
      V2_PAYMENT_NOT_PAID          — status_code ∉ {PAID, SUCCESS}
      V2_LEGACY_PLAN_CODE_FORBIDDEN — pay.plan_code != None
      V2_PAID_AT_REQUIRED          — pay.paid_at 없음
      V2_PAID_AT_INVALID           — paid_at 파싱 실패 또는 naive datetime
      V2_USER_REQUIRED             — pay.user_id 없음
      V2_USER_INVALID              — pay.user_id 유효 UUID 아님
      V2_QUOTE_SOURCE_INVALID      — quote.source != "member_auto"
      V2_QUOTE_SERVICE_INVALID     — quote.service_type != "SAAS"
      PAY_NOT_SAAS_V2              — product_type != "SAAS"
      PAY_NO_COMPANY_ID            — pay.company_id 없음
      PAY_QUOTE_COMPANY_MISMATCH   — pay.company_id != quote.company_id
      QUOTE_NOT_ISSUED             — quote.status_code != "ISSUED"
      PAY_NO_QUOTE_ID              — pay.quote_id 없음
      PAY_QUOTE_ID_MISMATCH        — pay.quote_id != quote.id
      QUOTE_ITEM_COUNT_INVALID     — items 수 != 1
      QUOTE_NOT_V2                 — quote_schema_version != SAAS_QUOTE_V2
      QUOTE_ITEM_INVALID           — SaasQuoteSnapshotItemV2 검증 실패
      QUOTE_SNAPSHOT_INVALID       — SaasPricingSnapshotV2 검증 실패
      AMOUNT_SNAPSHOT_MISMATCH     — pay/item/snapshot 금액 3중 불일치
      PAY_PERIOD_TERM_MISMATCH     — pay.period_months != snapshot.payment_months
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# ── Apply Plan ────────────────────────────────────────────────────────────────

@dataclass
class SaasV2ApplyPlan:
    """순수 계약 조립 플랜 — DB write = 0.

    원자적 저장은 별도 WO(BE-OBJ10-C)에서 처리한다.
    Fields:
      payment_id        — pay.id
      company_id        — pay.company_id
      contract_id       — 사전 생성 UUID (contracts + commercial_versions INSERT 동기화용)
      contract_row      — contracts INSERT 직접 사용 가능 (id 포함)
      commercial_bundle — saas_contract_commercial_versions + saas_contract_site_scopes INSERT용
    """
    payment_id: str
    company_id: str
    contract_id: uuid.UUID
    contract_row: dict
    commercial_bundle: SaasContractStorageBundleV2


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _parse_paid_at(paid_at_str: str) -> datetime:
    """ISO 8601 timezone-aware datetime 파싱. naive 불허."""
    try:
        dt = dateutil_parser.isoparse(paid_at_str)
    except (ValueError, TypeError) as exc:
        raise SaasPaymentSuccessV2AdapterError(
            "V2_PAID_AT_INVALID",
            f"paid_at ISO 파싱 실패: {paid_at_str!r}",
        ) from exc
    if dt.tzinfo is None:
        raise SaasPaymentSuccessV2AdapterError(
            "V2_PAID_AT_INVALID",
            f"paid_at timezone-aware 필수 (naive 불허): {paid_at_str!r}",
        )
    return dt


def _frozen_snapshot_to_calc_result(snap: SaasPricingSnapshotV2) -> SaasPricingCalculationResult:
    """Frozen Snapshot → status=READY SaasPricingCalculationResult. Repricing 없음."""
    return SaasPricingCalculationResult(
        status="READY",
        policy_version=snap.policy_version,
        site_breakdown=None,
        worker_breakdown=snap.worker,
        monthly_supply_amount=snap.monthly_supply_amount,
        raw_prepaid_supply_amount=snap.prepaid_supply_amount,
        payment_months=snap.payment_months,
        term_discount_rate_bps=snap.term_discount_rate_bps,
        snapshot=snap,
        block_reason=None,
    )


# ── Entry Point ───────────────────────────────────────────────────────────────

def build_saas_v2_payment_success_apply_plan(
    pay: dict,
    *,
    quote: dict,
    start: date,
    contract_no: str,
    contract_id_override: Optional[uuid.UUID] = None,
) -> SaasV2ApplyPlan:
    """Frozen Quote V2 Snapshot → Contract Row + Commercial Bundle (pure, DB write = 0).

    DB Read: 0 (caller가 사전 조회한 pay / quote 전달)
    DB Write: 0 (plans만 조립)
    contracts INSERT: 0 (BE-OBJ10-C에서 원자적 처리)

    Args:
      pay                  — payments 행 (product_type="SAAS", status_code∈{PAID,SUCCESS})
      quote                — get_member_quote 반환값 (source=member_auto, service_type=SAAS)
      start                — 계약 시작일 (결정성 테스트 지원)
      contract_no          — 계약번호 (결정성 테스트 지원)
      contract_id_override — 재사용할 UUID (Replay/Race-recovery 용). None이면 uuid4() 신규 생성.
    """
    # ── Step 1: Payment 성공 상태 가드 ───────────────────────────────────
    status_code = pay.get("status_code") or ""
    if status_code not in PAID_STATUS_CODES:
        raise SaasPaymentSuccessV2AdapterError(
            "V2_PAYMENT_NOT_PAID",
            f"결제 성공 상태(PAID/SUCCESS)만 처리합니다: {status_code!r}",
        )

    # ── Step 2: Legacy plan_code 금지 가드 ───────────────────────────────
    if pay.get("plan_code") is not None:
        raise SaasPaymentSuccessV2AdapterError(
            "V2_LEGACY_PLAN_CODE_FORBIDDEN",
            f"V2 결제는 plan_code=None이어야 합니다: {pay.get('plan_code')!r}",
        )

    # ── Step 3-4: paid_at 필수 + 파싱 ───────────────────────────────────
    if not pay.get("paid_at"):
        raise SaasPaymentSuccessV2AdapterError(
            "V2_PAID_AT_REQUIRED", "결제 성공 시각(paid_at)이 필수입니다."
        )
    paid_at_dt = _parse_paid_at(str(pay["paid_at"]))

    # ── Step 5-6: user_id 필수 + UUID 검증 ──────────────────────────────
    if not pay.get("user_id"):
        raise SaasPaymentSuccessV2AdapterError(
            "V2_USER_REQUIRED", "결제자(user_id)가 필수입니다."
        )
    try:
        user_uuid = uuid.UUID(str(pay["user_id"]))
    except (ValueError, AttributeError) as exc:
        raise SaasPaymentSuccessV2AdapterError(
            "V2_USER_INVALID",
            f"user_id가 유효한 UUID가 아닙니다: {pay.get('user_id')!r}",
        ) from exc

    # ── Step 7: product_type 가드 ─────────────────────────────────────
    if pay.get("product_type") != "SAAS":
        raise SaasPaymentSuccessV2AdapterError(
            "PAY_NOT_SAAS_V2",
            f"product_type=SAAS 결제만 처리합니다: {pay.get('product_type')!r}",
        )

    # ── Step 8: company_id 존재 + pay/quote 일치 ──────────────────────
    pay_company = str(pay.get("company_id") or "")
    quote_company = str(quote.get("company_id") or "")
    if not pay_company:
        raise SaasPaymentSuccessV2AdapterError(
            "PAY_NO_COMPANY_ID", "company_id 없는 결제입니다."
        )
    if pay_company != quote_company:
        raise SaasPaymentSuccessV2AdapterError(
            "PAY_QUOTE_COMPANY_MISMATCH",
            f"pay.company_id={pay_company} != quote.company_id={quote_company}",
        )

    # ── Step 9: quote source 가드 ────────────────────────────────────
    if quote.get("source") != "member_auto":
        raise SaasPaymentSuccessV2AdapterError(
            "V2_QUOTE_SOURCE_INVALID",
            f"source=member_auto 견적만 자동 결제 성공 계약 대상입니다: {quote.get('source')!r}",
        )

    # ── Step 10: quote service_type 가드 ─────────────────────────────
    if quote.get("service_type") != "SAAS":
        raise SaasPaymentSuccessV2AdapterError(
            "V2_QUOTE_SERVICE_INVALID",
            f"service_type=SAAS 견적만 처리합니다: {quote.get('service_type')!r}",
        )

    # ── Step 11: quote 발행 상태 ─────────────────────────────────────
    if quote.get("status_code") != "ISSUED":
        raise SaasPaymentSuccessV2AdapterError(
            "QUOTE_NOT_ISSUED",
            f"ISSUED 상태 견적만 처리합니다: {quote.get('status_code')!r}",
        )

    # ── Step 12: pay.quote_id 연결 ───────────────────────────────────
    if not pay.get("quote_id"):
        raise SaasPaymentSuccessV2AdapterError(
            "PAY_NO_QUOTE_ID", "V2 결제는 quote_id 필수입니다."
        )
    if str(pay.get("quote_id")) != str(quote.get("id")):
        raise SaasPaymentSuccessV2AdapterError(
            "PAY_QUOTE_ID_MISMATCH",
            f"pay.quote_id={pay.get('quote_id')} != quote.id={quote.get('id')}",
        )

    # ── Step 13: items 추출 ──────────────────────────────────────────
    items = quote.get("items") or []
    if len(items) != 1:
        raise SaasPaymentSuccessV2AdapterError(
            "QUOTE_ITEM_COUNT_INVALID",
            f"V2 견적은 item 1개여야 합니다. (실제: {len(items)})",
        )
    raw_item = items[0]
    if raw_item.get("quote_schema_version") != SAAS_QUOTE_SCHEMA_VERSION:
        raise SaasPaymentSuccessV2AdapterError(
            "QUOTE_NOT_V2",
            f"SAAS_QUOTE_V2 스키마 아님: {raw_item.get('quote_schema_version')!r}",
        )

    # ── Step 14: Item typed validation ───────────────────────────────
    try:
        item = SaasQuoteSnapshotItemV2.model_validate(raw_item)
    except (ValidationError, Exception) as exc:
        raise SaasPaymentSuccessV2AdapterError("QUOTE_ITEM_INVALID", str(exc)) from exc

    # ── Step 15: Pricing Snapshot typed validation ────────────────────
    try:
        snap = SaasPricingSnapshotV2.model_validate(item.pricing_snapshot)
    except (ValidationError, Exception) as exc:
        raise SaasPaymentSuccessV2AdapterError("QUOTE_SNAPSHOT_INVALID", str(exc)) from exc

    # ── Step 16: 금액 3중 정합성 (pay ↔ item ↔ snapshot) ─────────────
    p_supply = int(pay.get("supply_amount") or 0)
    p_vat = int(pay.get("vat_amount") or 0)
    p_total = int(pay.get("total_amount") or 0)

    if p_supply != item.supply_amount or item.supply_amount != snap.prepaid_supply_amount:
        raise SaasPaymentSuccessV2AdapterError(
            "AMOUNT_SNAPSHOT_MISMATCH",
            f"supply_amount 불일치: pay={p_supply}, item={item.supply_amount}, snap={snap.prepaid_supply_amount}",
        )
    if p_vat != item.vat_amount or item.vat_amount != snap.vat_amount:
        raise SaasPaymentSuccessV2AdapterError(
            "AMOUNT_SNAPSHOT_MISMATCH",
            f"vat_amount 불일치: pay={p_vat}, item={item.vat_amount}, snap={snap.vat_amount}",
        )
    if p_total != item.total_amount or item.total_amount != snap.total_amount:
        raise SaasPaymentSuccessV2AdapterError(
            "AMOUNT_SNAPSHOT_MISMATCH",
            f"total_amount 불일치: pay={p_total}, item={item.total_amount}, snap={snap.total_amount}",
        )

    # ── Step 17: period_months ↔ payment_months 정합성 ───────────────────
    pay_period = int(pay.get("period_months") or 0)
    if pay_period != snap.payment_months:
        raise SaasPaymentSuccessV2AdapterError(
            "PAY_PERIOD_TERM_MISMATCH",
            f"pay.period_months={pay_period} != snapshot.payment_months={snap.payment_months}",
        )

    # ── Step 18: contract_row 조립 (plan_code=None — V2 sentinel) ────
    contract_id = contract_id_override if contract_id_override is not None else uuid.uuid4()
    contract_row = _build_contract_row_from_payment(
        pay,
        start=start,
        contract_no=contract_no,
        plan_code_override=None,
    )
    contract_row["id"] = str(contract_id)

    # ── Step 19: Commercial Bundle 조립 ──────────────────────────────
    # effective_from = actual payment.paid_at (결제 성공 시각)
    # created_by     = payment.user_id
    selection = SaasCommercialSelection(
        product_tier=snap.product_tier,
        pricing_mode=snap.pricing_mode,
        worker_capacity=snap.worker.capacity,
        payment_months=snap.payment_months,
    )
    calc = _frozen_snapshot_to_calc_result(snap)
    commercial_bundle = build_standard_contract_storage_bundle_v2(
        contract_id=contract_id,
        version_no=1,
        selection=selection,
        calculation_result=calc,
        effective_from=paid_at_dt,
        created_by=user_uuid,
    )

    return SaasV2ApplyPlan(
        payment_id=str(pay.get("id") or ""),
        company_id=pay_company,
        contract_id=contract_id,
        contract_row=contract_row,
        commercial_bundle=commercial_bundle,
    )
