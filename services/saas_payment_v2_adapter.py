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
import os
from typing import Optional
from uuid import uuid4

from pydantic import ValidationError

import services.member_quote_svc as member_quote_svc
from db.direct_sql import insert_subscription
from schemas.saas_pricing_v2 import SaasPricingSnapshotV2
from schemas.saas_quote_v2 import SAAS_QUOTE_SCHEMA_VERSION, SaasQuoteSnapshotItemV2
from services.payment_helpers import (
    BILLING_RETURN_URL,
    DEFAULT_CLOSE_URL,
    now_iso as _now_iso,
    sha256 as _sha256,
    ts_ms as _ts_ms,
)
from services.payment_svc import (
    _build_inicis_prepare_response_exact,
    _run_inicis_prepare_exact,
    load_sign_key,
)
from services.time import now_kst

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = ("PENDING", "PAID", "SUCCESS")
_PAID_STATUSES = ("PAID", "SUCCESS")


# ── Domain Error ──────────────────────────────────────────────────────────────

_VALID_PAYMENT_MONTHS = frozenset({1, 3, 6, 9, 12})


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
      QUOTE_PAYMENT_MONTHS_INVALID   — payment_months not in {1,3,6,9,12}
      QUOTE_PAYMENT_PENDING          — 다른 사용자의 PENDING 결제 존재
      QUOTE_ALREADY_PAID             — PAID/SUCCESS 결제 이미 존재
      QUOTE_PAYMENT_STATE_CONFLICT   — 경쟁 삽입 후 재조회 불일치
      BILLING_ENV_NOT_SET            — 정기결제 환경변수 미설정
      V3_PAY_INSERT_FAILED           — V3 PENDING payment INSERT 실패
      V3_SUB_CREATE_FAILED           — V3 subscription 생성 실패 (compensation: payment→FAILED)
      V3_BIND_FAILED                 — V3 payment-subscription 바인드 실패 (compensation: both→FAILED)
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


# ── V3 Recurring Helpers ──────────────────────────────────────────────────────

def _require_billing_env(name: str) -> str:
    v = (os.getenv(name) or "").strip()
    if not v:
        raise SaasPaymentV2AdapterError(
            "BILLING_ENV_NOT_SET",
            f"정기결제 환경변수 미설정: {name}",
        )
    return v


def _make_billing_oid() -> str:
    return f"TAI-BIL-{now_kst():%Y%m%d%H%M%S}-{uuid4().hex[:6].upper()}"


def _build_billing_prepare_params(
    *,
    mid: str,
    sign_key: str,
    oid: str,
    total_amount: int,
    goodname: str,
    buyername: Optional[str] = None,
    buyertel: Optional[str] = None,
    buyeremail: Optional[str] = None,
) -> dict:
    """INICIS 빌링키 발급 파라미터 구성 (billing_prepare 라우터와 동일 서명 로직)."""
    price_str = str(total_amount)
    timestamp = _ts_ms()
    mKey = _sha256(sign_key)
    signature = _sha256(f"oid={oid}&price={price_str}&timestamp={timestamp}")
    verification = _sha256(f"oid={oid}&price={price_str}&signKey={sign_key}&timestamp={timestamp}")
    return {
        "mid": mid,
        "mKey": mKey,
        "oid": oid,
        "price": price_str,
        "goodname": goodname,
        "buyername": buyername or "",
        "buyertel": buyertel or "",
        "buyeremail": buyeremail or "",
        "timestamp": timestamp,
        "signature": signature,
        "verification": verification,
        "use_chkfake": "Y",
        "returnUrl": BILLING_RETURN_URL,
        "closeUrl": DEFAULT_CLOSE_URL,
        "charset": "UTF-8",
        "gopaymethod": "",
        "acceptmethod": "centerCd(Y):BILLAUTH(Card)",
    }


def _mark_payment_failed(supabase, payment_id: str, reason: str) -> None:
    try:
        supabase.table("payments").update({
            "status_code": "FAILED",
            "fail_reason": reason[:500] if reason else None,
            "updated_at": _now_iso(),
        }).eq("id", payment_id).execute()
    except Exception:
        logger.warning("[V3_RECURRING] payment FAILED mark failed: payment=%s", payment_id)


