"""전환크레딧 원장 서비스 (WO-3 CreditLedger).

Goal: G-ms4je4z3-33eada
정책: 진단 유료결제 후 30일 내 SaaS 전환 시 진단 결제액 100% 크레딧.
- grant/apply/balance/grant_from_diagnosis
- apply는 만료 제외·FIFO(오래된 것부터) 차감
- 모든 grant/apply는 audit_svc.record 기록 (best-effort)
- 불변식: 0 <= balance <= amount (DB CHECK + 서비스 로직)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase
from services import audit_svc
from services.payment_helpers import now_iso

log = logging.getLogger(__name__)

_CONVERSION_WINDOW_DAYS = 30


class CreditError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def grant(
    company_id: str,
    amount: int,
    source: str,
    source_ref: Optional[str] = None,
    expires_at: Optional[str] = None,
    created_by: Optional[str] = None,
    memo: Optional[str] = None,
) -> str:
    """크레딧 발행. balance=amount, status=ACTIVE."""
    amount = int(amount)
    if amount <= 0:
        raise CreditError(400, "크레딧 금액이 올바르지 않습니다.")
    if source not in ("DIAGNOSIS_CONVERT", "MANUAL"):
        raise CreditError(400, "source가 올바르지 않습니다.")

    supabase = get_supabase()
    comp = supabase.table("companies").select("id").eq("id", company_id).limit(1).execute()
    if not comp.data:
        raise CreditError(404, "회사를 찾을 수 없습니다.")

    row: Dict[str, Any] = {
        "company_id": company_id,
        "source": source,
        "amount": amount,
        "balance": amount,
        "status": "ACTIVE",
        "created_at": now_iso(),
    }
    if source_ref:
        row["source_ref"] = source_ref
    if expires_at:
        row["expires_at"] = expires_at
    if created_by:
        row["created_by"] = created_by
    if memo:
        row["memo"] = memo

    res = supabase.table("credits").insert(row).execute()
    if not res.data:
        raise CreditError(500, "크레딧 발행 실패")
    credit_id = res.data[0]["id"]

    audit_svc.record(
        "CREDIT_GRANT", "company", entity_id=company_id, actor_id=created_by,
        after={"credit_id": credit_id, "amount": amount, "source": source, "expires_at": expires_at},
    )
    return credit_id


def grant_from_diagnosis(diagnosis_purchase_id: str, created_by: Optional[str] = None) -> str:
    """진단 결제 기준 전환크레딧 발행. expires_at = paid_at + 30일. 중복 발행 방지."""
    supabase = get_supabase()
    dp = (
        supabase.table("diagnosis_purchases")
        .select("id, company_id, price, status, paid_at")
        .eq("id", diagnosis_purchase_id)
        .limit(1)
        .execute()
    )
    if not dp.data:
        raise CreditError(404, "진단 결제 건을 찾을 수 없습니다.")
    row = dp.data[0]
    if not row.get("company_id"):
        raise CreditError(400, "회사 정보가 없는 진단 결제입니다.")
    if not row.get("paid_at"):
        raise CreditError(400, "결제 완료되지 않은 진단입니다.")
    price = int(row.get("price") or 0)
    if price <= 0:
        raise CreditError(400, "유효한 결제액이 없습니다.")

    # 중복 발행 방지 (source_ref UNIQUE로도 막히지만 선제 확인)
    dup = supabase.table("credits").select("id").eq("source_ref", diagnosis_purchase_id).limit(1).execute()
    if dup.data:
        raise CreditError(409, "이미 전환크레딧이 발행된 진단입니다.")

    paid_at = datetime.fromisoformat(str(row["paid_at"]).replace("Z", "+00:00"))
    expires = (paid_at + timedelta(days=_CONVERSION_WINDOW_DAYS)).isoformat()

    return grant(
        company_id=row["company_id"],
        amount=price,
        source="DIAGNOSIS_CONVERT",
        source_ref=diagnosis_purchase_id,
        expires_at=expires,
        created_by=created_by,
        memo=f"진단→SaaS 전환크레딧 (진단결제 {price:,}원, {_CONVERSION_WINDOW_DAYS}일 이내 유효)",
    )


def _active_credits(company_id: str) -> List[Dict[str, Any]]:
    """ACTIVE·미만료 크레딧을 오래된 순(FIFO)으로."""
    supabase = get_supabase()
    res = (
        supabase.table("credits")
        .select("id, balance, expires_at, status, created_at")
        .eq("company_id", company_id)
        .eq("status", "ACTIVE")
        .gt("balance", 0)
        .order("created_at", desc=False)
        .execute()
    )
    now = datetime.now(timezone.utc)
    out = []
    for c in res.data or []:
        exp = c.get("expires_at")
        if exp:
            exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            if exp_dt <= now:
                continue  # 만료분 제외
        out.append(c)
    return out


def balance(company_id: str) -> int:
    """사용 가능한 크레딧 잔액(ACTIVE·미만료 balance 합)."""
    return sum(int(c["balance"]) for c in _active_credits(company_id))


def apply(company_id: str, payment_id: str, amount: int, actor_id: Optional[str] = None) -> Dict[str, Any]:
    """SaaS 결제에 크레딧 FIFO 차감. 반환: {applied, remaining_balance}."""
    amount = int(amount)
    if amount <= 0:
        raise CreditError(400, "차감 금액이 올바르지 않습니다.")

    supabase = get_supabase()
    credits = _active_credits(company_id)
    total_available = sum(int(c["balance"]) for c in credits)
    to_apply = min(amount, total_available)
    if to_apply <= 0:
        return {"applied": 0, "remaining_balance": 0}

    remaining = to_apply
    now = now_iso()
    for c in credits:
        if remaining <= 0:
            break
        cid = c["id"]
        bal = int(c["balance"])
        deduct = min(bal, remaining)
        new_bal = bal - deduct
        patch: Dict[str, Any] = {"balance": new_bal}
        if new_bal == 0:
            patch["status"] = "USED"
            patch["applied_payment_id"] = payment_id
        supabase.table("credits").update(patch).eq("id", cid).execute()
        remaining -= deduct

    remaining_balance = total_available - to_apply
    audit_svc.record(
        "CREDIT_APPLY", "payment", entity_id=payment_id, actor_id=actor_id,
        before={"available_before": total_available},
        after={"company_id": company_id, "applied": to_apply, "remaining_balance": remaining_balance},
    )
    return {"applied": to_apply, "remaining_balance": remaining_balance}
