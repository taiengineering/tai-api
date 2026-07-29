"""고객360 통합 집계 서비스 (WO-6 Customer360 + WO-9B 사업장 축).

Goal: G-ms4je4z3-33eada (구축 이어받기 G-ms5pdquz-9e76e5)
- 회사 1건 기준으로 시설·회원·결제·구독·진단·크레딧·세금계산서·환불·계약·문의·감사를 한 번에 집계.
- 원천 읽기만(어드민 DB 복제 없음). credit_svc.balance 재사용.
- soft delete 반영: factories/users/contacts는 deleted_at IS NULL 기준.
- WO-9B: get_factory_billing — 사업장별 구독·과금 산정(과금=사업장 수 비례).

[2026-07-29 P1-1/P1-2 CRM 개통]
- payments 에 최근 건별 목록(recent) 추가.
- contracts(계약)·inquiries(문의) 이력 블록 추가 — CRM "한 화면에서 결제·문의·계약" 요건.
- onboarding: WO-17 onboarding_svc.get_checklist 실연결(기존 None 하드코딩 제거).
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

    # 3) 결제 요약 + 최근 건별(recent, 최신순 10)
    pays = (
        supabase.table("payments")
        .select("id, total_amount, status_code, product_type, plan_code, pg_method, paid_at, created_at")
        .eq("company_id", company_id).order("created_at", desc=True).execute()
    ).data or []
    success_pays = [p for p in pays if p.get("status_code") == "SUCCESS"]
    paid_dates = [p["paid_at"] for p in success_pays if p.get("paid_at")]
    payments_summary = {
        "count": len(pays),
        "success_count": len(success_pays),
        "total_amount": sum(int(p["total_amount"] or 0) for p in success_pays),
        "last_paid_at": max(paid_dates) if paid_dates else None,
        "recent": pays[:10],
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

    # 10) 온보딩 (WO-17 onboarding_svc 실연결)
    try:
        from services.onboarding_svc import get_checklist
        onboarding = get_checklist(company_id)
    except Exception as e:  # noqa: BLE001
        log.warning("[C360] onboarding 조회 실패: %s", e)
        onboarding = None

    # 11) 사업장 과금 요약 (WO-9B — 과금=사업장 수 비례)
    billing = factory_billing_summary(company_id)

    # 12) 계약 이력 (CRM 축)
    contract_rows = (
        supabase.table("contracts")
        .select("id, contract_no, service_type, plan_code, status_code, total_amount, "
                "start_date, end_date, is_active, paid_at, created_at")
        .eq("company_id", company_id).order("created_at", desc=True).execute()
    ).data or []
    contracts = {
        "count": len(contract_rows),
        "active_count": len([c for c in contract_rows if c.get("is_active")]),
        "items": contract_rows[:20],
    }

    # 13) 문의 이력 (CRM 축)
    inquiry_rows = (
        supabase.table("inquiries")
        .select("id, no, category, title, status, priority, created_at, replied_at")
        .eq("company_id", company_id).order("created_at", desc=True).execute()
    ).data or []
    unanswered = len([q for q in inquiry_rows if (q.get("status") or "").upper() != "ANSWERED"])
    inquiries = {
        "count": len(inquiry_rows),
        "unanswered": unanswered,
        "items": inquiry_rows[:20],
    }

    return {
        "company": company,
        "counts": counts,
        "payments": payments_summary,
        "subscription": subscription,
        "diagnosis": diagnosis,
        "credit_balance": credit_balance,
        "invoices": invoices,
        "refunds": refunds_summary,
        "contracts": contracts,
        "inquiries": inquiries,
        "recent_audit": recent_audit,
        "onboarding": onboarding,
        "billing": billing,
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


# ── WO-9B 사업장 축 (과금=사업장 수 비례) ────────────────────────────
def factory_billing_summary(company_id: str) -> Dict[str, Any]:
    """회사의 사업장 수 기반 과금 집계(요약).

    - 활성 사업장 수, 구독 있는 사업장 수, 월 과금 합계(ACTIVE 구독 amount 합).
    반환 예: {active_factories, subscribed_factories, unsubscribed_factories, monthly_amount}
    """
    supabase = get_supabase()
    active_factories = _count_active("factories", company_id)

    subs = (
        supabase.table("subscriptions")
        .select("factory_id, status, amount")
        .eq("company_id", company_id).execute()
    ).data or []
    active_subs = [s for s in subs if s.get("status") == "ACTIVE"]
    subscribed_factory_ids = {s["factory_id"] for s in active_subs if s.get("factory_id")}
    monthly_amount = sum(int(s.get("amount") or 0) for s in active_subs)

    return {
        "active_factories": active_factories,
        "subscribed_factories": len(subscribed_factory_ids),
        "unsubscribed_factories": max(active_factories - len(subscribed_factory_ids), 0),
        "monthly_amount": monthly_amount,
    }


def get_factory_billing(company_id: str, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    """회사의 사업장별 구독·과금 상세.

    - 사업장 목록(활성) + 각 사업장 plan_code·diagnosis_status·구독 상태/금액.
    - 집계(factory_billing_summary) 동봉.
    """
    supabase = get_supabase()

    comp = supabase.table("companies").select("id, name").eq("id", company_id).limit(1).execute()
    if not comp.data:
        raise Customer360Error(404, "회사를 찾을 수 없습니다.")

    # 활성 사업장 목록
    facs = (
        supabase.table("factories")
        .select("id, name, site_code, plan_code, diagnosis_status, "
                "legal_applicable_count, last_diagnosis_at, is_active")
        .eq("company_id", company_id).is_("deleted_at", "null")
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1).execute()
    ).data or []

    # 사업장별 구독 매핑
    subs = (
        supabase.table("subscriptions")
        .select("factory_id, status, plan_code, plan_name, amount, next_billing_at")
        .eq("company_id", company_id).execute()
    ).data or []
    sub_by_factory: Dict[str, Dict[str, Any]] = {}
    for s in subs:
        fid = s.get("factory_id")
        if fid and (fid not in sub_by_factory or s.get("status") == "ACTIVE"):
            sub_by_factory[fid] = s

    items = []
    for f in facs:
        sub = sub_by_factory.get(f["id"])
        items.append({
            "factory_id": f["id"],
            "name": f.get("name"),
            "site_code": f.get("site_code"),
            "plan_code": f.get("plan_code"),
            "diagnosis_status": f.get("diagnosis_status"),
            "legal_applicable_count": f.get("legal_applicable_count"),
            "last_diagnosis_at": f.get("last_diagnosis_at"),
            "subscription": {
                "status": sub.get("status") if sub else None,
                "plan_code": sub.get("plan_code") if sub else None,
                "plan_name": sub.get("plan_name") if sub else None,
                "amount": sub.get("amount") if sub else None,
                "next_billing_at": sub.get("next_billing_at") if sub else None,
            } if sub else None,
        })

    return {
        "company_id": company_id,
        "summary": factory_billing_summary(company_id),
        "factories": items,
        "limit": limit,
        "offset": offset,
    }