def _mark_subscription_failed(supabase, subscription_id: str, reason: str) -> None:
    try:
        supabase.table("subscriptions").update({
            "status": "FAILED",
            "last_failure_reason": reason[:500] if reason else None,
            "updated_at": _now_iso(),
        }).eq("id", subscription_id).execute()
    except Exception:
        logger.warning("[V3_RECURRING] subscription FAILED mark failed: sub=%s", subscription_id)


def _build_v3_recurring_response(
    *,
    mid: str,
    sign_key: str,
    billing_oid: str,
    payment_id: str,
    subscription_id: str,
    snap: SaasPricingSnapshotV2,
    goodname: str,
    buyername: Optional[str],
    buyertel: Optional[str],
    buyeremail: Optional[str],
) -> dict:
    params = _build_billing_prepare_params(
        mid=mid,
        sign_key=sign_key,
        oid=billing_oid,
        total_amount=snap.total_amount,
        goodname=goodname,
        buyername=buyername,
        buyertel=buyertel,
        buyeremail=buyeremail,
    )
    return {
        "status": "success",
        "data": {
            **params,
            "payment_id": payment_id,
            "subscription_id": subscription_id,
            "payment_route": "RECURRING",
        },
    }


def _prepare_saas_v3_recurring(
    supabase,
    *,
    quote_id: str,
    user_id: str,
    company_id: str,
    snap: SaasPricingSnapshotV2,
    goodname: str,
    buyername: Optional[str] = None,
    buyertel: Optional[str] = None,
    buyeremail: Optional[str] = None,
) -> dict:
    """V3 정기결제 준비 (payment_months=1).

    STEP 1: duplicate guard
    STEP 2: PENDING payment INSERT (quote_id, plan_code=NULL, subscription_id=NULL 초기)
    STEP 3: PENDING subscription INSERT (plan_code=NULL, product_type=SAAS)
    STEP 4: bind payment.subscription_id + inicis_order_id
    STEP 5: return INICIS Billing params
    """
    mid = _require_billing_env("INICIS_BILLING_MID")
    sign_key = _require_billing_env("INICIS_BILLING_SIGN_KEY")

    # STEP 1: duplicate guard
    existing = _find_existing_v2_payment(supabase, quote_id)
    if existing:
        status = (existing.get("status_code") or "").upper()
        if status in _PAID_STATUSES:
            raise SaasPaymentV2AdapterError("QUOTE_ALREADY_PAID", "이미 결제 완료된 견적입니다.")
        if str(existing.get("user_id")) != str(user_id):
            raise SaasPaymentV2AdapterError("QUOTE_PAYMENT_PENDING", "이 견적에 대해 진행 중인 결제가 있습니다.")
        # Same-user PENDING → reuse: rebuild billing params from subscription
        sub_id = existing.get("subscription_id")
        if not sub_id:
            raise SaasPaymentV2AdapterError(
                "QUOTE_PAYMENT_STATE_CONFLICT",
                "정기결제 예약 상태 불일치: subscription_id 없음",
            )
        sub_res = (
            supabase.table("subscriptions")
            .select("id, inicis_order_id, status")
            .eq("id", str(sub_id))
            .limit(1)
            .execute()
        )
        sub = sub_res.data[0] if sub_res.data else None
        if not sub or not sub.get("inicis_order_id"):
            raise SaasPaymentV2AdapterError(
                "QUOTE_PAYMENT_STATE_CONFLICT",
                "정기결제 구독 조회 실패",
            )
        logger.info(
            "[V3_RECURRING] quote=%s user=%s PENDING reuse payment=%s",
            quote_id, user_id, existing.get("id"),
        )
        return _build_v3_recurring_response(
            mid=mid,
            sign_key=sign_key,
            billing_oid=sub["inicis_order_id"],
            payment_id=str(existing["id"]),
            subscription_id=str(sub_id),
            snap=snap,
            goodname=goodname,
            buyername=buyername,
            buyertel=buyertel,
            buyeremail=buyeremail,
        )

    # STEP 2: INSERT PENDING payment (subscription_id=NULL initially)
    now = _now_iso()
    pay_row = {
        "user_id": user_id,
        "company_id": company_id,
        "quote_id": quote_id,
        "product_type": "SAAS",
        "payment_method": "INICIS",
        "payment_type": "CARD",
        "pg_method": "CardBilling",
        "proof_type": "CARD_RECEIPT",
        "supply_amount": snap.prepaid_supply_amount,
        "vat_amount": snap.vat_amount,
        "total_amount": snap.total_amount,
        "plan_code": None,
        "period_months": 1,
        "charge_cycle": 1,
        "is_recurring": False,
        "status_code": "PENDING",
        "created_at": now,
        "updated_at": now,
    }
    try:
        pay_ins = supabase.table("payments").insert(pay_row).execute()
    except Exception as exc:
        if _is_quote_v2_unique_violation(exc):
            logger.info("[V3_RECURRING] quote=%s race-INSERT 23505 → recovery", quote_id)
            return _handle_v3_recurring_race_recovery(
                supabase, quote_id, user_id, mid, sign_key, snap, goodname,
                buyername=buyername, buyertel=buyertel, buyeremail=buyeremail,
            )
        raise SaasPaymentV2AdapterError("V3_PAY_INSERT_FAILED", f"결제 레코드 생성 실패: {exc}")

    if not pay_ins.data:
        raise SaasPaymentV2AdapterError("V3_PAY_INSERT_FAILED", "결제 레코드 생성 실패")
    payment_id = str(pay_ins.data[0]["id"])

    # STEP 3: INSERT PENDING subscription (plan_code=NULL, product_type=SAAS)
    billing_oid = _make_billing_oid()
    sub_row = {
        "user_id": user_id,
        "company_id": company_id,
        "product_type": "SAAS",
        "plan_code": None,
        "plan_name": goodname,
        "amount": snap.total_amount,
        "supply_amount": snap.prepaid_supply_amount,
        "vat_amount": snap.vat_amount,
        "billing_cycle": "monthly",
        "status": "PENDING",
        "inicis_order_id": billing_oid,
        "created_at": now,
        "updated_at": now,
    }
    try:
        created_sub = insert_subscription(sub_row)
    except Exception as exc:
        _mark_payment_failed(supabase, payment_id, f"subscription 생성 실패: {exc}")
        raise SaasPaymentV2AdapterError("V3_SUB_CREATE_FAILED", f"구독 레코드 생성 실패: {exc}")

    if not created_sub:
        _mark_payment_failed(supabase, payment_id, "subscription 생성 실패 (no data)")
        raise SaasPaymentV2AdapterError("V3_SUB_CREATE_FAILED", "구독 레코드 생성 실패")

    subscription_id = str(created_sub["id"])

    # STEP 4: bind payment.subscription_id + inicis_order_id
    try:
        supabase.table("payments").update({
            "subscription_id": subscription_id,
            "inicis_order_id": billing_oid,
            "updated_at": _now_iso(),
        }).eq("id", payment_id).execute()
    except Exception as exc:
        _mark_payment_failed(supabase, payment_id, f"subscription 바인딩 실패: {exc}")
        _mark_subscription_failed(supabase, subscription_id, f"payment 바인딩 실패: {exc}")
        raise SaasPaymentV2AdapterError("V3_BIND_FAILED", f"결제-구독 연결 실패: {exc}")

    logger.info(
        "[V3_RECURRING] quote=%s user=%s payment=%s subscription=%s",
        quote_id, user_id, payment_id, subscription_id,
    )
    return _build_v3_recurring_response(
        mid=mid,
        sign_key=sign_key,
        billing_oid=billing_oid,
        payment_id=payment_id,
        subscription_id=subscription_id,
        snap=snap,
        goodname=goodname,
        buyername=buyername,
        buyertel=buyertel,
        buyeremail=buyeremail,
    )


