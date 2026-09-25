"""OBJ13 LINKED_BUSINESS_JOURNEY_SEGMENTS read model.

Canonical business facts from OBJ08B (get_marketing_business_outcomes) reused.
Additional link-presence counts only. No new base predicates.

Fail-closed:
  OBJ08B unavailable → available=False, segments=None
  Any additional query failure → available=False, segments=None
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from services.stats_dashboard_svc import (
    _count_exact_strict,
    _parse_date_token,
    get_marketing_business_outcomes,
)

log = logging.getLogger(__name__)

_BRIDGES: Dict[str, str] = {
    "diagnosis_to_user": "DETERMINISTIC_WHEN_CLAIMED",
    "user_to_company": "DETERMINISTIC_WHEN_PRESENT",
    "user_to_factory": "OPTIONAL_DIRECT_LINK",
    "company_to_factory": "ONE_TO_MANY",
    "user_to_paid_diagnosis_payment": "DETERMINISTIC_WHEN_PRESENT",
    "user_to_subscription": "DETERMINISTIC",
    "subscription_to_payment": "DETERMINISTIC",
    "subscription_to_saas_contract": "NOT_PROVEN",
    "marketing_to_business": "UNLINKED",
}


def get_marketing_journey(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """OBJ13 LINKED_BUSINESS_JOURNEY_SEGMENTS.

    Reuses get_marketing_business_outcomes() for canonical counts.
    Adds link-presence counts (user_id/company_id IS NOT NULL).
    Fail-closed on any DB error.
    """
    outcomes = get_marketing_business_outcomes(date_from=date_from, date_to=date_to)

    from_label = outcomes.get("date_from", "")
    to_label = outcomes.get("date_to", "")

    _unavailable: Dict[str, Any] = {
        "available": False,
        "scope": "LINKED_BUSINESS_JOURNEY_SEGMENTS",
        "date_from": from_label,
        "date_to": to_label,
        "timezone": "Asia/Seoul",
        "segments": None,
        "bridges": _BRIDGES,
        "marketing_link": {"available": False, "reason": "NO_GA4_TAI_IDENTITY_BRIDGE"},
        "business_outcome_attribution": None,
        "cross_source_estimate": None,
        "cohort_joined": False,
        "rates": None,
        "safe_to_sum": False,
    }

    if not outcomes.get("available"):
        return _unavailable

    flows = outcomes["flows"]
    stock = outcomes["current_stock"]

    # Re-derive ISO bounds for link-presence queries (same tokens as OBJ08B uses)
    from_token = date_from or "28daysAgo"
    to_token = date_to or "today"
    from_dt = _parse_date_token(from_token)
    to_dt = _parse_date_token(to_token)
    if from_dt is None or to_dt is None:
        return _unavailable

    from_iso = from_dt.isoformat()
    to_iso = (to_dt + timedelta(days=1)).isoformat()

    try:
        paid_diag_user_linked = _count_exact_strict(
            "payments",
            lambda q: (
                q.eq("product_type", "DIAGNOSIS")
                 .eq("status_code", "SUCCESS")
                 .not_.is_("paid_at", "null")
                 .gte("paid_at", from_iso)
                 .lt("paid_at", to_iso)
                 .not_.is_("user_id", "null")
            ),
        )

        saas_pay_user_linked = _count_exact_strict(
            "payments",
            lambda q: (
                q.like("product_type", "SAAS%")
                 .eq("status_code", "SUCCESS")
                 .not_.is_("paid_at", "null")
                 .gte("paid_at", from_iso)
                 .lt("paid_at", to_iso)
                 .not_.is_("user_id", "null")
            ),
        )

        saas_pay_company_linked = _count_exact_strict(
            "payments",
            lambda q: (
                q.like("product_type", "SAAS%")
                 .eq("status_code", "SUCCESS")
                 .not_.is_("paid_at", "null")
                 .gte("paid_at", from_iso)
                 .lt("paid_at", to_iso)
                 .not_.is_("company_id", "null")
            ),
        )

        sub_user_linked = _count_exact_strict(
            "subscriptions",
            lambda q: q.eq("status", "ACTIVE").not_.is_("user_id", "null"),
        )

        sub_company_linked = _count_exact_strict(
            "subscriptions",
            lambda q: q.eq("status", "ACTIVE").not_.is_("company_id", "null"),
        )

        saas_svc_company_linked = _count_exact_strict(
            "contracts",
            lambda q: (
                q.eq("service_type", "SAAS")
                 .eq("status_code", "ACTIVE")
                 .eq("is_active", True)
                 .not_.is_("company_id", "null")
            ),
        )

    except Exception as e:
        log.warning("[MKT-JOURNEY] linked-count query failed: %s", e)
        return _unavailable

    purchased = flows["paid_diagnosis_purchased"]

    return {
        "available": True,
        "scope": "LINKED_BUSINESS_JOURNEY_SEGMENTS",
        "date_from": from_label,
        "date_to": to_label,
        "timezone": "Asia/Seoul",
        "segments": {
            "diagnosis": {
                "kind": "FLOW_CONTEXT",
                "completed": flows["free_diagnosis_completed"],
                "claimed": flows["free_diagnosis_claimed"],
                "user_linked": flows["free_diagnosis_claimed"],
                "claim_timestamp_available": False,
                "timestamp_basis": "DIAGNOSIS_CREATED_AT",
            },
            "account": {
                "kind": "FLOW",
                "signup_complete": flows["signup_complete"],
                "signup_timestamp_exact": False,
                "timestamp_basis": "USER_ROW_CREATED_AT",
            },
            "paid_diagnosis": {
                "kind": "FLOW",
                "grain": "PAYMENT",
                "purchased": purchased,
                "user_linked": paid_diag_user_linked,
                "user_unlinked": purchased - paid_diag_user_linked,
                "timestamp_basis": "PAID_AT",
            },
            "saas_payment": {
                "kind": "FLOW",
                "grain": "PAYMENT",
                "success": flows["saas_payment_success"],
                "user_linked": saas_pay_user_linked,
                "company_linked": saas_pay_company_linked,
                "timestamp_basis": "PAID_AT",
            },
            "subscription": {
                "kind": "STOCK",
                "grain": "SUBSCRIPTION",
                "active": stock["subscription_active"],
                "user_linked": sub_user_linked,
                "company_linked": sub_company_linked,
                "timestamp_basis": "SNAPSHOT",
            },
            "saas_service": {
                "kind": "STOCK",
                "grain": "CONTRACT",
                "active": stock["saas_service_active"],
                "company_linked": saas_svc_company_linked,
                "timestamp_basis": "SNAPSHOT",
                "factory_mapping": "NOT_PROVEN",
            },
        },
        "bridges": _BRIDGES,
        "marketing_link": {"available": False, "reason": "NO_GA4_TAI_IDENTITY_BRIDGE"},
        "business_outcome_attribution": None,
        "cross_source_estimate": None,
        "cohort_joined": False,
        "rates": None,
        "safe_to_sum": False,
    }
