"""고객360 통합 집계 서비스 (WO-6 Customer360).

Goal: G-ms4je4z3-33eada
- 회사 1건 기준으로 시설·회원·결제·구독·진단·크레딧·세금계산서·환불·감사를 한 번에 집계.
- 원천 읽기만(어드민 DB 복제 없음). credit_svc.balance 재사용.
- soft delete 반영: factories/users/contacts는 deleted_at IS NULL 기준.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase
from services import credit_svc

log = logging.getLogger(__name__)


class Customer360Error(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _count_active(table: str, company_id: str) -> int:
    """deleted_at IS NULL 활성 건수."""
    res = (
        get_supabase().table(table).select("id", count="exact")
        .eq("company_id", company_id).is_("deleted_at", "null").execute()
    )
    return res.count or 0


def get_summary(company_id: str, audit_limit: int = 10) -> Dict[str, Any]:
    supabase = get_supabase()

    # 1) 회사 상세
    comp = supabase.table("companies").select("*").eq("id", company_id).limit(1).execute()
    if not comp.data:
        raise Customer360Error(404, "회사를 찾을 수 없습니다.")
    company = comp.data[0]

    # 2) 카운트 (soft delete 반영)
    counts = {
        "factories": _count_active("factories", company_id),
        "users": _count_active("users", company_id),
        "contacts": _count_active("company_contacts", company_id),
    }

    # 3) 결제 요약
    pays = (
        supabase.table("payments")
        .select("id, total_amount, status_code, paid_at")
        .eq("company_id", company_id).execute()
    ).data or []
    success_pays = [p for p in pays if p.get("status_code") == "SUCCESS"]
    paid_dates = [p["paid_at"] for p in success_pays if p.get("paid_at")]
    payments_summary = {
        "count": len(pays),
        "success_count": len(success_pays),
        "total_amount": sum(int(p["total_amount"] or 0) for p in success_pays),
        "last_paid_at": max(paid_dates) if paid_dates else None,
    }
    payment_ids = [p["id"] for p in pays]

    # 4) 구독 상태 (가장 최근)
    subs = (
        supabase.table("subscriptions")
        .select("status, plan_code, product_type, created_at")
        .eq("company_id", company_id).order("created_at", desc=True).execute()
    ).data or []
    subscription = {
        "count": len(subs),
        "status": subs[0]["status"] if subs else None,
        "plan": subs[0].get("plan_code") if subs else None,
        "product_type": subs[0].get("product_type") if subs else None,
    }

    # 5) 진단 이력
    diags = (
        supabase.table("diagnosis_purchases")
        .select("id, price, paid_at")
        .eq("company_id", company_id).execute()
    ).data or []
    diag_dates = [d["paid_at"] for d in diags if d.get("paid_at")]
    diagnosis = {
        "count": len(diags),
        "last_paid_at": max(diag_dates) if diag_dates else None,
    }

    # 6) 크레딧 잔액 (credit_svc 재사용)
    try:
        credit_balance = credit_svc.balance(company_id)
    except Exception as e:  # noqa: BLE001
        log.warning("[C360] credit balance 실패: %s", e)
        credit_balance = 0

    # 7) 세금계산서/현금영수증 요약
    invs = (
        supabase.table("tax_invoices")
        .select("status, doc_type")
        .eq("company_id", company_id).execute()
    ).data or []
    invoices = {
        "issued": len([i for i in invs if i.get("status") == "ISSUED"]),
        "cancelled": len([i for i in invs if i.get("status") == "CANCELLED"]),
        "total": len(invs),
    }

    # 8) 환불 요약 (payments 경유)
    refunds_summary = {"count": 0, "total": 0}
    if payment_ids:
        refs = (
            supabase.table("refunds")
            .select("amount, status")
            .in_("payment_id", payment_ids).eq("status", "DONE").execute()
        ).data or []
        refunds_summary = {
            "count": len(refs),
            "total": sum(int(r["amount"] or 0) for r in refs),
        }

    # 9) 최근 감사 (이 회사 + 관련 결제)
    recent_audit = _recent_audit(company_id, payment_ids, audit_limit)

    # 10) 온보딩 (WO-17 전까지 null)
    onboarding = None

    return {
        "company": company,
        "counts": counts,
        "payments": payments_summary,
        "subscription": subscription,
        "diagnosis": diagnosis,
        "credit_balance": credit_balance,
        "invoices": invoices,
        "refunds": refunds_summary,
        "recent_audit": recent_audit,
        "onboarding": onboarding,
    }


def _recent_audit(company_id: str, payment_ids: List[str], limit: int) -> List[Dict[str, Any]]:
    """admin_ops_audit_logs에서 이 회사(company_id) 또는 관련 결제(payment_id) 최근 건."""
    try:
        supabase = get_supabase()
        ids = [company_id] + (payment_ids or [])
        res = (
            supabase.table("admin_ops_audit_logs")
            .select("id, action, entity_type, entity_id, created_at")
            .in_("entity_id", ids)
            .order("created_at", desc=True)
            .limit(limit).execute()
        )
        return res.data or []
    except Exception as e:  # noqa: BLE001
        log.warning("[C360] audit 조회 실패: %s", e)
        return []