def _handle_v3_recurring_race_recovery(
    supabase,
    quote_id: str,
    user_id: str,
    mid: str,
    sign_key: str,
    snap: SaasPricingSnapshotV2,
    goodname: str,
    *,
    buyername: Optional[str] = None,
    buyertel: Optional[str] = None,
    buyeremail: Optional[str] = None,
) -> dict:
    """V3 recurring 경쟁 INSERT 후 재조회 → 동일 라우팅."""
    existing = _find_existing_v2_payment(supabase, quote_id)
    if not existing:
        raise SaasPaymentV2AdapterError(
            "QUOTE_PAYMENT_STATE_CONFLICT",
            "결제 중복 감지 후 기존 결제를 확인할 수 없습니다.",
        )
    status = (existing.get("status_code") or "").upper()
    if status in _PAID_STATUSES:
        raise SaasPaymentV2AdapterError("QUOTE_ALREADY_PAID", "이미 결제 완료된 견적입니다.")
    if str(existing.get("user_id")) != str(user_id):
        raise SaasPaymentV2AdapterError("QUOTE_PAYMENT_PENDING", "이 견적에 대해 진행 중인 결제가 있습니다.")
    sub_id = existing.get("subscription_id")
    if not sub_id:
        raise SaasPaymentV2AdapterError(
            "QUOTE_PAYMENT_STATE_CONFLICT",
            "정기결제 예약 상태 불일치: subscription_id 없음",
        )
    sub_res = (
        supabase.table("subscriptions")
        .select("id, inicis_order_id")
        .eq("id", str(sub_id))
        .limit(1)
        .execute()
    )
    sub = sub_res.data[0] if sub_res.data else None
    if not sub or not sub.get("inicis_order_id"):
        raise SaasPaymentV2AdapterError(
            "QUOTE_PAYMENT_STATE_CONFLICT",
            "정기결제 구독 조회 실패",
        )
    return _build_v3_recurring_response(
        mid=mid,
        sign_key=sign_key,
        billing_oid=sub["inicis_order_id"],
        payment_id=str(existing["id"]),
        subscription_id=str(sub_id),
        snap=snap,
        goodname=goodname,
        buyername=buyername,
        buyertel=buyertel,
        buyeremail=buyeremail,
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

    # ── Step 9.5: payment_months 검증 및 결제 경로 분기 ──────────────
    if snap.payment_months not in _VALID_PAYMENT_MONTHS:
        raise SaasPaymentV2AdapterError(
            "QUOTE_PAYMENT_MONTHS_INVALID",
            f"payment_months는 1,3,6,9,12 중 하나여야 합니다: {snap.payment_months}",
        )

    if snap.payment_months == 1:
        # RECURRING: V3 정기결제 (monthly billing)
        return _prepare_saas_v3_recurring(
            supabase,
            quote_id=quote_id,
            user_id=user_id,
            company_id=company_id,
            snap=snap,
            goodname=item.display_name,
            buyername=buyername,
            buyertel=buyertel,
            buyeremail=buyeremail,
        )

    # SINGLE: payment_months in {3,6,9,12} → 기존 단건결제 경로
    sign_key = load_sign_key()

    def _with_single_route(resp: dict) -> dict:
        if isinstance(resp.get("data"), dict):
            resp["data"]["payment_route"] = "SINGLE"
        return resp

    # ── Step 10: Duplicate Guard ──────────────────────────────────────
    existing = _find_existing_v2_payment(supabase, quote_id)
    if existing:
        return _with_single_route(_validate_pending_reuse(
            existing, user_id, company_id, quote_id, snap, sign_key, item.display_name,
            buyername=buyername, buyertel=buyertel, buyeremail=buyeremail,
        ))

    # ── Step 11: INICIS Prepare Core 호출 ────────────────────────────
    try:
        return _with_single_route(_run_inicis_prepare_exact(
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
        ))
    except Exception as exc:
        if _is_quote_v2_unique_violation(exc):
            logger.info("[V2_ADAPTER] quote=%s race-INSERT 23505 → recovery", quote_id)
            return _with_single_route(_handle_race_recovery(
                supabase, quote_id, user_id, company_id, snap, sign_key, item.display_name,
                buyername=buyername, buyertel=buyertel, buyeremail=buyeremail,
            ))
        raise
