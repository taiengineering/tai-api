"""
WO-COMM-V3-RECURRING-SCHEDULER-TRIGGER-001
Orchestration service: selects due SAAS subscriptions, validates pre-charge
guards, and delegates to the existing _charge_subscription_once path.
Does NOT contain billing logic and does NOT duplicate INICIS charge code.
"""
from __future__ import annotations

import logging
from typing import Any

from services.time import now_kst, serialize_business_datetime

log = logging.getLogger(__name__)

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100


def run_due_saas_recurring_billing(payload: dict) -> dict:
    """
    Entry for direct://saas_recurring_billing.
    Default dry_run=True — explicit {"dry_run": false} required to charge.
    """
    dry_run: bool = bool(payload.get("dry_run", True))
    limit: int = min(int(payload.get("limit", _DEFAULT_LIMIT)), _MAX_LIMIT)

    from db.supabase_client import get_supabase
    supabase = get_supabase()

    now_iso = serialize_business_datetime(now_kst())

    # §4: bounded due candidate query — ordered by next_billing_at ASC, id ASC
    res = (
        supabase.table("subscriptions")
        .select("*")
        .eq("status", "ACTIVE")
        .eq("product_type", "SAAS")
        .not_.is_("next_billing_at", "null")
        .lte("next_billing_at", now_iso)
        .not_.is_("billing_key_id", "null")
        .order("next_billing_at", desc=False)
        .order("id", desc=False)
        .limit(limit)
        .execute()
    )
    candidates = res.data or []

    scanned = len(candidates)
    eligible_count = 0
    charged_success = 0
    charged_failed = 0
    skipped = 0
    errors = 0
    items: list[dict] = []

    for sub in candidates:
        sub_id = sub["id"]
        item: dict[str, Any] = {
            "subscription_id": sub_id,
            "next_billing_at": sub.get("next_billing_at"),
        }

        guard = _pre_charge_guard(supabase, sub, now_iso)
        if not guard["eligible"]:
            item["eligible"] = False
            item["reason_code"] = guard["reason_code"]
            skipped += 1
            items.append(item)
            continue

        item["eligible"] = True
        eligible_count += 1

        if dry_run:
            item["reason_code"] = "DRY_RUN"
            items.append(item)
            continue

        # §8: live — existing charge path called exactly once per candidate
        try:
            charge = _do_charge(
                supabase,
                sub,
                guard["billing_key_row"],
                guard["charge_cycle"],
            )
            if charge["success"]:
                charged_success += 1
                item["charged"] = True
                item["payment_id"] = charge["payment_id"]
            else:
                charged_failed += 1
                item["charged"] = False
                item["payment_id"] = charge.get("payment_id")
                item["reason_code"] = "CHARGE_FAILED"
        except Exception as exc:
            # §8: per-item exception must not abort batch
            errors += 1
            item["charged"] = False
            item["reason_code"] = "EXCEPTION"
            item["error"] = str(exc)[:200]
            log.exception("[SAAS_RECURRING] sub=%s exception: %s", sub_id, exc)

        items.append(item)

    return {
        "dry_run": dry_run,
        "scanned": scanned,
        "eligible": eligible_count,
        "charged_success": charged_success,
        "charged_failed": charged_failed,
        "skipped": skipped,
        "errors": errors,
        "items": items,
    }


def _pre_charge_guard(supabase, sub: dict, now_iso: str) -> dict:
    """
    §6 fail-closed guard. All checks must pass before any INICIS call.
    Returns {"eligible": bool, "reason_code": str, ...}.
    """
    sub_id = sub["id"]

    # §6.1: re-validate subscription state
    if sub.get("status") != "ACTIVE":
        return {"eligible": False, "reason_code": "SUB_NOT_ACTIVE"}
    if sub.get("product_type") != "SAAS":
        return {"eligible": False, "reason_code": "SUB_NOT_SAAS"}
    if not sub.get("next_billing_at"):
        return {"eligible": False, "reason_code": "NEXT_BILLING_AT_MISSING"}
    if sub["next_billing_at"] > now_iso:
        return {"eligible": False, "reason_code": "NOT_YET_DUE"}
    if not sub.get("billing_key_id"):
        return {"eligible": False, "reason_code": "BILLING_KEY_ID_MISSING"}

    # §6.2: billing key — must exist and be ACTIVE
    bk_res = (
        supabase.table("billing_keys")
        .select("*")
        .eq("id", sub["billing_key_id"])
        .limit(1)
        .execute()
    )
    if not bk_res.data:
        return {"eligible": False, "reason_code": "BILLING_KEY_NOT_FOUND"}
    bk = bk_res.data[0]
    if bk.get("status") != "ACTIVE":
        return {"eligible": False, "reason_code": "BILLING_KEY_INACTIVE"}

    # §6.3: V3 linkage — cycle-1 success + quote_id + contract_id
    pays_res = (
        supabase.table("payments")
        .select("id,charge_cycle,status_code,quote_id,contract_id")
        .eq("subscription_id", sub_id)
        .execute()
    )
    all_pays = pays_res.data or []
    cycle1_ok = [
        p for p in all_pays
        if p.get("charge_cycle") == 1 and p.get("status_code") in ("PAID", "SUCCESS")
    ]
    if not cycle1_ok:
        return {"eligible": False, "reason_code": "CYCLE1_PAYMENT_NOT_FOUND"}

    init_pay = cycle1_ok[0]
    if not init_pay.get("quote_id"):
        return {"eligible": False, "reason_code": "QUOTE_ID_MISSING"}
    if not init_pay.get("contract_id"):
        return {"eligible": False, "reason_code": "CONTRACT_ID_MISSING"}

    contract_id = init_pay["contract_id"]

    # §6.4: contract state
    ct_res = (
        supabase.table("contracts")
        .select("*")
        .eq("id", contract_id)
        .limit(1)
        .execute()
    )
    if not ct_res.data:
        return {"eligible": False, "reason_code": "CONTRACT_NOT_FOUND"}
    ct = ct_res.data[0]
    if ct.get("status_code") != "ACTIVE":
        return {"eligible": False, "reason_code": "CONTRACT_NOT_ACTIVE"}
    if ct.get("service_type") != "SAAS":
        return {"eligible": False, "reason_code": "CONTRACT_NOT_SAAS"}
    if not ct.get("is_active"):
        return {"eligible": False, "reason_code": "CONTRACT_IS_ACTIVE_FALSE"}
    if not ct.get("end_date"):
        return {"eligible": False, "reason_code": "CONTRACT_END_DATE_MISSING"}

    charge_cycle = len(all_pays) + 1

    return {
        "eligible": True,
        "reason_code": "OK",
        "billing_key_row": bk,
        "charge_cycle": charge_cycle,
    }


def _do_charge(
    supabase,
    sub: dict,
    billing_key_row: dict,
    charge_cycle: int,
) -> dict:
    """Delegates to existing charge path. Contains no billing logic."""
    from routers.payment_billing import _charge_subscription_once

    result = _charge_subscription_once(
        supabase,
        subscription=sub,
        billing_key_row=billing_key_row,
        charge_cycle=charge_cycle,
        is_recurring=True,
    )

    # §5: V3 SAAS success → renewal chain (same path as billing_charge endpoint)
    if result.get("success") and sub.get("product_type") == "SAAS":
        try:
            from services.payment_post_process import on_payment_success_sync
            on_payment_success_sync(result["payment_id"])
        except Exception as e:
            log.error(
                "[SAAS_RECURRING] on_payment_success_sync failed payment=%s: %s",
                result.get("payment_id"),
                e,
            )

    return result
