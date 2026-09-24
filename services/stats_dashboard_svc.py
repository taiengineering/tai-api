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
from services.time import now_kst, serialize_external_utc

log = logging.getLogger(__name__)

_PAGE = 1000
_MAX_PAGES = 60  # 안전 상한(최대 6만행)


def _day(iso: Optional[str]) -> Optional[str]:
    """ISO 타임스탬프 → 'YYYY-MM-DD'. 앞 10자만 사용(타임존 파싱 회피)."""
    if not iso or len(iso) < 10:
        return None
    return iso[:10]


def _since_iso(days: int) -> str:
    start = now_kst() - timedelta(days=days)
    return start.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _date_axis(days: int) -> List[str]:
    """오늘 포함 최근 days 일의 날짜 라벨(오름차순)."""
    today = now_kst().date()
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
        "generated_at": serialize_external_utc(now_kst()),
        "summary": summary,
        "revenue": revenue,
        "customers": customers,
        "products": products,
        "marketing": marketing,
    }


# ── OBJ08B Canonical Marketing Business Outcomes ──────────────────────────────

_KST = timezone(timedelta(hours=9))


def _parse_date_token(token: str) -> Optional["datetime"]:
    """date token → KST datetime(date 시작, 00:00:00). 실패 → None."""
    import re
    token = (token or "").strip()
    if token == "today":
        return now_kst().replace(hour=0, minute=0, second=0, microsecond=0)
    if token == "yesterday":
        return (now_kst() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    m = re.fullmatch(r"(\d+)daysAgo", token)
    if m:
        n = int(m.group(1))
        return (now_kst() - timedelta(days=n)).replace(hour=0, minute=0, second=0, microsecond=0)
    # YYYY-MM-DD
    try:
        from datetime import date as _date
        d = _date.fromisoformat(token)
        return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=_KST)
    except (ValueError, AttributeError):
        return None


def _count_exact_strict(table: str, build: Optional[Callable] = None) -> int:
    """엄격 count — DB 오류 시 0이 아니라 예외 전파. 0과 장애를 구분."""
    q = get_supabase().table(table).select("id", count="exact")
    if build:
        q = build(q)
    result = q.execute()
    return result.count or 0


def get_marketing_business_outcomes(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """OBJ08B Canonical Marketing Business Outcomes.

    반환: {available, date_from, date_to, timezone, flows, current_stock,
           rates, cohort_joined, semantics}

    fail-closed: DB 오류 → available=False, flows=None, current_stock=None.
    0건 ≠ 오류. rates=None(cohort join 금지). cohort_joined=False.
    """
    from_token = date_from or "28daysAgo"
    to_token = date_to or "today"

    from_dt = _parse_date_token(from_token)
    to_dt = _parse_date_token(to_token)

    if from_dt is None or to_dt is None:
        raise ValueError(f"invalid date token: from={from_token!r} to={to_token!r}")

    # to_dt: 해당 날짜 다음날 00:00:00 KST (exclusive upper bound)
    to_exclusive = to_dt + timedelta(days=1)

    if from_dt >= to_exclusive:
        raise ValueError(f"date range invalid: from={from_token!r} >= to={to_token!r}")

    from_iso = from_dt.isoformat()
    to_iso = to_exclusive.isoformat()

    # date_from/date_to 응답용 (YYYY-MM-DD)
    from_label = from_dt.strftime("%Y-%m-%d")
    to_label = to_dt.strftime("%Y-%m-%d")

    snapshot_at = serialize_external_utc(now_kst())

    try:
        # B01 Canonical: anonymous_diagnosis_results.created_at within period
        free_diagnosis_completed = _count_exact_strict(
            "anonymous_diagnosis_results",
            lambda q: q.gte("created_at", from_iso).lt("created_at", to_iso),
        )

        # B02 Canonical: users WHERE auth_id IS NOT NULL AND created_at within period
        # auth_id is set ONLY by /auth/register (Supabase sign_up) and /auth/ensure-user (social OAuth JWT).
        # Excludes: worker OTP (_ensure_user_row: auth_id NULL), admin /users (auth_id NULL),
        #           company invite accept (auth_id NULL).
        # Residual: ensure-user may UPDATE auth_id on an admin-created row with matching email.
        #   That row's created_at precedes the social login, so period attribution is the admin
        #   creation date — not structurally fixable without a new schema column.
        signup_complete = _count_exact_strict(
            "users",
            lambda q: (
                q.not_.is_("auth_id", "null")
                 .gte("created_at", from_iso)
                 .lt("created_at", to_iso)
            ),
        )

        # B04 Canonical: payments WHERE product_type='DIAGNOSIS' AND status='SUCCESS'
        # AND paid_at IS NOT NULL AND paid_at within period
        paid_diagnosis_purchased = _count_exact_strict(
            "payments",
            lambda q: (
                q.eq("product_type", "DIAGNOSIS")
                 .eq("status_code", "SUCCESS")
                 .not_.is_("paid_at", "null")
                 .gte("paid_at", from_iso)
                 .lt("paid_at", to_iso)
            ),
        )

        # B05 Canonical: payments WHERE product_type LIKE 'SAAS%' AND status='SUCCESS'
        # AND paid_at IS NOT NULL AND paid_at within period
        saas_payment_success = _count_exact_strict(
            "payments",
            lambda q: (
                q.like("product_type", "SAAS%")
                 .eq("status_code", "SUCCESS")
                 .not_.is_("paid_at", "null")
                 .gte("paid_at", from_iso)
                 .lt("paid_at", to_iso)
            ),
        )

        # B06 Current stock (no date filter — point-in-time)
        saas_service_active = _count_exact_strict(
            "contracts",
            lambda q: (
                q.eq("service_type", "SAAS")
                 .eq("status_code", "ACTIVE")
                 .eq("is_active", True)
            ),
        )

        # B07 Canonical: anonymous_diagnosis_results WHERE claimed_user_id IS NOT NULL
        # AND created_at within period (진단 생성 시점 기준, claimed_at 컬럼 없음)
        free_diagnosis_claimed = _count_exact_strict(
            "anonymous_diagnosis_results",
            lambda q: (
                q.not_.is_("claimed_user_id", "null")
                 .gte("created_at", from_iso)
                 .lt("created_at", to_iso)
            ),
        )

        # B08 Current stock (no date filter — point-in-time)
        # subscriptions.status='ACTIVE' ≠ contracts.service_type='SAAS'
        subscription_active = _count_exact_strict(
            "subscriptions",
            lambda q: q.eq("status", "ACTIVE"),
        )

    except Exception as e:
        log.warning("[MKT-OUTCOMES] DB query failed: %s", e)
        return {
            "available": False,
            "date_from": from_label,
            "date_to": to_label,
            "timezone": "Asia/Seoul",
            "flows": None,
            "current_stock": None,
            "rates": None,
            "cohort_joined": False,
            "semantics": "independent_business_facts_not_cohort",
        }

    return {
        "available": True,
        "date_from": from_label,
        "date_to": to_label,
        "timezone": "Asia/Seoul",
        "flows": {
            "free_diagnosis_completed": free_diagnosis_completed,
            "free_diagnosis_claimed": free_diagnosis_claimed,
            "signup_complete": signup_complete,
            "paid_diagnosis_purchased": paid_diagnosis_purchased,
            "saas_payment_success": saas_payment_success,
        },
        "current_stock": {
            "saas_service_active": saas_service_active,
            "subscription_active": subscription_active,
            "snapshot_at": snapshot_at,
        },
        "rates": None,
        "cohort_joined": False,
        "semantics": "independent_business_facts_not_cohort",
    }
