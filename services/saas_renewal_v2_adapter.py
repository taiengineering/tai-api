"""TAI Safe SaaS Renewal V2 Adapter — V2 Prepaid Renewal Payment Prepare + Plan Builder.

역할:
  기존 V2 Contract에 대해 Renewal Quote Frozen Snapshot을 검증하고
  INICIS Prepaid 결제 준비(payment_type="RENEWAL") + 순수 Renewal Plan을 조립한다.

Billing Boundary FREEZE:
  이 모듈은 Prepaid Renewal 경계(한 번의 선불 결제)만 담당한다.
  아래 항목은 이 경계 밖이며 이 모듈에서 절대 다루지 않는다:
    - subscriptions 테이블 생성 / 조회 / 변경
    - billing_keys 테이블 생성 / 조회 / 변경
    - 자동 반복 청구 (auto-recurring / BillKey / CardBilling)
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
from datetime import datetime, timezone
from typing import Optional

from dateutil import parser as dateutil_parser
from pydantic import ValidationError

import services.member_quote_svc as member_quote_svc
from schemas.saas_contract_commercial_v2 import (
    COMMERCIAL_STORAGE_SCHEMA_VERSION,
    SaasContractStorageBundleV2,
)
from schemas.saas_pricing_v2 import SaasCommercialSelection, SaasPricingSnapshotV2
from schemas.saas_quote_v2 import SAAS_QUOTE_SCHEMA_VERSION, SaasQuoteSnapshotItemV2
from services.payment_post_process import PAID_STATUS_CODES
from services.payment_svc import _run_inicis_prepare_exact, load_sign_key
from services.saas_commercial_version_time_v2 import (
    TemporalVersionError,
    find_future_commercial_versions_v2,
    select_effective_commercial_version_v2,
)
from services.saas_contract_storage_mapper_v2 import build_standard_contract_storage_bundle_v2
from services.saas_payment_success_v2_adapter import _frozen_snapshot_to_calc_result


# ── Domain Error ──────────────────────────────────────────────────────────────

class SaasRenewalV2AdapterError(Exception):
    """V2 Renewal Adapter 도메인 오류.

    code values (prepare):
      CONTRACT_NOT_FOUND                    — contract_id 미존재
      CONTRACT_NOT_OWNED                    — contracts.company_id != company_id
      CONTRACT_NOT_ACTIVE                   — contracts.status_code != ACTIVE
      CONTRACT_NOT_SAAS                     — contracts.service_type != SAAS
      CURRENT_CV_NOT_FOUND                  — as_of 시점 effective CV 없음
      CURRENT_CV_AMBIGUOUS                  — as_of 시점 effective CV 2개 이상
      RENEWAL_AS_OF_INVALID                 — as_of naive datetime
      RENEWAL_ALREADY_SCHEDULED             — as_of 기준 미래 scheduled Renewal CV 존재
      QUOTE_NOT_FOUND                       — quote_id 미존재
      QUOTE_NOT_OWNED                       — quote.company_id != company_id
      QUOTE_SOURCE_INVALID                  — quote.source != member_auto
      QUOTE_NOT_ISSUED                      — quote.status_code != ISSUED
      QUOTE_NOT_SAAS                        — quote.service_type != SAAS
      QUOTE_NOT_V2                          — items 수 != 1 / schema_version 불일치
      QUOTE_ITEM_INVALID                    — SaasQuoteSnapshotItemV2 검증 실패
      QUOTE_PAYMENT_SNAPSHOT_INVALID        — quote/item/snapshot 금액 3중 불일치

    code values (plan builder):
      RENEWAL_PAYMENT_NOT_PAID              — status_code ∉ {PAID, SUCCESS}
      RENEWAL_LEGACY_PLAN_CODE_FORBIDDEN    — pay.plan_code != None
      RENEWAL_PAID_AT_REQUIRED              — pay.paid_at 없음
      RENEWAL_PAID_AT_INVALID               — paid_at 파싱 실패 / naive datetime
      RENEWAL_USER_REQUIRED                 — pay.user_id 없음
      RENEWAL_USER_INVALID                  — pay.user_id 유효 UUID 아님
      RENEWAL_PAY_NOT_SAAS                  — product_type != SAAS
      RENEWAL_COMPANY_MISMATCH              — pay.company_id != quote.company_id
      RENEWAL_CONTRACT_ID_REQUIRED          — pay.contract_id 없음
      RENEWAL_QUOTE_ID_REQUIRED             — pay.quote_id 없음
      RENEWAL_PAYMENT_TYPE_INVALID          — pay.payment_type != RENEWAL
      CURRENT_CV_SCHEMA_INVALID             — commercial_schema_version 불일치 / effective_from 파싱 불가
      CURRENT_CV_SUPERSEDED                 — current_cv.superseded_at < requested_effective_at
      RENEWAL_BOUNDARY_CONFLICT             — current_cv.superseded_at > requested_effective_at
      CURRENT_CV_VERSION_NO_INVALID         — current_cv.version_no < 1
      RENEWAL_CONTRACT_CV_MISMATCH          — pay.contract_id != current_cv.contract_id
      QUOTE_SOURCE_INVALID                  — quote.source != member_auto (plan re-check)
      RENEWAL_QUOTE_ID_MISMATCH             — pay.quote_id != quote.id
      RENEWAL_EFFECTIVE_AT_INVALID          — requested_effective_at naive datetime
      RENEWAL_EFFECTIVE_BEFORE_CURRENT_VERSION — requested_effective_at < current_cv.effective_from
      RENEWAL_PERIOD_TERM_MISMATCH          — pay.period_months != snapshot.term_months
      AMOUNT_SNAPSHOT_MISMATCH              — pay/item/snapshot 금액 3중 불일치
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
      quote_id               — pay.quote_id (Frozen Snapshot 출처 견적)
      current_version_no     — current_cv.version_no
      next_version_no        — current_cv.version_no + 1
      requested_effective_at — 갱신 적용 기준 시각 (caller 입력, Owner Gate 결정)
      commercial_bundle      — 새 CV + 새 site_scopes (version_no=next_version_no)
    """
    payment_id: str
    company_id: str
    contract_id: uuid.UUID
    quote_id: str
    current_version_no: int
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


def _fetch_and_validate_contract(
    supabase,
    contract_id: str,
    company_id: str,
    as_of: datetime,
) -> tuple[dict, dict]:
    """DB에서 Contract + temporal current CV 조회 및 검증.

    DB Read: contracts(1) + saas_contract_commercial_versions(N)
    site_scopes는 BE-OBJ10-D-B에서 별도 조회.

    Temporal current selection:
      is_commercial_version_effective_at_v2(cv, as_of) 기준으로 선택.
      unique partial index (superseded_at IS NULL)로 LIMIT 1 하지 않음.

    Future renewal guard:
      as_of 이후 effective_from인 CV 존재 → RENEWAL_ALREADY_SCHEDULED.

    Returns: (contract_row, current_cv_row)
    """
    ct_res = (
        supabase.table("contracts")
        .select("id, company_id, status_code, service_type")
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
    if contract.get("service_type") != "SAAS":
        raise SaasRenewalV2AdapterError(
            "CONTRACT_NOT_SAAS",
            f"contract_id={contract_id} service_type={contract.get('service_type')}: "
            "SAAS 계약만 V2 갱신 대상입니다.",
        )

    cv_res = (
        supabase.table("saas_contract_commercial_versions")
        .select("*")
        .eq("contract_id", contract_id)
        .execute()
    )
    all_cvs = cv_res.data or []

    # Temporal current selection — LIMIT 1로 숨기지 않음
    try:
        current_cv = select_effective_commercial_version_v2(all_cvs, as_of)
    except TemporalVersionError as exc:
        if exc.code == "TEMPORAL_CURRENT_NOT_FOUND":
            raise SaasRenewalV2AdapterError(
                "CURRENT_CV_NOT_FOUND",
                f"contract_id={contract_id}: as_of={as_of} 시점 유효한 CV가 없습니다.",
            ) from exc
        if exc.code == "TEMPORAL_CURRENT_AMBIGUOUS":
            raise SaasRenewalV2AdapterError(
                "CURRENT_CV_AMBIGUOUS",
                f"contract_id={contract_id}: as_of={as_of} 시점 effective CV 2건 이상 — DB invariant 위반.",
            ) from exc
        raise

    # Future renewal guard — 미래 scheduled version = 중복 Renewal 금지
    future_cvs = find_future_commercial_versions_v2(all_cvs, as_of)
    if future_cvs:
        raise SaasRenewalV2AdapterError(
            "RENEWAL_ALREADY_SCHEDULED",
            f"contract_id={contract_id}: 미래 예약된 Renewal CV {len(future_cvs)}건 존재. "
            "추가 Renewal 적용 불가.",
        )

    return contract, current_cv


def _validate_renewal_quote(
    supabase,
    quote_id: str,
    company_id: str,
) -> tuple[dict, SaasQuoteSnapshotItemV2, SaasPricingSnapshotV2]:
    """Quote 조회 → 소유권/source/상태/스키마/금액 검증.

    Returns: (quote_row, item, snap)
    """
    quote = member_quote_svc.get_member_quote(supabase, quote_id)
    if not quote:
        raise SaasRenewalV2AdapterError("QUOTE_NOT_FOUND", "견적을 찾을 수 없습니다.")
    if str(quote.get("company_id")) != str(company_id):
        raise SaasRenewalV2AdapterError("QUOTE_NOT_OWNED", "견적 소유권이 없습니다.")
    if quote.get("source") != "member_auto":
        raise SaasRenewalV2AdapterError(
            "QUOTE_SOURCE_INVALID",
            f"source=member_auto 견적만 Renewal 결제 대상입니다: {quote.get('source')!r}",
        )
    if quote.get("status_code") != "ISSUED":
        raise SaasRenewalV2AdapterError(
            "QUOTE_NOT_ISSUED", "발행(ISSUED) 상태 견적만 결제할 수 있습니다."
        )
    if quote.get("service_type") != "SAAS":
        raise SaasRenewalV2AdapterError(
            "QUOTE_NOT_SAAS", "SaaS 견적만 이 경로로 결제할 수 있습니다."
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
    as_of: datetime,
    proof_type: Optional[str] = None,
    buyername: Optional[str] = None,
    buyertel: Optional[str] = None,
    buyeremail: Optional[str] = None,
) -> dict:
    """기존 V2 Contract에 대해 Renewal Quote 기반 INICIS Prepaid 결제 준비.

    DB Read:  contracts(1) + saas_contract_commercial_versions(N) + quotes(1)
    DB Write: payments(1, payment_type=RENEWAL, contract_id=기존)
    DB Write 금지: contracts 0 · commercial_versions 0 · site_scopes 0 ·
                  subscriptions 0 · billing_keys 0

    as_of: timezone-aware datetime (caller 제공, datetime.now() 직접 호출 금지)
    """
    if as_of.tzinfo is None:
        raise SaasRenewalV2AdapterError(
            "RENEWAL_AS_OF_INVALID",
            f"as_of은 timezone-aware datetime이어야 합니다: {as_of!r}",
        )
    _fetch_and_validate_contract(supabase, contract_id, company_id, as_of)
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
    requested_effective_at: datetime,
) -> SaasV2RenewalApplyPlan:
    """Frozen Quote V2 Snapshot → Renewal Commercial Bundle (pure, DB write = 0).

    DB Read:  0 (caller가 사전 조회한 pay / quote / current_cv 전달)
    DB Write: 0 (plan만 조립)
    contracts mutation:    0
    commercial_versions:   0 (BE-OBJ10-D-B에서 원자적 처리)
    subscriptions:         0
    billing_keys:          0

    CHANGE_ORDER_REUSE = NOT WIRED IN D-A
      D-A 목적은 Frozen Renewal Quote → Renewal Apply Plan 경계 확립이며
      실제 supersede/apply + change classification은 D-B 책임.

    Args:
      pay                   — payments 행 (payment_type=RENEWAL, status_code∈{PAID,SUCCESS})
      quote                 — get_member_quote 반환값 (source=member_auto, ISSUED, SAAS)
      current_cv            — saas_contract_commercial_versions 현재 행
                              (superseded_at IS NULL — DB unique partial index 보장)
      requested_effective_at — 갱신 적용 기준 시각 (Owner Gate 결정, paid_at 아님)
    """
    # ── Step 1: 결제 성공 상태 ───────────────────────────────────────
    status_code = pay.get("status_code") or ""
    if status_code not in PAID_STATUS_CODES:
        raise SaasRenewalV2AdapterError(
            "RENEWAL_PAYMENT_NOT_PAID",
            f"결제 성공 상태(PAID/SUCCESS)만 처리합니다: {status_code!r}",
        )

    # ── Step 2: Legacy plan_code 금지 ───────────────────────────────
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

    # ── Step 8: pay ↔ quote company 일치 ────────────────────────────
    pay_company = str(pay.get("company_id") or "")
    quote_company = str(quote.get("company_id") or "")
    if not pay_company or pay_company != quote_company:
        raise SaasRenewalV2AdapterError(
            "RENEWAL_COMPANY_MISMATCH",
            f"pay.company_id={pay_company} != quote.company_id={quote_company}",
        )

    # ── Step 9: contract_id 필수 ────────────────────────────────────
    pay_contract_id = pay.get("contract_id")
    if not pay_contract_id:
        raise SaasRenewalV2AdapterError(
            "RENEWAL_CONTRACT_ID_REQUIRED",
            "Renewal 결제는 contract_id가 필수입니다.",
        )

    # ── Step 10: quote_id 필수 ──────────────────────────────────────
    pay_quote_id = pay.get("quote_id")
    if not pay_quote_id:
        raise SaasRenewalV2AdapterError(
            "RENEWAL_QUOTE_ID_REQUIRED",
            "Renewal 결제는 quote_id가 필수입니다.",
        )

    # ── Step 11: payment_type = RENEWAL ─────────────────────────────
    if (pay.get("payment_type") or "").upper() != "RENEWAL":
        raise SaasRenewalV2AdapterError(
            "RENEWAL_PAYMENT_TYPE_INVALID",
            f"payment_type=RENEWAL만 처리합니다: {pay.get('payment_type')!r}",
        )

    # ── Step 12: current_cv 구조 검증 ───────────────────────────────
    if current_cv.get("commercial_schema_version") != COMMERCIAL_STORAGE_SCHEMA_VERSION:
        raise SaasRenewalV2AdapterError(
            "CURRENT_CV_SCHEMA_INVALID",
            f"commercial_schema_version 불일치: {current_cv.get('commercial_schema_version')!r}",
        )
    # timezone-aware 검증을 superseded_at 비교보다 먼저 수행 (TypeError 방지)
    if requested_effective_at.tzinfo is None:
        raise SaasRenewalV2AdapterError(
            "RENEWAL_EFFECTIVE_AT_INVALID",
            "requested_effective_at는 timezone-aware datetime이어야 합니다.",
        )
    # transition-source 판정: superseded_at 기준 3-way
    #   IS NULL                       → PRE-APPLY: PASS
    #   == requested_effective_at     → POST-APPLY IDEMPOTENT REBUILD: PASS
    #   < requested_effective_at      → CURRENT_CV_SUPERSEDED
    #   > requested_effective_at      → RENEWAL_BOUNDARY_CONFLICT
    sup_raw = current_cv.get("superseded_at")
    if sup_raw is not None:
        try:
            sup_dt = dateutil_parser.isoparse(str(sup_raw))
        except (ValueError, TypeError) as exc:
            raise SaasRenewalV2AdapterError(
                "CURRENT_CV_SCHEMA_INVALID",
                f"current_cv.superseded_at 파싱 실패: {sup_raw!r}",
            ) from exc
        if sup_dt.tzinfo is None:
            sup_dt = sup_dt.replace(tzinfo=timezone.utc)
        if requested_effective_at == sup_dt:
            pass  # idempotent rebuild: 동일 boundary B2 적용 후 재처리 허용
        elif requested_effective_at > sup_dt:
            raise SaasRenewalV2AdapterError(
                "CURRENT_CV_SUPERSEDED",
                f"current_cv.superseded_at={sup_dt} < requested_effective_at={requested_effective_at}"
                " — 이미 더 이른 시점에 supersede된 Version입니다.",
            )
        else:  # requested_effective_at < sup_dt
            raise SaasRenewalV2AdapterError(
                "RENEWAL_BOUNDARY_CONFLICT",
                f"current_cv.superseded_at={sup_dt} > requested_effective_at={requested_effective_at}"
                " — 다른 boundary로 예약된 transition source입니다.",
            )
    cv_version_no = current_cv.get("version_no")
    if not isinstance(cv_version_no, int) or cv_version_no < 1:
        raise SaasRenewalV2AdapterError(
            "CURRENT_CV_VERSION_NO_INVALID",
            f"current_cv.version_no={cv_version_no}: 1 이상이어야 합니다.",
        )

    # ── Step 13: pay.contract_id ↔ current_cv.contract_id ───────────
    if str(pay_contract_id) != str(current_cv.get("contract_id") or ""):
        raise SaasRenewalV2AdapterError(
            "RENEWAL_CONTRACT_CV_MISMATCH",
            f"pay.contract_id={pay_contract_id} != current_cv.contract_id={current_cv.get('contract_id')}",
        )

    # ── Step 14: Quote 신원/상태 재검증 ─────────────────────────────
    if quote.get("source") != "member_auto":
        raise SaasRenewalV2AdapterError(
            "QUOTE_SOURCE_INVALID",
            f"source=member_auto 견적만 처리합니다: {quote.get('source')!r}",
        )
    if quote.get("service_type") != "SAAS":
        raise SaasRenewalV2AdapterError(
            "QUOTE_NOT_SAAS",
            f"service_type=SAAS 견적만 처리합니다: {quote.get('service_type')!r}",
        )
    if quote.get("status_code") != "ISSUED":
        raise SaasRenewalV2AdapterError(
            "QUOTE_NOT_ISSUED",
            f"ISSUED 상태 견적만 처리합니다: {quote.get('status_code')!r}",
        )

    # ── Step 15: pay.quote_id ↔ quote.id ────────────────────────────
    if str(pay_quote_id) != str(quote.get("id") or ""):
        raise SaasRenewalV2AdapterError(
            "RENEWAL_QUOTE_ID_MISMATCH",
            f"pay.quote_id={pay_quote_id} != quote.id={quote.get('id')}",
        )

    # ── Step 17: effective_from 파싱 + 순서 검증 ────────────────────
    raw_eff = current_cv.get("effective_from")
    if raw_eff is None:
        raise SaasRenewalV2AdapterError(
            "CURRENT_CV_SCHEMA_INVALID", "current_cv.effective_from 없음"
        )
    if isinstance(raw_eff, str):
        try:
            cv_effective_from: datetime = dateutil_parser.isoparse(raw_eff)
        except Exception as exc:
            raise SaasRenewalV2AdapterError(
                "CURRENT_CV_SCHEMA_INVALID",
                f"current_cv.effective_from 파싱 실패: {raw_eff!r}",
            ) from exc
    else:
        cv_effective_from = raw_eff

    if cv_effective_from.tzinfo is None:
        cv_effective_from = cv_effective_from.replace(tzinfo=timezone.utc)

    if requested_effective_at < cv_effective_from:
        raise SaasRenewalV2AdapterError(
            "RENEWAL_EFFECTIVE_BEFORE_CURRENT_VERSION",
            f"requested_effective_at={requested_effective_at} < "
            f"current_cv.effective_from={cv_effective_from}",
        )

    # ── Step 18: Quote 항목 추출 + 검증 ─────────────────────────────
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

    # ── Step 19: 금액 3중 정합성 ────────────────────────────────────
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

    # ── Step 20: period_months ↔ term_months ────────────────────────
    pay_period = int(pay.get("period_months") or 0)
    if pay_period != snap.term_months:
        raise SaasRenewalV2AdapterError(
            "RENEWAL_PERIOD_TERM_MISMATCH",
            f"pay.period_months={pay_period} != snapshot.term_months={snap.term_months}",
        )

    # ── Step 21: next_version_no 계산 ───────────────────────────────
    next_version_no = cv_version_no + 1
    contract_uuid = uuid.UUID(str(pay_contract_id))

    # ── Step 22: 새 Commercial Bundle 조립 ──────────────────────────
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
        company_id=pay_company,
        contract_id=contract_uuid,
        quote_id=str(pay_quote_id),
        current_version_no=cv_version_no,
        next_version_no=next_version_no,
        requested_effective_at=requested_effective_at,
        commercial_bundle=commercial_bundle,
    )
