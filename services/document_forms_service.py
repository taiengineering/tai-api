from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)


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
    items = res.data or []
    _enrich_with_availability(supabase, items)
    return {
        "items": items,
        "total": int(res.count or 0),
        "page": page,
        "per_page": per_page,
    }


_APPROVED = "APPROVED_FOR_RUNTIME_USE"
_CANDIDATE = "CANDIDATE"


def _enrich_with_availability(supabase: Any, items: list[dict]) -> None:
    """Batch-enriches items with schema_availability. Mutates in place.

    Availability contract (mirrors catalog_resolver.py):
      APPROVED_FOR_RUNTIME_USE == 1  → READY_FOR_EDIT
      APPROVED_FOR_RUNTIME_USE > 1   → SCHEMA_ERROR (integrity violation, same policy as catalog_resolver)
      only CANDIDATE                 → PREPARING
      neither                        → NO_SCHEMA
      DB query failure               → NO_SCHEMA (fail-closed; never silently READY)
    """
    if not items:
        return

    catalog_ids = [item["id"] for item in items if item.get("id")]
    if not catalog_ids:
        for item in items:
            item["schema_availability"] = "NO_SCHEMA"
        return

    try:
        schema_rows = (
            supabase.table("runtime_form_schema")
            .select("catalog_document_id,status")
            .in_("catalog_document_id", catalog_ids)
            .in_("status", [_APPROVED, _CANDIDATE])
            .execute()
        ).data or []
    except Exception as exc:
        # DB query failure: distinct from "schema not yet created" — use SCHEMA_ERROR
        # so the frontend shows "상태 확인 불가" rather than "서식 미준비"
        log.warning("runtime_form_schema batch query failed — marking all as SCHEMA_ERROR: %s", exc)
        for item in items:
            item["schema_availability"] = "SCHEMA_ERROR"
        return

    approved_map: dict[str, int] = {}
    candidate_count_map: dict[str, int] = {}
    for s in schema_rows:
        cid = s["catalog_document_id"]
        if s["status"] == _APPROVED:
            approved_map[cid] = approved_map.get(cid, 0) + 1
        elif s["status"] == _CANDIDATE:
            candidate_count_map[cid] = candidate_count_map.get(cid, 0) + 1

    for item in items:
        cid = item.get("id")
        acount = approved_map.get(cid, 0)
        ccount = candidate_count_map.get(cid, 0)
        if acount > 1:
            item["schema_availability"] = "SCHEMA_ERROR"
        elif acount == 1:
            item["schema_availability"] = "READY_FOR_EDIT"
        elif ccount > 0:
            item["schema_availability"] = "PREPARING"
        else:
            item["schema_availability"] = "NO_SCHEMA"


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

