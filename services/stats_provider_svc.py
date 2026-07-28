"""경영 지표 집계 서비스 (WO-14 StatsProvider).

Goal: G-ms4je4z3-33eada
- 매출·구독(MRR)·결제 건전성·전환 지표. admin_stats(자산 수)와 상보.
- 결제 상태(system_codes payment_status): PENDING/SUCCESS/FAILED/CANCELLED.
- 원천 읽기만. 각 지표 오류 격리.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

_PAGE = 1000


def _fetch_all(table: str, select: str, build=None) -> List[Dict[str, Any]]:
    """페이지네이션으로 전량 조회(집계용)."""
    out: List[Dict[str, Any]] = []
    offset = 0
    try:
        while True:
            q = get_supabase().table(table).select(select)
            if build:
                q = build(q)
            res = q.range(offset, offset + _PAGE - 1).execute()
            rows = res.data or []
            out.extend(rows)
            if len(rows) < _PAGE:
                break
            offset += _PAGE
    except Exception as e:  # noqa: BLE001
        log.warning("[STATS] fetch 실패 %s: %s", table, e)
    return out


def revenue() -> Dict[str, Any]:
    """매출: 결제 성공 합 + 상품유형별 + 진단 매출."""
    pays = _fetch_all("payments", "total_amount, status_code, product_type",
                      lambda q: q.eq("status_code", "SUCCESS"))
    total = sum(int(p.get("total_amount") or 0) for p in pays)
    by_product: Dict[str, int] = {}
    for p in pays:
        key = p.get("product_type") or "UNKNOWN"
        by_product[key] = by_product.get(key, 0) + int(p.get("total_amount") or 0)

    diags = _fetch_all("diagnosis_purchases", "price, status",
                       lambda q: q.eq("status", "SUCCESS"))
    diag_total = sum(int(d.get("price") or 0) for d in diags)

    return {
        "total_paid": total,
        "by_product": by_product,
        "diagnosis_revenue": diag_total,
        "diagnosis_count": len(diags),
    }


def subscription_metrics() -> Dict[str, Any]:
    """구독: MRR(ACTIVE amount 합), 활성/해지 수, 상품유형별."""
    subs = _fetch_all("subscriptions", "status, amount, product_type")
    active = [s for s in subs if s.get("status") == "ACTIVE"]
    cancelled = [s for s in subs if s.get("status") in ("CANCELLED", "CANCELED")]
    mrr = sum(int(s.get("amount") or 0) for s in active)
    by_product: Dict[str, int] = {}
    for s in active:
        key = s.get("product_type") or "UNKNOWN"
        by_product[key] = by_product.get(key, 0) + 1
    return {
        "mrr": mrr,
        "active_count": len(active),
        "cancelled_count": len(cancelled),
        "total_subscriptions": len(subs),
        "active_by_product": by_product,
    }


def payment_health() -> Dict[str, Any]:
    """결제 건전성: 성공률·실패·대기."""
    pays = _fetch_all("payments", "status_code")
    success = sum(1 for p in pays if p.get("status_code") == "SUCCESS")
    failed = sum(1 for p in pays if p.get("status_code") == "FAILED")
    pending = sum(1 for p in pays if p.get("status_code") == "PENDING")
    denom = success + failed
    success_rate = round(success / denom * 100, 1) if denom else None
    return {
        "total": len(pays),
        "success": success,
        "failed": failed,
        "pending": pending,
        "success_rate_pct": success_rate,
    }


def conversion() -> Dict[str, Any]:
    """진단→SaaS 전환: 진단 구매 회사 중 SaaS 구독 보유 비율(간접 산출)."""
    diag_companies = {
        d.get("company_id") for d in
        _fetch_all("diagnosis_purchases", "company_id", lambda q: q.eq("status", "SUCCESS"))
        if d.get("company_id")
    }
    saas_companies = {
        s.get("company_id") for s in
        _fetch_all("subscriptions", "company_id, status", lambda q: q.eq("status", "ACTIVE"))
        if s.get("company_id")
    }
    converted = diag_companies & saas_companies
    rate = round(len(converted) / len(diag_companies) * 100, 1) if diag_companies else None
    return {
        "diagnosis_companies": len(diag_companies),
        "converted_to_saas": len(converted),
        "conversion_rate_pct": rate,
    }


def get_stats() -> Dict[str, Any]:
    """경영 지표 종합. 각 지표 오류 격리."""
    out: Dict[str, Any] = {}
    for key, fn in (("revenue", revenue), ("subscription", subscription_metrics),
                    ("payment_health", payment_health), ("conversion", conversion)):
        try:
            out[key] = fn()
        except Exception as e:  # noqa: BLE001
            log.warning("[STATS] %s 실패: %s", key, e)
            out[key] = {"error": str(e)}
    return out
