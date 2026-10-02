"""Member Subscription Service — WO-COMM-V3-07C.

GET  /me/commercial/subscription  — RS1 subscription 조회
POST /me/commercial/subscription/cancel — RS1 구독 해지

Authority: company_id = auth token 파생.
Subscription 연결: current contract → payments.contract_id → payments.subscription_id.
Client subscription_id input = 0.
Remote BillKey revoke (INIAPI) = 0 (현재 운영 cancel semantics 보존).
DB write (cancel 외) = 0.
Scheduler/billing engine 변경 = 0.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from services.time import now_kst


class MemberSubscriptionError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 422) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


_PAYMENT_COLS = "id, subscription_id, contract_id, product_type, status_code, charge_cycle"
_SUB_COLS = (
    "id, company_id, user_id, product_type, status, "
    "billing_key_id, next_billing_at, last_billed_at, created_at, updated_at"
)
_BK_COLS = "id, status"


def _resolve_subscription_by_contract(
    supabase,
    contract_id: str,
    company_id: str,
) -> Optional[Dict[str, Any]]:
    """contract_id → cycle-1 success payment → subscription_id → subscription 1건.

    Returns subscription row 또는 None.
    Ambiguous (2건 이상) 시 MemberSubscriptionError(SUBSCRIPTION_AMBIGUOUS) 발생.
    Ownership 불일치 시 MemberSubscriptionError(SUBSCRIPTION_COMPANY_MISMATCH) 발생.
    """
    pay_res = (
        supabase.table("payments")
        .select(_PAYMENT_COLS)
        .eq("contract_id", contract_id)
        .eq("product_type", "SAAS")
        .in_("status_code", ["PAID", "SUCCESS"])
        .eq("charge_cycle", 1)
        .limit(10)
        .execute()
    )
    rows = [r for r in (pay_res.data or []) if r.get("subscription_id")]
    if not rows:
        return None

    subscription_ids = list({str(r["subscription_id"]) for r in rows if r.get("subscription_id")})
    if len(subscription_ids) > 1:
        raise MemberSubscriptionError(
            "SUBSCRIPTION_AMBIGUOUS",
            "복수의 정기결제 이력이 있습니다. 담당자에게 문의해 주세요.",
            409,
        )

    subscription_id = subscription_ids[0]
    sub_res = (
        supabase.table("subscriptions")
        .select(_SUB_COLS)
        .eq("id", subscription_id)
        .limit(1)
        .execute()
    )
    sub = (sub_res.data or [None])[0]
    if sub is None:
        return None

    if str(sub.get("company_id") or "") != str(company_id):
        raise MemberSubscriptionError(
            "SUBSCRIPTION_COMPANY_MISMATCH",
            "이용계약과 정기결제 소유자가 일치하지 않습니다.",
            403,
        )

    return sub


def _cancel_subscription_local(supabase, subscription: Dict[str, Any]) -> None:
    """Local cancel mutation — DB 상태 변경만. Remote INIAPI 호출 없음.

    subscriptions: status=CANCELLED, next_billing_at=NULL, ended_at=now, cancelled_at=now
    billing_keys:  status=REVOKED (billing_key_id 있을 때)
    """
    now = now_kst()
    sub_id = str(subscription["id"])

    supabase.table("subscriptions").update({
        "status": "CANCELLED",
        "cancelled_at": now,
        "cancel_reason": "사용자 요청",
        "next_billing_at": None,
        "ended_at": now,
        "updated_at": now,
    }).eq("id", sub_id).execute()

    billing_key_id = subscription.get("billing_key_id")
    if billing_key_id:
        supabase.table("billing_keys").update({
            "status": "REVOKED",
            "revoked_at": now,
            "revoke_reason": "사용자 요청",
            "updated_at": now,
        }).eq("id", str(billing_key_id)).execute()


def get_member_subscription(
    supabase,
    company_id: Optional[str],
    contract_id: Optional[str],
    payment_months: Optional[int],
) -> Dict[str, Any]:
    """RS1 subscription 조회.

    payment_months != 1 → state=NOT_RECURRING, subscription=null.
    payment_months = 1  → contract → payments → subscription 연결 시도.

    Returns:
        state: ACTIVE | NOT_RECURRING | NOT_FOUND | ERROR
        subscription: subscription row 또는 null
    """
    if not company_id or not contract_id:
        return {"state": "NOT_FOUND", "subscription": None}

    if payment_months != 1:
        return {"state": "NOT_RECURRING", "subscription": None}

    try:
        sub = _resolve_subscription_by_contract(supabase, contract_id, company_id)
    except MemberSubscriptionError as exc:
        return {"state": "ERROR", "error_code": exc.code, "subscription": None}

    if sub is None:
        return {"state": "NOT_FOUND", "subscription": None}

    sub_status = str(sub.get("status") or "")
    if sub_status not in {"ACTIVE", "PAUSED", "CANCELLED", "FAILED"}:
        return {"state": "NOT_FOUND", "subscription": None}

    return {
        "state": sub_status if sub_status in {"ACTIVE", "PAUSED"} else sub_status,
        "subscription": {
            "id": str(sub["id"]),
            "status": sub_status,
            "next_billing_at": sub.get("next_billing_at"),
            "last_billed_at": sub.get("last_billed_at"),
            "has_active_billing_key": bool(sub.get("billing_key_id")),
            "created_at": sub.get("created_at"),
        },
    }


def cancel_member_subscription(
    supabase,
    company_id: Optional[str],
    contract_id: Optional[str],
    payment_months: Optional[int],
) -> Dict[str, Any]:
    """RS1 구독 해지. 다음 자동결제 중단.

    contract 활성 상태 변경 없음. end_date 변경 없음. 환불 없음.
    Returns cancelled subscription state.
    """
    if not company_id or not contract_id:
        raise MemberSubscriptionError(
            "SUBSCRIPTION_NOT_FOUND",
            "정기결제 이용 계약을 찾을 수 없습니다.",
            404,
        )

    if payment_months != 1:
        raise MemberSubscriptionError(
            "SUBSCRIPTION_NOT_RECURRING",
            "정기결제 계약이 아닙니다.",
            422,
        )

    sub = _resolve_subscription_by_contract(supabase, contract_id, company_id)
    if sub is None:
        raise MemberSubscriptionError(
            "SUBSCRIPTION_NOT_FOUND",
            "정기결제 정보를 찾을 수 없습니다.",
            404,
        )

    sub_status = str(sub.get("status") or "")
    if sub_status == "CANCELLED":
        raise MemberSubscriptionError(
            "SUBSCRIPTION_ALREADY_CANCELLED",
            "이미 해지된 정기결제입니다.",
            409,
        )

    if sub_status not in {"ACTIVE", "PAUSED"}:
        raise MemberSubscriptionError(
            "SUBSCRIPTION_NOT_CANCELLABLE",
            f"해지할 수 없는 상태입니다: {sub_status}",
            409,
        )

    _cancel_subscription_local(supabase, sub)

    return {
        "cancelled": True,
        "subscription_id": str(sub["id"]),
        "status": "CANCELLED",
    }
