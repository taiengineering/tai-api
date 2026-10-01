"""
WO-COMM-V3-RECURRING-SCHEDULER-TRIGGER-001 / PATCH-001 / PATCH-002
Orchestration service: selects due SAAS subscriptions, validates pre-charge
guards, and delegates to the existing _charge_subscription_once path.
Does NOT contain billing logic and does NOT duplicate INICIS charge code.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from services.time import now_kst, serialize_business_datetime, TAI_TIMEZONE

log = logging.getLogger(__name__)

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100


class SaasRecurringBillingError(RuntimeError):
    """Raised after batch when post_process_failed > 0 or errors > 0 so monitoring cannot record clean SUCCESS."""
    def __init__(self, summary: dict) -> None:
        self.summary = summary
        super().__init__(
            f"[SAAS_RECURRING] batch completed with failures: "
            f"post_process_failed={summary['post_process_failed']} "
            f"errors={summary['errors']} "
            f"charged_success={summary['charged_success']} "
            f"charged_failed={summary['charged_failed']}"
        )


def build_v3_recurring_charge_context(
    supabase,
    subscription_id: str,
    now: datetime,
) -> dict:
    """
    §PATCH2-B: single fresh read for all monetary authority.
    Returns {"eligible": True, subscription, billing_key_row, contract_id, quote_id, charge_cycle}
    or {"eligible": False, "reason_code": str}.
    """
    # Fresh subscription read
    sub_res = (
        supabase.table("subscriptions")
        .select("*")
        .eq("id", subscription_id)
        .limit(1)
        .execute()
    )
    if not sub_res.data:
        return {"eligible": False, "reason_code": "SUB_VANISHED"}
    sub = sub_res.data[0]

    if sub.get("status") != "ACTIVE":
        return {"eligible": False, "reason_code": "SUB_NOT_ACTIVE"}
    if sub.get("product_type") != "SAAS":
        return {"eligible": False, "reason_code": "SUB_NOT_SAAS"}
    if not sub.get("billing_key_id"):
        return {"eligible": False, "reason_code": "BILLING_KEY_ID_MISSING"}

    # §PATCH2-D: timezone-aware temporal check
    nba = sub.get("next_billing_at")
    if not nba:
        return {"eligible": False, "reason_code": "NEXT_BILLING_AT_MISSING"}
    try:
        nba_dt = datetime.fromisoformat(str(nba))
    except (ValueError, TypeError):
        return {"eligible": False, "reason_code": "NEXT_BILLING_AT_INVALID"}
    if nba_dt.tzinfo is None:
        return {"eligible": False, "reason_code": "NEXT_BILLING_AT_INVALID"}

    # Fresh billing key
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

    # V3 linkage
    pays_res = (
        supabase.table("payments")
        .select("id,charge_cycle,status_code,quote_id,contract_id")
        .eq("subscription_id", subscription_id)
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
    quote_id = init_pay["quote_id"]

    # Contract state
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

    # §PATCH3: Contract boundary temporal authority
    end_val = ct["end_date"]
    try:
        from datetime import date as _date
        end_dt = _date.fromisoformat(str(end_val)) if isinstance(end_val, str) else end_val
        contract_end_boundary = datetime(end_dt.year, end_dt.month, end_dt.day, 0, 0, 0, tzinfo=TAI_TIMEZONE)
    except Exception:
        return {"eligible": False, "reason_code": "CONTRACT_END_DATE_INVALID"}
    contract_due_at = contract_end_boundary - timedelta(days=1)

    if now < contract_due_at:
        return {"eligible": False, "reason_code": "CONTRACT_NOT_DUE"}
    if now >= contract_end_boundary:
        return {"eligible": False, "reason_code": "CONTRACT_EXPIRED_FOR_RECURRING"}

    # §PATCH3: Subscription schedule must match contract due (by instant)
    if nba_dt != contract_due_at:
        return {
            "eligible": False,
            "reason_code": "SCHEDULE_CONTRACT_MISMATCH",
            "subscription_next_billing_at": nba_dt.isoformat(),
            "contract_due_at": contract_due_at.isoformat(),
            "contract_end_boundary": contract_end_boundary.isoformat(),
        }

    # §PATCH2-C: shared cycle helper
    from routers.payment_billing import _v3_cycle_from_pays
    charge_cycle = _v3_cycle_from_pays(all_pays)

    # PENDING guard from already-fetched data
    pending_for_cycle = [
        p for p in all_pays
        if p.get("charge_cycle") == charge_cycle and p.get("status_code") == "PENDING"
    ]
    if pending_for_cycle:
        return {"eligible": False, "reason_code": "PENDING_CYCLE_EXISTS"}

    return {
        "eligible": True,
        "reason_code": "OK",
        "subscription": sub,
        "billing_key_row": bk,
        "contract_id": contract_id,
        "quote_id": quote_id,
        "charge_cycle": charge_cycle,
    }


def run_due_saas_recurring_billing(payload: dict) -> dict:
    """
    Entry for direct://saas_recurring_billing.
    Default dry_run=True — explicit {"dry_run": false} required to charge.
    """
    dry_run: bool = bool(payload.get("dry_run", True))
    limit: int = min(int(payload.get("limit", _DEFAULT_LIMIT)), _MAX_LIMIT)

    from db.supabase_client import get_supabase
    supabase = get_supabase()

    now_kst_dt: datetime = now_kst()
    now_iso: str = serialize_business_datetime(now_kst_dt)

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
    post_process_failed = 0
    skipped = 0
    errors = 0
    items: list[dict] = []

    for sub in candidates:
        sub_id = sub["id"]
        item: dict[str, Any] = {
            "subscription_id": sub_id,
            "next_billing_at": sub.get("next_billing_at"),
        }

        # §PATCH2-B: single fresh read for all monetary authority (dry_run and live)
        ctx = build_v3_recurring_charge_context(supabase, sub_id, now_kst_dt)
        if not ctx["eligible"]:
            item["eligible"] = False
            item["reason_code"] = ctx["reason_code"]
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
                ctx["subscription"],
                ctx["billing_key_row"],
                ctx["charge_cycle"],
                contract_id=ctx["contract_id"],
            )
            if charge["success"] and charge.get("post_process") == "OK":
                charged_success += 1
                item["charged"] = True
                item["payment_id"] = charge["payment_id"]
            elif charge["success"] and charge.get("post_process") == "FAILED":
                # §E state C: monetary succeeded, renewal post-process failed
                post_process_failed += 1
                item["charged"] = True
                item["payment_id"] = charge["payment_id"]
                item["reason_code"] = "POST_PROCESS_FAILED"
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

    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "scanned": scanned,
        "eligible": eligible_count,
        "charged_success": charged_success,
        "charged_failed": charged_failed,
        "post_process_failed": post_process_failed,
        "skipped": skipped,
        "errors": errors,
        "items": items,
    }

    # §PATCH2-F: post-process failures OR errors must not be silently reported as clean SUCCESS
    if post_process_failed > 0 or errors > 0:
        raise SaasRecurringBillingError(summary)

    return summary


def _do_charge(
    supabase,
    sub: dict,
    billing_key_row: dict,
    charge_cycle: int,
    contract_id: str | None = None,
) -> dict:
    """
    Delegates to existing charge path. Contains no billing logic.
    Returns {"success": bool, "post_process": "OK"|"FAILED"|None, "payment_id": str, ...}.
    """
    from routers.payment_billing import _charge_subscription_once

    result = _charge_subscription_once(
        supabase,
        subscription=sub,
        billing_key_row=billing_key_row,
        charge_cycle=charge_cycle,
        is_recurring=True,
    )

    if not result.get("success"):
        return {
            "success": False,
            "post_process": None,
            "payment_id": result.get("payment_id"),
            "result": result.get("result"),
        }

    # §E: V3 SAAS success → renewal chain; post-process failure is a distinct state
    try:
        from services.payment_post_process import on_payment_success_sync
        on_payment_success_sync(result["payment_id"])
        if contract_id:
            from routers.payment_billing import _align_v3_subscription_next_billing_to_contract_end
            _align_v3_subscription_next_billing_to_contract_end(supabase, sub["id"], contract_id)
        return {
            "success": True,
            "post_process": "OK",
            "payment_id": result["payment_id"],
            "result": result.get("result"),
        }
    except Exception as e:
        log.error(
            "[SAAS_RECURRING] on_payment_success_sync failed payment=%s: %s",
            result.get("payment_id"),
            e,
        )
        return {
            "success": True,
            "post_process": "FAILED",
            "post_process_error": str(e)[:200],
            "payment_id": result["payment_id"],
            "result": result.get("result"),
        }
