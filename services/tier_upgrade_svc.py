"""SaaS tier upgrade prepare + idempotent writer.

WO-COMMON-TIER-PAYMENT-GATE-MODULARIZE-001 / B3.
판정은 B2 resolve_saas_tier_gate_context 한 길. VAT 는 payment_helpers.add_vat.
client amount/plan 미신뢰. PLAN_MAP / alias / billing charge 미사용.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import uuid4

from schemas.payment import PrepareBody
from services.payment_helpers import add_vat, now_iso
from services.payment_svc import run_inicis_prepare
from services.tier_payment_gate_svc import (
    TierGateError,
    resolve_saas_tier_gate_context,
)

log = logging.getLogger(__name__)

_EXPECTED_VAT_RATE = 0.1
_SECTOR_PRODUCT = {
    "INDUSTRY": "SAAS_INDUSTRY",
    "BUILDING": "SAAS_BUILDING",
    "CONSTRUCTION": "SAAS_CONSTRUCTION",
}


class TierUpgradeError(Exception):
    """upgrade 도메인 오류. code 를 라우터/writer 가 번역한다."""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message or code
        super().__init__(self.message)


def prepare_saas_tier_upgrade(
    supabase,
    current,
    *,
    factory_id=None,
    site_id=None,
    buyername=None,
    buyertel=None,
    buyeremail=None,
) -> dict:
    """auth/ownership 은 라우터. 여기서는 gate 재평가 → delta → server prepare → transition."""
    ctx = resolve_saas_tier_gate_context(
        supabase, current, factory_id=factory_id, site_id=site_id
    )
    if ctx["status"] == "FIT":
        raise TierUpgradeError("ALREADY_FIT", "이미 필요 플랜을 충족합니다.")
    if ctx["status"] != "UPGRADE_REQUIRED":
        raise TierGateError(ctx["status"], "업그레이드 대상이 아닙니다.")

    current_plan = ctx["current_plan"]
    target_plan = ctx["required_plan"]
    _assert_price_contract(current_plan)
    _assert_price_contract(target_plan)

    current_supply = _money(current_plan.get("amount"))
    target_supply = _money(target_plan.get("amount"))
    if target_supply <= 0:
        raise TierUpgradeError(
            "MANUAL_QUOTE_REQUIRED",
            "맞춤 플랜은 자동 결제가 불가합니다. 견적이 필요합니다.",
        )
    delta_supply = target_supply - current_supply
    if delta_supply <= 0:
        raise TierUpgradeError("INVALID_UPGRADE_DELTA", "업그레이드 차액이 없습니다.")

    delta_total = add_vat(delta_supply)
    delta_vat = delta_total - delta_supply
    target_total = add_vat(target_supply)
    target_vat = target_total - target_supply

    sub_snap = _snapshot_active_subscription(supabase, ctx["company_id"])

    sector = ctx["sector"]
    product_type = _SECTOR_PRODUCT.get(sector)
    if not product_type:
        raise TierUpgradeError("UNSUPPORTED_PRICE_CONTRACT", "결제 상품 유형을 정할 수 없습니다.")

    from_code = (current_plan.get("tier_code") or "").strip()
    target_code = (target_plan.get("tier_code") or "").strip()
    display = target_plan.get("display_name") or target_code

    _reject_if_prepared_attempt_open(
        supabase,
        company_id=ctx["company_id"],
        contract_id=ctx["contract"]["id"],
        entity_type=ctx["entity_type"],
        entity_id=ctx["entity_id"],
        target_plan_code=target_code,
    )

    body = PrepareBody(
        user_id=str(current.get("id") or ""),
        company_id=ctx["company_id"],
        contract_id=ctx["contract"]["id"],
        product_type=product_type,
        amount=delta_supply,
        plan_code=target_code,
        payment_type="UPGRADE",
        period_months=1,
        goodname=f"SaaS 업그레이드 {from_code} → {target_code}",
        buyername=buyername or "고객",
        buyertel=buyertel or "00000000000",
        buyeremail=buyeremail,
    )
    prepared = run_inicis_prepare(body)
    payment_id = (prepared.get("data") or {}).get("payment_id")
    if not payment_id:
        raise TierUpgradeError("TRANSITION_PERSIST_FAILED", "결제 준비에 실패했습니다.")

    now = now_iso()
    transition = {
        "id": str(uuid4()),
        "payment_id": payment_id,
        "company_id": ctx["company_id"],
        "contract_id": ctx["contract"]["id"],
        "entity_type": ctx["entity_type"],
        "entity_id": ctx["entity_id"],
        "sector": sector,
        "from_plan_code": from_code,
        "target_plan_code": target_code,
        "billing_unit": "MONTHLY",
        "current_supply_amount": current_supply,
        "target_supply_amount": target_supply,
        "delta_supply_amount": delta_supply,
        "delta_vat_amount": delta_vat,
        "delta_total_amount": delta_total,
        "target_vat_amount": target_vat,
        "target_total_amount": target_total,
        "status": "PREPARED",
        "last_error": None,
        "applied_at": None,
        "created_at": now,
        "updated_at": now,
        "subscription_id": (sub_snap or {}).get("id"),
        "subscription_snapshot": sub_snap,
        "target_plan_name": display,
    }
    try:
        ins = (
            supabase.table("saas_tier_upgrade_transitions")
            .insert(transition)
            .execute()
        )
        if not ins.data:
            raise RuntimeError("empty insert")
    except Exception as e:  # noqa: BLE001
        log.error("tier upgrade transition insert failed payment=%s: %s", payment_id, e)
        try:
            supabase.table("payments").update(
                {
                    "status_code": "FAILED",
                    "fail_reason": "TIER_UPGRADE_TRANSITION_PERSIST_FAILED",
                    "updated_at": now_iso(),
                }
            ).eq("id", payment_id).execute()
        except Exception as cleanup_exc:  # noqa: BLE001
            log.error(
                "tier upgrade payment FAILED cleanup failed payment=%s: %s",
                payment_id,
                cleanup_exc,
            )
        raise TierUpgradeError(
            "TRANSITION_PERSIST_FAILED",
            "업그레이드 이력을 저장하지 못해 결제를 진행할 수 없습니다.",
        ) from e

    prepared = dict(prepared)
    prepared["upgrade"] = {
        "from_plan_code": from_code,
        "target_plan_code": target_code,
        "delta_supply_amount": delta_supply,
        "delta_vat_amount": delta_vat,
        "delta_total_amount": delta_total,
        "target_supply_amount": target_supply,
        "target_vat_amount": target_vat,
        "target_total_amount": target_total,
        "sector": sector,
    }
    return prepared


def apply_saas_tier_upgrade(payment_id: str, supabase=None) -> dict:
    """UPGRADE 전용 writer. payment SUCCESS 유지. APPLIED 면 no-op."""
    from db.supabase_client import get_supabase

    sb = supabase or get_supabase()
    pay_rows = (
        sb.table("payments").select("*").eq("id", payment_id).limit(1).execute().data
        or []
    )
    if not pay_rows:
        return {"status": "SKIP", "reason": "PAYMENT_NOT_FOUND"}
    pay = pay_rows[0]
    if (pay.get("payment_type") or "").upper() != "UPGRADE":
        return {"status": "SKIP", "reason": "NOT_UPGRADE"}

    tr_rows = (
        sb.table("saas_tier_upgrade_transitions")
        .select("*")
        .eq("payment_id", payment_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not tr_rows:
        _mark_apply_failed(sb, None, payment_id, "TRANSITION_NOT_FOUND")
        return {"status": "APPLY_FAILED", "code": "TRANSITION_NOT_FOUND"}
    tr = tr_rows[0]
    if (tr.get("status") or "").upper() == "APPLIED":
        return {"status": "APPLIED", "noop": True, "transition_id": tr.get("id")}

    try:
        _apply_contract(sb, tr, pay)
        _apply_subscription(sb, tr)
        now = now_iso()
        sb.table("saas_tier_upgrade_transitions").update(
            {
                "status": "APPLIED",
                "last_error": None,
                "applied_at": now,
                "updated_at": now,
            }
        ).eq("id", tr["id"]).execute()
        return {"status": "APPLIED", "noop": False, "transition_id": tr.get("id")}
    except Exception as e:  # noqa: BLE001
        code = getattr(e, "code", None) or "APPLY_FAILED"
        log.error("tier upgrade apply failed payment=%s: %s", payment_id, e)
        _mark_apply_failed(sb, tr.get("id"), payment_id, f"{code}: {e}")
        return {"status": "APPLY_FAILED", "code": code}


def _reject_if_prepared_attempt_open(
    supabase,
    *,
    company_id,
    contract_id,
    entity_type,
    entity_id,
    target_plan_code,
) -> None:
    """동일 대상 PREPARED attempt 가 있으면 새 PENDING 생성 금지. 조회 실패는 fail-closed."""
    try:
        res = (
            supabase.table("saas_tier_upgrade_transitions")
            .select("id")
            .eq("company_id", company_id)
            .eq("contract_id", contract_id)
            .eq("entity_type", entity_type)
            .eq("entity_id", entity_id)
            .eq("target_plan_code", target_plan_code)
            .eq("status", "PREPARED")
            .limit(1)
            .execute()
        )
        existing = res.data
    except Exception as e:  # noqa: BLE001
        log.error("tier upgrade pending lookup failed: %s", e)
        raise TierUpgradeError(
            "TRANSITION_PERSIST_FAILED",
            "진행 중인 추가결제를 확인하지 못해 결제를 진행할 수 없습니다.",
        ) from e
    if existing is None:
        raise TierUpgradeError(
            "TRANSITION_PERSIST_FAILED",
            "진행 중인 추가결제를 확인하지 못해 결제를 진행할 수 없습니다.",
        )
    if existing:
        raise TierUpgradeError(
            "TIER_UPGRADE_ALREADY_PENDING",
            "이미 진행 중인 추가결제가 있습니다.",
        )


def _assert_price_contract(plan: dict) -> None:
    unit = (plan.get("billing_unit") or "").strip().upper()
    if unit != "MONTHLY":
        raise TierUpgradeError("UNSUPPORTED_PRICE_CONTRACT", "월 과금 플랜만 업그레이드할 수 있습니다.")
    vat_included = plan.get("vat_included")
    if vat_included not in (False, 0):
        raise TierUpgradeError("UNSUPPORTED_PRICE_CONTRACT", "부가세 별도 플랜만 업그레이드할 수 있습니다.")
    try:
        rate = float(plan.get("vat_rate"))
    except (TypeError, ValueError):
        raise TierUpgradeError("UNSUPPORTED_PRICE_CONTRACT", "부가세율이 올바르지 않습니다.") from None
    if abs(rate - _EXPECTED_VAT_RATE) > 1e-9:
        raise TierUpgradeError("UNSUPPORTED_PRICE_CONTRACT", "부가세율이 올바르지 않습니다.")


def _money(raw) -> int:
    try:
        value = int(round(float(raw)))
    except (TypeError, ValueError):
        raise TierUpgradeError("INVALID_UPGRADE_DELTA", "플랜 금액을 읽을 수 없습니다.") from None
    return value


def _snapshot_active_subscription(supabase, company_id) -> Optional[dict]:
    rows = (
        supabase.table("subscriptions")
        .select("id, plan_code, plan_name, amount, supply_amount, vat_amount, billing_cycle, status")
        .eq("company_id", company_id)
        .eq("status", "ACTIVE")
        .execute()
        .data
        or []
    )
    if len(rows) >= 2:
        raise TierUpgradeError(
            "AMBIGUOUS_ACTIVE_SUBSCRIPTION",
            "활성 구독이 2건 이상입니다.",
        )
    if not rows:
        return None
    row = rows[0]
    return {
        "id": row.get("id"),
        "plan_code": row.get("plan_code"),
        "plan_name": row.get("plan_name"),
        "amount": row.get("amount"),
        "supply_amount": row.get("supply_amount"),
        "vat_amount": row.get("vat_amount"),
        "billing_cycle": row.get("billing_cycle"),
        "status": row.get("status"),
    }


def _apply_contract(sb, tr: dict, pay: dict) -> None:
    cid = tr.get("contract_id")
    rows = (
        sb.table("contracts")
        .select("id, plan_code, start_date, end_date, contract_amount, vat_amount, total_amount, paid_amount")
        .eq("id", cid)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise TierUpgradeError("CONTRACT_STATE_DRIFT", "계약을 찾을 수 없습니다.")
    contract = rows[0]
    current_code = (contract.get("plan_code") or "").strip().upper()
    from_code = (tr.get("from_plan_code") or "").strip().upper()
    target_code = (tr.get("target_plan_code") or "").strip().upper()
    if current_code not in {from_code, target_code}:
        raise TierUpgradeError("CONTRACT_STATE_DRIFT", "계약 플랜이 업그레이드 대상과 다릅니다.")

    now = now_iso()
    sb.table("contracts").update(
        {
            "plan_code": tr["target_plan_code"],
            "contract_amount": tr["target_supply_amount"],
            "vat_amount": tr["target_vat_amount"],
            "total_amount": tr["target_total_amount"],
            "paid_amount": tr["delta_total_amount"],
            "paid_at": pay.get("paid_at") or now,
            "status_code": "ACTIVE",
            "is_active": True,
            "updated_at": now,
        }
    ).eq("id", cid).execute()


def _apply_subscription(sb, tr: dict) -> None:
    snap = tr.get("subscription_snapshot")
    sub_id = tr.get("subscription_id")
    if not sub_id and not snap:
        return
    if not sub_id:
        return
    rows = (
        sb.table("subscriptions")
        .select("id, plan_code, plan_name, amount, supply_amount, vat_amount, billing_cycle, status")
        .eq("id", sub_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise TierUpgradeError("SUBSCRIPTION_STATE_DRIFT", "구독을 찾을 수 없습니다.")
    live = rows[0]
    if snap:
        for key in ("plan_code", "amount", "supply_amount", "vat_amount", "status"):
            if _norm(live.get(key)) != _norm(snap.get(key)):
                raise TierUpgradeError(
                    "SUBSCRIPTION_STATE_DRIFT",
                    "구독 상태가 준비 시점과 다릅니다.",
                )
    now = now_iso()
    sb.table("subscriptions").update(
        {
            "plan_code": tr["target_plan_code"],
            "plan_name": tr.get("target_plan_name") or tr["target_plan_code"],
            "supply_amount": tr["target_supply_amount"],
            "vat_amount": tr["target_vat_amount"],
            "amount": tr["target_total_amount"],
            "updated_at": now,
        }
    ).eq("id", sub_id).execute()


def _norm(value: Any):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    return str(value).strip().upper() if isinstance(value, str) else value


def _mark_apply_failed(sb, transition_id, payment_id, error: str) -> None:
    now = now_iso()
    patch = {"status": "APPLY_FAILED", "last_error": error[:1000], "updated_at": now}
    q = sb.table("saas_tier_upgrade_transitions").update(patch)
    if transition_id:
        q.eq("id", transition_id).execute()
    else:
        q.eq("payment_id", payment_id).execute()
