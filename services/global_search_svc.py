"""통합 교차검색 서비스 (WO-11 GlobalSearch).

Goal: G-ms4je4z3-33eada
- 검색어 하나로 회사·회원·사업장·결제를 교차 검색.
- 결과 정규화: {type, id, title, subtitle, company_id}. 어드민이 바로 이동.
- soft delete 반영(deleted_at IS NULL). ilike 부분일치.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

TYPES = ("company", "user", "factory", "payment")
_MIN_LEN = 2


def search(query: str, types: Optional[List[str]] = None,
           limit_per_type: int = 5) -> Dict[str, Any]:
    """통합 교차검색. 반환: {query, results: [...], counts: {...}}."""
    q = (query or "").strip()
    if len(q) < _MIN_LEN:
        return {"query": q, "results": [], "counts": {}, "note": "검색어는 2자 이상 입력하세요."}

    targets = [t for t in (types or TYPES) if t in TYPES]
    results: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {}

    if "company" in targets:
        rows = _search_companies(q, limit_per_type)
        counts["company"] = len(rows)
        results.extend(rows)
    if "user" in targets:
        rows = _search_users(q, limit_per_type)
        counts["user"] = len(rows)
        results.extend(rows)
    if "factory" in targets:
        rows = _search_factories(q, limit_per_type)
        counts["factory"] = len(rows)
        results.extend(rows)
    if "payment" in targets:
        rows = _search_payments(q, limit_per_type)
        counts["payment"] = len(rows)
        results.extend(rows)

    return {"query": q, "results": results, "counts": counts}


def _like(cols: List[str], q: str) -> str:
    """or_ 조건 문자열 생성 (ilike 부분일치)."""
    return ",".join(f"{c}.ilike.%{q}%" for c in cols)


def _search_companies(q: str, limit: int) -> List[Dict[str, Any]]:
    cols = ["name", "business_number", "company_code", "representative_name",
            "contact_phone", "contact_email"]
    res = (
        get_supabase().table("companies")
        .select("id, name, business_number, representative_name")
        .or_(_like(cols, q)).is_("deleted_at", "null").limit(limit).execute()
    ).data or []
    return [{
        "type": "company", "id": r["id"], "company_id": r["id"],
        "title": r.get("name"),
        "subtitle": " · ".join(filter(None, [r.get("representative_name"), r.get("business_number")])),
    } for r in res]


def _search_users(q: str, limit: int) -> List[Dict[str, Any]]:
    cols = ["name", "phone", "email", "user_code", "username"]
    res = (
        get_supabase().table("users")
        .select("id, name, email, phone, company_id")
        .or_(_like(cols, q)).is_("deleted_at", "null").limit(limit).execute()
    ).data or []
    return [{
        "type": "user", "id": r["id"], "company_id": r.get("company_id"),
        "title": r.get("name"),
        "subtitle": " · ".join(filter(None, [r.get("email"), r.get("phone")])),
    } for r in res]


def _search_factories(q: str, limit: int) -> List[Dict[str, Any]]:
    cols = ["name", "site_code", "manager_name", "manager_phone"]
    res = (
        get_supabase().table("factories")
        .select("id, name, site_code, manager_name, company_id")
        .or_(_like(cols, q)).is_("deleted_at", "null").limit(limit).execute()
    ).data or []
    return [{
        "type": "factory", "id": r["id"], "company_id": r.get("company_id"),
        "title": r.get("name"),
        "subtitle": " · ".join(filter(None, [r.get("site_code"), r.get("manager_name")])),
    } for r in res]


def _search_payments(q: str, limit: int) -> List[Dict[str, Any]]:
    cols = ["inicis_order_id", "inicis_tid"]
    res = (
        get_supabase().table("payments")
        .select("id, inicis_order_id, inicis_tid, total_amount, company_id")
        .or_(_like(cols, q)).limit(limit).execute()
    ).data or []
    return [{
        "type": "payment", "id": r["id"], "company_id": r.get("company_id"),
        "title": r.get("inicis_order_id") or r.get("inicis_tid") or r["id"],
        "subtitle": f"{int(r.get('total_amount') or 0):,}원",
    } for r in res]
