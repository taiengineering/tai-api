"""TAI Safe SaaS Renewal V2 Adapter — V2 Prepaid Renewal Payment Prepare + Plan Builder.

역할:
  기존 V2 Contract에 대해 Renewal Quote Frozen Snapshot을 검증하고
  INICIS Prepaid 결제 준비(payment_type="RENEWAL") + 순수 Renewal Plan을 조립한다.

Billing Boundary FREEZE:
  이 모듈은 Prepaid Renewal 경계(한 번의 선불 결제)만 담당한다.
  아래 항목은 이 경계 밖이며 이 모듈에서 절대 다루지 않는다:
    - subscriptions 테이블 생성 / 조회 / 변경
    - billing_keys 테이블 생성 / 조회 / 변경
    - 자동 반복 청구 (auto-recurring / CardBilling / BillKey)
    - 재과금 로직 (re-billing / retry)

금지:
  - Server Repricing (price engine 0)
  - Client 금액 신뢰 (Frozen Snapshot SSOT)
  - contract_id = None 결제 (기존 계약 필수)
  - V2 신규 계약 생성 경로 혼용
  - datetime.now() 직접 호출
  - contracts / saas_contract_commercial_versions / saas_contract_site_scopes mutation
  - Router wiring

Payment Amount SSOT: Frozen Quote V2 Snapshot (quotes.items[0].pricing_snapshot)
requested_effective_at SSOT: caller 입력 (Owner Gate 결정, paid_at 아님)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from dateutil import parser as dateutil_parser
from pydantic import ValidationError

import services.member_quote_svc as member_quote_svc
from schemas.saas_contract_commercial_v2 import (
    COMMERCIAL_STORAGE_SCHEMA_VERSION,
    SaasContractCommercialVersionV2,
    SaasContractSiteScopeV2,
    SaasContractStorageBundleV2,
)
from schemas.saas_pricing_v2 import SaasCommercialSelection, SaasPricingSnapshotV2
from schemas.saas_quote_v2 import SAAS_QUOTE_SCHEMA_VERSION, SaasQuoteSnapshotItemV2
from services.payment_post_process import PAID_STATUS_CODES
from services.payment_svc import _run_inicis_prepare_exact, load_sign_key
from services.saas_contract_storage_mapper_v2 import build_standard_contract_storage_bundle_v2
from services.saas_payment_success_v2_adapter import _frozen_snapshot_to_calc_result


# ── Domain Error ──────────────────────────────────────────────────────────────

class SaasRenewalV2AdapterError(Exception):
    """V2 Renewal Adapter 도메인 오류.

    code values:
      CONTRACT_NOT_FOUND                — contract_id 미존재
      CONTRACT_NOT_OWNED                — contracts.company_id != company_id
      CONTRACT_NOT_ACTIVE               — contracts.status_code != ACTIVE
      CURRENT_CV_NOT_FOUND              — 현재 유효 CV 없음 (superseded_at IS NULL 행 0)
      QUOTE_NOT_FOUND                   — quote_id 미존재
      QUOTE_NOT_OWNED                   — quote.company_id != company_id
      QUOTE_NOT_ISSUED                  — quote.status_code != ISSUED
      QUOTE_NOT_SAAS                    — quote.service_type != SAAS
      QUOTE_NOT_V2                      — items 수 != 1 또는 schema_version != SAAS_QUOTE_V2
      QUOTE_ITEM_INVALID                — SaasQuoteSnapshotItemV2 또는 SaasPricingSnapshotV2 검증 실패
      QUOTE_PAYMENT_SNAPSHOT_INVALID    — quote/item/snapshot 금액 3중 불일치
      RENEWAL_PAYMENT_NOT_PAID          — status_code ∉ {PAID, SUCCESS}
      RENEWAL_LEGACY_PLAN_CODE_FORBIDDEN — pay.plan_code != None
      RENEWAL_PAID_AT_REQUIRED          — pay.paid_at 없음
      RENEWAL_PAID_AT_INVALID           — paid_at 파싱 실패 또는 naive datetime
      RENEWAL_USER_REQUIRED             — pay.user_id 없음
      RENEWAL_USER_INVALID              — pay.user_id 유효 UUID 아님
      RENEWAL_PAY_NOT_SAAS              — product_type != SAAS
      RENEWAL_CONTRACT_ID_REQUIRED      — pay.contract_id 없음 (renewal은 기존 계약 필수)
      RENEWAL_CONTRACT_ID_MISMATCH      — pay.contract_id != contract_id
      RENEWAL_PAYMENT_TYPE_INVALID      — pay.payment_type != RENEWAL
      RENEWAL_PERIOD_TERM_MISMATCH      — pay.period_months != snapshot.term_months
    """

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# ── Apply Plan ────────────────────────────────────────────────────────────────

@dataclass
class SaasV2RenewalApplyPlan:
    """순수 Renewal 계약 조립 플랜 — DB write = 0.

    원자적 갱신 적용은 별도 WO(BE-OBJ10-D-B)에서 처리한다.
    Fields:
      payment_id             — pay.id
      company_id             — pay.company_id
      contract_id            — 기존 계약 UUID (신규 생성 아님)
      next_version_no        — current_cv.version_no + 1
      requested_effective_at — 갱신 적용 기준 시각 (caller 입력, Owner Gate 결정)
      commercial_bundle      — 새 CV + 새 site_scopes (version_no=next_version_no)
    """
    payment_id: str
    company_id: str
    contract_id: uuid.UUID
    next_version_no: int
    requested_effective_at: datetime
    commercial_bundle: SaasContractStorageBundleV2


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _parse_paid_at(paid_at_str: str) -> datetime:
    try:
        dt = dateutil_parser.isoparse(paid_at_str)
    except (ValueError, TypeError) as exc:
        raise SaasRenewalV2AdapterError(
            "RENEWAL_PAID_AT_INVALID",
            f"paid_at ISO 파싱 실패: {paid_at_str!r}",
        ) from exc
    if dt.tzinfo is None:
        raise SaasRenewalV2AdapterError(
            "RENEWAL_PAID_AT_INVALID",
            f"paid_at timezone-aware 필수 (naive 불허): {paid_at_str!r}",
        )
    return dt


def _fetch_current_contract_bundle(
    supabase,
    contract_id: str,
    company_id: str,
) -> tuple[dict, dict, list]:
    """DB에서 현재 Contract + 현재 CV + Site Scopes를 조회.

    Returns: (contract_row, cv_row, scope_rows)
    """
    # ── Contract 조회 ─────────────────────────────────────────────────
    ct_res = (
        supabase.table("contracts")
        .select("id, company_id, status_code")
        .eq("id", contract_id)
        .limit(1)
        .execute()
    )
    if not ct_res.data:
        raise SaasRenewalV2AdapterError(
            "CONTRACT_NOT_FOUND",
            f"contract_id={contract_id} 계약을 찾을 수 없습니다.",
        )
    contract = ct_res.data[0]

    if str(contract.get("company_id")) != str(company_id):
        raise SaasRenewalV2AdapterError(
            "CONTRACT_NOT_OWNED",
            f"contract_id={contract_id} 계약 소유권이 없습니다.",
        )
    if contract.get("status_code") != "ACTIVE":
        raise SaasRenewalV2AdapterError(
            "CONTRACT_NOT_ACTIVE",
            f"contract_id={contract_id} status_code={contract.get('status_code')}: "
            "ACTIVE 계약만 갱신할 수 있습니다.",
        )

    # ── 현재 CV 조회 (superseded_at IS NULL) ─────────────────────────
    cv_res = (
        supabase.table("saas_contract_commercial_versions")
        .select("*")
        .eq("contract_id", contract_id)
        .is_("superseded_at", "null")
        .limit(1)
        .execute()
    )
    if not cv_res.data:
        raise SaasRenewalV2AdapterError(
            "CURRENT_CV_NOT_FOUND",
            f"contract_id={contract_id}: 현재 유효한 Commercial Version이 없습니다.",
        )
    cv_row = cv_res.data[0]

    # ── Site Scopes 조회 ──────────────────────────────────────────────
    scope_res = (
        supabase.table("saas_contract_site_scopes")
        .select("entity_type, entity_id, sector, base_band_code")
        .eq("commercial_version_id", cv_row["id"])
        .execute()
    )
    scope_rows = scope_res.data or []

    return contract, cv_row, scope_rows


def _build_storage_bundle_from_db_rows(
    cv_row: dict,
    scope_rows: list,
) -> SaasContractStorageBundleV2:
    """DB 조회 결과를 SaasContractStorageBundleV2로 조립."""
    site_scopes = [
        SaasContractSiteScopeV2(
            entity_type=r["entity_type"],
            entity_id=r["entity_id"],
            sector=r["sector"],
            base_band_code=r.get("base_band_code"),
        )
        for r in scope_rows
    ]

    cv_kwargs: dict = {
        "commercial_schema_version": cv_row["commercial_schema_version"],
        "contract_id": cv_row["contract_id"],
        "version_no": cv_row["version_no"],
        "product_tier": cv_row["product_tier"],
        "pricing_mode": cv_row["pricing_mode"],
        "worker_capacity": cv_row["worker_capacity"],
        "term_months": cv_row["term_months"],
        "pricing_result_status": cv_row["pricing_result_status"],
        "pricing_policy_version": cv_row.get("pricing_policy_version"),
        "pricing_snapshot": cv_row.get("pricing_snapshot"),
        "effective_from": cv_row["effective_from"],
        "superseded_at": cv_row.get("superseded_at"),
        "created_by": cv_row.get("created_by"),
    }
    commercial_version = SaasContractCommercialVersionV2(**cv_kwargs)
    return SaasContractStorageBundleV2(
        commercial_version=commercial_version,
        site_scopes=site_scopes,
    )


def _validate_renewal_quote(
    supabase,
    quote_id: str,
    company_id: str,
) -> tuple[dict, SaasQuoteSnapshotItemV2, SaasPricingSnapshotV2]:
    """Quote 조회 → 소유권/상태/스키마/금액 검증.

    Returns: (quote_row, item, snap)
    """
    quote = member_quote_svc.get_member_quote(supabase, quote_id)
    if not quote:
        raise SaasRenewalV2AdapterError(
            "QUOTE_NOT_FOUND",
            "견적을 찾을 수 없습니다.",
        )
    if str(quote.get("company_id")) != str(company_id):
        raise SaasRenewalV2AdapterError(
            "QUOTE_NOT_OWNED",
            "견적 소유권이 없습니다.",
        )
    if quote.get("status_code") != "ISSUED":
        raise SaasRenewalV2AdapterError(
            "QUOTE_NOT_ISSUED",
            "발행(ISSUED) 상태 견적만 결제할 수 있습니다.",
        )
    if quote.get("service_type") != "SAAS":
        raise SaasRenewalV2AdapterError(
            "QUOTE_NOT_SAAS",
            "SaaS 견적만 이 경로로 결제할 수 있습니다.",
        )
    items = quote.get("items") or []
    if len(items) != 1:
        raise SaasRenewalV2AdapterError(
            "QUOTE_NOT_V2",
            f"V2 견적은 정확히 1개의 item을 가져야 합니다. (실제: {len(items)})",
        )
    raw_item = items[0]
    if raw_item.get("quote_schema_version") != SAAS_QUOTE_SCHEMA_VERSION:
        raise SaasRenewalV2AdapterError(
            "QUOTE_NOT_V2",
            f"SAAS_QUOTE_V2 스키마가 아닙니다: {raw_item.get('quote_schema_version')}",
        )
    try:
        item = SaasQuoteSnapshotItemV2.model_validate(raw_item)
    except (ValidationError, Exception) as exc:
        raise SaasRenewalV2AdapterError("QUOTE_ITEM_INVALID", str(exc)) from exc
    try:
        snap = SaasPricingSnapshotV2.model_validate(item.pricing_snapshot)
    except (ValidationError, Exception) as exc:
        raise SaasRenewalV2AdapterError("QUOTE_ITEM_INVALID", str(exc)) from exc

    q_supply = int(quote.get("supply_amount") or 0)
    q_vat = int(quote.get("vat_amount") or 0)
    q_total = int(quote.get("total_amount") or 0)

    if q_supply != item.supply_amount or item.supply_amount != snap.prepaid_supply_amount:
        raise SaasRenewalV2AdapterError(
            "QUOTE_PAYMENT_SNAPSHOT_INVALID",
            f"supply_amount 불일치: quote={q_supply}, item={item.supply_amount}, snap={snap.prepaid_supply_amount}",
        )
    if q_vat != item.vat_amount or item.vat_amount != snap.vat_amount:
        raise SaasRenewalV2AdapterError(
            "QUOTE_PAYMENT_SNAPSHOT_INVALID",
            f"vat_amount 불일치: quote={q_vat}, item={item.vat_amount}, snap={snap.vat_amount}",
        )
    if q_total != item.total_amount or item.total_amount != snap.total_amount:
        raise SaasRenewalV2AdapterError(
            "QUOTE_PAYMENT_SNAPSHOT_INVALID",
            f"total_amount 불일치: quote={q_total}, item={item.total_amount}, snap={snap.total_amount}",
        )

    return quote, item, snap


# ── Prepare Entry Point ───────────────────────────────────────────────────────

def prepare_saas_v2_renewal_payment_from_quote(
    supabase,
    *,
    contract_id: str,
    quote_id: str,
    company_id: str,
    user_id: str,
    proof_type: Optional[str] = None,
    buyername: Optional[str] = None,
    buyertel: Optional[str] = None,
    buyeremail: Optional[str] = None,
) -> dict:
    """기존 V2 Contract에 대해 Renewal Quote 기반 INICIS Prepaid 결제 준비.

    DB Read:  contracts (1) · saas_contract_commercial_versions (1) ·
              saas_contract_site_scopes (N) · quotes (1)
    DB Write: payments (1 row, payment_type=RENEWAL, contract_id=기존)
    DB Write 금지: contracts 0 · commercial_versions 0 · site_scopes 0 ·
                  subscriptions 0 · billing_keys 0

    Billing Boundary FREEZE:
      - payment_type="RENEWAL" (선불 1회, CardBilling/BillKey 아님)
      - subscriptions 테이블 접근 없음
      - billing_keys 테이블 접근 없음
    """
    _contract, _cv_row, _scope_rows = _fetch_current_contract_bundle(
        supabase, contract_id, company_id
    )
    _quote, item, snap = _validate_renewal_quote(supabase, quote_id, company_id)

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
        contract_id=contract_id,
        quote_id=quote_id,
        plan_code=None,
        period_months=snap.term_months,
        payment_type="RENEWAL",
        proof_type=proof_type,
        buyername=buyername,
        buyertel=buyertel,
        buyeremail=buyeremail,
    )


# ── Plan Builder Entry Point ──────────────────────────────────────────────────

def build_saas_v2_renewal_apply_plan(
    pay: dict,
    *,
    quote: dict,
    current_cv: dict,
    site_scopes: list,
    requested_effective_at: datetime,
) -> SaasV2RenewalApplyPlan:
    """Frozen Quote V2 Snapshot → Renewal Commercial Bundle (pure, DB write = 0).

    DB Read:  0 (caller가 사전 조회한 pay / quote / current_cv / site_scopes 전달)
    DB Write: 0 (plan만 조립)
    contracts mutation:    0
    commercial_versions:   0 (BE-OBJ10-D-B에서 원자적 처리)
    subscriptions:         0
    billing_keys:          0

    Args:
      pay                   — payments 행 (payment_type=RENEWAL, status_code∈{PAID,SUCCESS})
      quote                 — get_member_quote 반환값
      current_cv            — saas_contract_commercial_versions 현재 행 (superseded_at IS NULL)
      site_scopes           — saas_contract_site_scopes 행 목록
      requested_effective_at — 갱신 적용 기준 시각 (Owner Gate 결정, paid_at 아님)
    """
    # ── Step 1: 결제 성공 상태 가드 ──────────────────────────────────
    status_code = pay.get("status_code") or ""
    if status_code not in PAID_STATUS_CODES:
        raise SaasRenewalV2AdapterError(
            "RENEWAL_PAYMENT_NOT_PAID",
            f"결제 성공 상태(PAID/SUCCESS)만 처리합니다: {status_code!r}",
        )

    # ── Step 2: Legacy plan_code 금지 ────────────────────────────────
    if pay.get("plan_code") is not None:
        raise SaasRenewalV2AdapterError(
            "RENEWAL_LEGACY_PLAN_CODE_FORBIDDEN",
            f"V2 갱신 결제는 plan_code=None이어야 합니다: {pay.get('plan_code')!r}",
        )

    # ── Step 3-4: paid_at 필수 + 파싱 ──────────────────────────────
    if not pay.get("paid_at"):
        raise SaasRenewalV2AdapterError(
            "RENEWAL_PAID_AT_REQUIRED", "결제 성공 시각(paid_at)이 필수입니다."
        )
    _parse_paid_at(str(pay["paid_at"]))

    # ── Step 5-6: user_id 필수 + UUID 검증 ─────────────────────────
    if not pay.get("user_id"):
        raise SaasRenewalV2AdapterError(
            "RENEWAL_USER_REQUIRED", "결제자(user_id)가 필수입니다."
        )
    try:
        user_uuid = uuid.UUID(str(pay["user_id"]))
    except (ValueError, AttributeError) as exc:
        raise SaasRenewalV2AdapterError(
            "RENEWAL_USER_INVALID",
            f"user_id가 유효한 UUID가 아닙니다: {pay.get('user_id')!r}",
        ) from exc

    # ── Step 7: product_type 가드 ───────────────────────────────────
    if pay.get("product_type") != "SAAS":
        raise SaasRenewalV2AdapterError(
            "RENEWAL_PAY_NOT_SAAS",
            f"product_type=SAAS 결제만 처리합니다: {pay.get('product_type')!r}",
        )

    # ── Step 8: contract_id 필수 ─────────────────────────────────────
    pay_contract_id = pay.get("contract_id")
    if not pay_contract_id:
        raise SaasRenewalV2AdapterError(
            "RENEWAL_CONTRACT_ID_REQUIRED",
            "Renewal 결제는 contract_id가 필수입니다.",
        )

    # ── Step 9: payment_type = RENEWAL 가드 ──────────────────────────
    if (pay.get("payment_type") or "").upper() != "RENEWAL":
        raise SaasRenewalV2AdapterError(
            "RENEWAL_PAYMENT_TYPE_INVALID",
            f"payment_type=RENEWAL만 처리합니다: {pay.get('payment_type')!r}",
        )

    # ── Step 10: Quote 항목 추출 + 검증 ─────────────────────────────
    items = quote.get("items") or []
    if len(items) != 1:
        raise SaasRenewalV2AdapterError(
            "QUOTE_NOT_V2",
            f"V2 견적은 item 1개여야 합니다. (실제: {len(items)})",
        )
    raw_item = items[0]
    if raw_item.get("quote_schema_version") != SAAS_QUOTE_SCHEMA_VERSION:
        raise SaasRenewalV2AdapterError(
            "QUOTE_NOT_V2",
            f"SAAS_QUOTE_V2 스키마 아님: {raw_item.get('quote_schema_version')!r}",
        )
    try:
        item = SaasQuoteSnapshotItemV2.model_validate(raw_item)
    except (ValidationError, Exception) as exc:
        raise SaasRenewalV2AdapterError("QUOTE_ITEM_INVALID", str(exc)) from exc
    try:
        snap = SaasPricingSnapshotV2.model_validate(item.pricing_snapshot)
    except (ValidationError, Exception) as exc:
        raise SaasRenewalV2AdapterError("QUOTE_ITEM_INVALID", str(exc)) from exc

    # ── Step 11: 금액 3중 정합성 ────────────────────────────────────
    p_supply = int(pay.get("supply_amount") or 0)
    p_vat = int(pay.get("vat_amount") or 0)
    p_total = int(pay.get("total_amount") or 0)

    if p_supply != item.supply_amount or item.supply_amount != snap.prepaid_supply_amount:
        raise SaasRenewalV2AdapterError(
            "AMOUNT_SNAPSHOT_MISMATCH",
            f"supply_amount 불일치: pay={p_supply}, item={item.supply_amount}, snap={snap.prepaid_supply_amount}",
        )
    if p_vat != item.vat_amount or item.vat_amount != snap.vat_amount:
        raise SaasRenewalV2AdapterError(
            "AMOUNT_SNAPSHOT_MISMATCH",
            f"vat_amount 불일치: pay={p_vat}, item={item.vat_amount}, snap={snap.vat_amount}",
        )
    if p_total != item.total_amount or item.total_amount != snap.total_amount:
        raise SaasRenewalV2AdapterError(
            "AMOUNT_SNAPSHOT_MISMATCH",
            f"total_amount 불일치: pay={p_total}, item={item.total_amount}, snap={snap.total_amount}",
        )

    # ── Step 12: period_months ↔ term_months 정합성 ─────────────────
    pay_period = int(pay.get("period_months") or 0)
    if pay_period != snap.term_months:
        raise SaasRenewalV2AdapterError(
            "RENEWAL_PERIOD_TERM_MISMATCH",
            f"pay.period_months={pay_period} != snapshot.term_months={snap.term_months}",
        )

    # ── Step 13: next_version_no 계산 ───────────────────────────────
    current_version_no = int(current_cv.get("version_no") or 0)
    next_version_no = current_version_no + 1
    contract_uuid = uuid.UUID(str(pay_contract_id))

    # ── Step 14: 새 Commercial Bundle 조립 ──────────────────────────
    # effective_from = requested_effective_at (Owner Gate 결정, paid_at 아님)
    selection = SaasCommercialSelection(
        product_tier=snap.product_tier,
        pricing_mode=snap.pricing_mode,
        worker_capacity=snap.worker.capacity,
        term_months=snap.term_months,
    )
    calc = _frozen_snapshot_to_calc_result(snap)
    commercial_bundle = build_standard_contract_storage_bundle_v2(
        contract_id=contract_uuid,
        version_no=next_version_no,
        selection=selection,
        calculation_result=calc,
        effective_from=requested_effective_at,
        created_by=user_uuid,
    )

    return SaasV2RenewalApplyPlan(
        payment_id=str(pay.get("id") or ""),
        company_id=str(pay.get("company_id") or ""),
        contract_id=contract_uuid,
        next_version_no=next_version_no,
        requested_effective_at=requested_effective_at,
        commercial_bundle=commercial_bundle,
    )
