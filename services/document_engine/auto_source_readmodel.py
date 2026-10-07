"""AUTO-REUSE-01: AUTO_SOURCE document discovery read model.

Queries completed Inspection and TBM records and builds unified list items.
Read-only. Zero persistence. Reuses existing scope/resolver patterns.

Sources:
  INSPECTION → safety_inspections.status_code IN ('COMPLETED','ISSUE','HOLD','completed')
               joined with work_schedules for summary/company_id
  TBM        → tbm_meetings.status_code = 'COMPLETED'
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.company_scope import DENY, ScopeFilter, apply_scoped_filter


# Raw status values that represent a terminal "completed" inspection
_INSP_TERMINAL_STATUSES = ("COMPLETED", "ISSUE", "HOLD", "completed")


def _build_insp_document_key(inspection_id: str) -> str:
    return f"auto:v1:INSPECTION:{inspection_id}:INSP:-"


def _build_tbm_document_key(meeting_id: str) -> str:
    return f"auto:v1:TBM:{meeting_id}:TBM:-"


def _insp_item(row: dict) -> dict:
    ws = row.get("work_schedules") or {}
    title = ws.get("summary") or "점검 기록"
    occurred = (
        row.get("inspection_date")
        or row.get("updated_at")
        or row.get("created_at")
    )
    return {
        "document_key": _build_insp_document_key(row["id"]),
        "channel": "AUTO_SOURCE",
        "source_type": "INSPECTION",
        "source_id": str(row["id"]),
        "doc_type": "INSP",
        "title": title,
        "occurred_at": occurred,
        "source_status": row.get("status_code", "COMPLETED"),
        "factory_id": str(row.get("factory_id") or ws.get("factory_id") or ""),
        "company_id": str(row.get("company_id") or ws.get("company_id") or ""),
        "can_preview": True,
        "can_pdf": True,
    }


def _tbm_item(row: dict) -> dict:
    work_date = row.get("work_date") or row.get("created_at")
    title = row.get("meeting_title") or f"TBM {(work_date or '')[:10]}"
    return {
        "document_key": _build_tbm_document_key(row["id"]),
        "channel": "AUTO_SOURCE",
        "source_type": "TBM",
        "source_id": str(row["id"]),
        "doc_type": "TBM",
        "title": title,
        "occurred_at": row.get("completed_at") or work_date,
        "source_status": row.get("status_code", "COMPLETED"),
        "factory_id": str(row.get("factory_id") or ""),
        "company_id": str(row.get("company_id") or ""),
        "can_preview": True,
        "can_pdf": True,
    }


def list_auto_documents(
    sb: Any,
    scope_filter: ScopeFilter,
    *,
    source_type: str = "ALL",
    factory_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """Build unified AUTO document list.

    Returns {"items": [...], "total": int, "page": int, "page_size": int, "total_pages": int}
    Zero DB writes.
    """
    if scope_filter is DENY:
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0}

    items: List[dict] = []

    if source_type in ("ALL", "INSPECTION"):
        items.extend(_fetch_inspections(sb, scope_filter, factory_id=factory_id))

    if source_type in ("ALL", "TBM"):
        items.extend(_fetch_tbm(sb, scope_filter, factory_id=factory_id))

    # Unified sort: occurred_at DESC, then source_type, source_id for stability
    items.sort(
        key=lambda x: (
            x.get("occurred_at") or "",
            x.get("source_type") or "",
            x.get("source_id") or "",
        ),
        reverse=True,
    )

    total = len(items)
    offset = (page - 1) * page_size
    page_items = items[offset: offset + page_size]
    total_pages = max(1, (total + page_size - 1) // page_size)

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def _fetch_inspections(
    sb: Any,
    scope_filter: ScopeFilter,
    factory_id: Optional[str] = None,
) -> List[dict]:
    q = (
        sb.table("safety_inspections")
        .select(
            "id, inspection_date, status_code, factory_id, "
            "work_schedules!assignment_id(summary, company_id, factory_id)"
        )
        .in_("status_code", list(_INSP_TERMINAL_STATUSES))
    )
    q = apply_scoped_filter(q, scope_filter)
    if factory_id:
        q = q.eq("factory_id", factory_id)
    # Limit to avoid unbounded table scan (caller applies page-level slicing)
    res = q.order("inspection_date", desc=True).limit(500).execute()
    return [_insp_item(r) for r in (res.data or [])]


def _fetch_tbm(
    sb: Any,
    scope_filter: ScopeFilter,
    factory_id: Optional[str] = None,
) -> List[dict]:
    q = (
        sb.table("tbm_meetings")
        .select("id, meeting_title, work_date, completed_at, status_code, factory_id, company_id")
        .eq("status_code", "COMPLETED")
    )
    q = apply_scoped_filter(q, scope_filter)
    if factory_id:
        q = q.eq("factory_id", factory_id)
    res = q.order("work_date", desc=True).limit(500).execute()
    return [_tbm_item(r) for r in (res.data or [])]
