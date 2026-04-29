from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException

from db.supabase_client import get_supabase


def list_document_forms(
    *,
    sector: Optional[str] = None,
    category: Optional[str] = None,
    tai_grade: Optional[str] = None,
    tab_type: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> Dict[str, Any]:
    supabase = get_supabase()
    query = supabase.table("document_forms").select("*", count="exact").eq("is_active", True)

    if sector:
        query = query.eq("sector", sector)
    if category:
        query = query.eq("category", category)
    if tai_grade:
        query = query.eq("tai_grade", tai_grade.upper())
    if tab_type:
        query = query.eq("tab_type", tab_type)
    if search:
        q = search.replace(",", " ").strip()
        if q:
            query = query.or_(f"doc_name.ilike.%{q}%,law_ref.ilike.%{q}%,doc_id.ilike.%{q}%")

    page = max(1, int(page))
    per_page = max(1, min(200, int(per_page)))
    start = (page - 1) * per_page
    end = start + per_page - 1

    res = query.order("doc_id").range(start, end).execute()
    return {
        "items": res.data or [],
        "total": int(res.count or 0),
        "page": page,
        "per_page": per_page,
    }


def get_document_form(doc_id: str) -> Dict[str, Any]:
    supabase = get_supabase()
    res = (
        supabase.table("document_forms")
        .select("*")
        .eq("doc_id", doc_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail=f"document form not found: {doc_id}")
    return res.data[0]


def get_document_forms_stats() -> Dict[str, Any]:
    supabase = get_supabase()
    res = (
        supabase.table("document_forms")
        .select("sector,tai_grade,tab_type")
        .eq("is_active", True)
        .execute()
    )
    rows = res.data or []

    by_sector: Dict[str, int] = {}
    by_grade: Dict[str, int] = {}
    by_tab: Dict[str, int] = {}
    for r in rows:
        s = (r.get("sector") or "").strip() or "UNKNOWN"
        g = (r.get("tai_grade") or "").strip().upper() or "X"
        t = (r.get("tab_type") or "").strip() or "UNKNOWN"
        by_sector[s] = by_sector.get(s, 0) + 1
        by_grade[g] = by_grade.get(g, 0) + 1
        by_tab[t] = by_tab.get(t, 0) + 1

    return {
        "total": len(rows),
        "by_sector": by_sector,
        "by_grade": by_grade,
        "by_tab": by_tab,
    }

