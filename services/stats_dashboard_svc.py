"""통계 대시보드 집계 서비스 (이커머스 수준 통계).

Goal: G-ms5pdquz-9e76e5
- 하나의 GET /stats/dashboard 로 4축을 반환:
  · 매출·결제: 일별 시계열(시도금액/완료금액/건수) + 상품·플랜·수단·상태 분포
  · 고객·구독: 신규 회사·회원 일별 + 구독 상태·플랜 분포
  · 상품·진단·교육: 진단(세션·구매·요청) 일별 + 총계
  · 마케팅 유입: 익명진단 유입 일별 + 전환 퍼널(익명→요청→구매→결제시도→결제완료)
- 매출 기준: 완료(SUCCESS)=매출, 시도(전체 상태)=참고. 실측상 완료결제가 없어도 시도·상태가 드러난다.
- 집계는 Python(엔진 격리, RLS 무관 service_role). 큰 테이블(anonymous_diagnosis_results)은 페이지네이션.
- 각 소스 오류 격리: 한 소스 실패해도 나머지 반환.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

_PAGE = 1000
_MAX_PAGES = 60  # 안전 상한(최대 6만행)


def _day(iso: Optional[str]) -> Optional[str]:
    """ISO 타임스탬프 → 'YYYY-MM-DD'. 앞 10자만 사용(타임존 파싱 회피)."""
    if not iso or len(iso) < 10:
        return None
    return iso[:10]


def _since_iso(days: int) -> str:
    start = datetime.now(timezone.utc) - timedelta(days=days)
    return start.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _date_axis(days: int) -> List[str]:
    """오늘 포함 최근 days 일의 날짜 라벨(오름차순)."""
    today = datetime.now(timezone.utc).date()
    return [(today - timedelta(days=(days - 1 - i))).isoformat() for i in range(days)]


def _count(table: str, build: Optional[Callable] = None) -> int:
    try:
        q = get_supabase().table(table).select("id", count="exact")
        if build:
            q = build(q)
        return q.execute().count or 0
    except Exception as e:  # noqa: BLE001
        log.warning("[STATS] count 실패 %s: %s", table, e)
        return 0


def _fetch(table: str, cols: str, since: Optional[str] = None,
           date_col: str = "created_at") -> List[Dict[str, Any]]:
    """행 조회. since 있으면 date_col >= since. 1000행씩 페이지네이션."""
    rows: List[Dict[str, Any]] = []
    try:
        sb = get_supabase()
        for page in range(_MAX_PAGES):
            q = sb.table(table).select(cols)
            if since:
                q = q.gte(date_col, since)
            q = q.order(date_col, desc=False).range(page * _PAGE, page * _PAGE + _PAGE - 1)
            batch = q.execute().data or []
            rows.extend(batch)
            if len(batch) < _PAGE:
                break
    except Exception as e:  # noqa: BLE001
        log.warning("[STATS] fetch 실패 %s: %s", table, e)
    return rows


def _daily_count(rows: List[Dict[str, Any]], axis: List[str],
                 date_col: str = "created_at") -> List[int]:
    idx = {d: 0 for d in axis}
    for r in rows:
        d = _day(r.get(date_col))
        if d in idx:
            idx[d] += 1
    return [idx[d] for d in axis]


def _breakdown(rows: List[Dict[str, Any]], key_col: str,
               amount_col: Optional[str] = None) -> List[Dict[str, Any]]:
    agg: Dict[str, Dict[str, int]] = {}
    for r in rows:
        k = r.get(key_col) or "(미지정)"
        a = agg.setdefault(k, {"count": 0, "amount": 0})
        a["count"] += 1
        if amount_col:
            a["amount"] += int(r.get(amount_col) or 0)
    out = [{"key": k, "count": v["count"], "amount": v["amount"]} for k, v in agg.items()]
    out.sort(key=lambda x: (x["amount"] if amount_col else x["count"]), reverse=True)
    return out


# ── 축별 집계 ────────────────────────────────────────────────────────
def _revenue(payments: List[Dict[str, Any]], axis: List[str]) -> Dict[str, Any]:
    """매출·결제. 완료(SUCCESS) 금액=매출, 전체 금액=시도. paid_at 우선(없으면 created_at)."""
    attempted = {d: 0 for d in axis}
    completed = {d: 0 for d in axis}
    count = {d: 0 for d in axis}
    for p in payments:
        d = _day(p.get("created_at"))
        amt = int(p.get("total_amount") or 0)
        if d in attempted:
            attempted[d] += amt
            count[d] += 1
        if p.get("status_code") == "SUCCESS":
            pd = _day(p.get("paid_at")) or d
            if pd in completed:
                completed[pd] += amt
    return {
        "daily": [{"date": d, "attempted": attempted[d], "completed": completed[d], "count": count[d]}
                  for d in axis],
        "by_product": _breakdown(payments, "product_type", "total_amount"),
        "by_plan": _breakdown(payments, "plan_code", "total_amount"),
        "by_method": _breakdown(payments, "payment_method"),
        "by_status": _breakdown(payments, "status_code", "total_amount"),
    }


def get_dashboard(days: int = 90) -> Dict[str, Any]:
    """통계 대시보드 종합."""
    days = max(7, min(int(days or 90), 365))
    axis = _date_axis(days)
    since = _since_iso(days)

    # ── 매출·결제 (payments 는 소량 — 전체 조회 후 기간 필터는 daily 에서) ──
    payments = _fetch("payments", "created_at, paid_at, status_code, total_amount, product_type, plan_code, payment_method", since=since)
    revenue = _revenue(payments, axis)

    # ── 고객·구독 ──
    companies = _fetch("companies", "created_at", since=since)
    users = _fetch("users", "created_at", since=since)
    subs = _fetch("subscriptions", "created_at, status, plan_code")
    customers = {
        "new_companies_daily": [{"date": d, "count": c}
                                for d, c in zip(axis, _daily_count(companies, axis))],
        "new_users_daily": [{"date": d, "count": c}
                            for d, c in zip(axis, _daily_count(users, axis))],
        "subscription_status": _breakdown(subs, "status"),
        "subscription_plan": _breakdown(subs, "plan_code"),
    }

    # ── 상품·진단·교육 ──
    sessions = _fetch("diagnosis_session", "created_at", since=since)
    purchases = _fetch("diagnosis_purchases", "created_at", since=since)
    requests = _fetch("public_diagnosis_requests", "created_at", since=since)
    s_daily = _daily_count(sessions, axis)
    p_daily = _daily_count(purchases, axis)
    r_daily = _daily_count(requests, axis)
    products = {
        "diagnosis_daily": [{"date": axis[i], "sessions": s_daily[i], "purchases": p_daily[i], "requests": r_daily[i]}
                            for i in range(len(axis))],
        "totals": {
            "diagnosis_sessions": _count("diagnosis_session"),
            "diagnosis_purchases": _count("diagnosis_purchases"),
            "public_requests": _count("public_diagnosis_requests"),
            "anonymous_diagnosis": _count("anonymous_diagnosis_results"),
            "education_history": _count("education_history"),
            "inquiries": _count("inquiries"),
        },
    }

    # ── 마케팅 유입 (익명진단 = 사이트 유입) ──
    anon = _fetch("anonymous_diagnosis_results", "created_at", since=since)
    anon_daily = _daily_count(anon, axis)
    marketing = {
        "inflow_daily": [{"date": axis[i], "anon": anon_daily[i], "requests": r_daily[i]}
                         for i in range(len(axis))],
        "funnel": [
            {"stage": "익명진단(사이트 유입)", "count": _count("anonymous_diagnosis_results")},
            {"stage": "진단 요청", "count": _count("public_diagnosis_requests")},
            {"stage": "진단 구매", "count": _count("diagnosis_purchases")},
            {"stage": "결제 시도", "count": _count("payments", lambda q: q.eq("product_type", "DIAGNOSIS"))},
            {"stage": "결제 완료", "count": _count("payments", lambda q: q.eq("status_code", "SUCCESS"))},
        ],
    }

    # ── 요약 카드(전체 기간 총계) ──
    summary = {
        "companies": _count("companies"),
        "factories": _count("factories"),
        "users": _count("users"),
        "subscriptions_total": _count("subscriptions"),
        "payments_total": _count("payments"),
        "payment_success": _count("payments", lambda q: q.eq("status_code", "SUCCESS")),
        "payment_pending": _count("payments", lambda q: q.eq("status_code", "PENDING")),
        "revenue_completed": sum(int(p.get("total_amount") or 0) for p in payments if p.get("status_code") == "SUCCESS"),
        "revenue_pending": sum(int(p.get("total_amount") or 0) for p in payments if p.get("status_code") == "PENDING"),
    }

    return {
        "range_days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "revenue": revenue,
        "customers": customers,
        "products": products,
        "marketing": marketing,
    }
