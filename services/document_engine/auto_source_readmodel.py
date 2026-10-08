"""AUTO-REUSE-01: AUTO_SOURCE document discovery read model.

Read-only. Zero persistence. Reuses existing scope/resolver patterns.

HOTFIX-001: PostgREST single-column FK embed hint removed (was causing PGRST200).
  Production FK is composite (assignment_id, factory_id) — hint-based embed fails.
  Schedule metadata now fetched via separate batch SELECT (_fetch_schedule_metadata).

CORR-002:
  - _insp_item uses effective record — source_status = effective.inspection_status
  - Effective fields prefer resolver output, fall back to raw
  - Resolver error: InspectionRecordError → fail-close exclude; unexpected errors propagate

Sources:
  INSPECTION → safety_inspections (candidate: status_code IN candidates)
               scoped via work_schedules.company_id/factory_id through assignment_id
               metadata: batch SELECT work_schedules by candidate assignment_ids
               effective: resolve_inspection_record() → is_active=True, inspection_status=COMPLETED
               item fields from effective record (not raw candidate row)
  TBM        → tbm_meetings.status_code = 'COMPLETED'
               scoped via tbm_meetings.company_id/factory_id directly
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.company_scope import DENY, ScopeFilter, apply_scoped_filter
from services.inspection_record_resolver import InspectionRecordError, resolve_inspection_record

# Raw status values used as candidate narrowing only — NOT final authority.
# IN_PROGRESS is included because journal can produce effective COMPLETED from raw IN_PROGRESS.
_INSP_CANDIDATE_STATUSES = ("COMPLETED", "ISSUE", "HOLD", "completed", "IN_PROGRESS")


def _build_insp_document_key(inspection_id: str) -> str:
    return f"auto:v1:INSPECTION:{inspection_id}:INSP:-"


def _build_tbm_document_key(meeting_id: str) -> str:
    return f"auto:v1:TBM:{meeting_id}:TBM:-"


def _insp_item(row: dict, effective: dict) -> dict:
    """Build inspection AUTO document item.

    source_status and other fields come from the effective resolved record.
    Falls back to raw row fields if resolver did not provide them.
    """
    ws = row.get("work_schedules") or {}
    title = ws.get("summary") or "점검 기록"

    # Prefer effective record values over raw candidate row
    source_status = effective.get("inspection_status") or row.get("status_code") or "COMPLETED"
    occurred_at = (
        effective.get("inspection_date")
        or row.get("inspection_date")
        or row.get("updated_at")
        or row.get("created_at")
    )
    factory_id = (
        effective.get("factory_id")
        or row.get("factory_id")
        or ws.get("factory_id")
        or ""
    )
    company_id = (
        effective.get("company_id")
        or row.get("company_id")
        or ws.get("company_id")
        or ""
    )

    return {
        "document_key": _build_insp_document_key(row["id"]),
        "channel": "AUTO_SOURCE",
        "source_type": "INSPECTION",
        "source_id": str(row["id"]),
        "doc_type": "INSP",
        "title": title,
        "occurred_at": occurred_at,
        "source_status": source_status,
        "factory_id": str(factory_id),
        "company_id": str(company_id),
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
    Zero DB writes. V1 cap: 500 rows/source before pagination.
    """
    if scope_filter is DENY:
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0}

    items: List[dict] = []

    if source_type in ("ALL", "INSPECTION"):
        items.extend(_fetch_inspections(sb, scope_filter, factory_id=factory_id))

    if source_type in ("ALL", "TBM"):
        items.extend(_fetch_tbm(sb, scope_filter, factory_id=factory_id))

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


def _fetch_inspection_assignment_ids(
    sb: Any,
    scope_filter: ScopeFilter,
) -> Optional[List[str]]:
    """Return allowed assignment_ids from work_schedules, or None meaning no restriction.

    safety_inspections has no company_id — tenant scope routes through
    work_schedules.company_id/factory_id via the assignment_id FK.

    Returns:
        None  — ALL tier (scope_filter = {}), no tenant restriction
        []    — scope has no matching work_schedules → caller must return empty
        [ids] — list of assignment_ids the tenant is allowed to see
    """
    if not scope_filter:  # {} = ALL tier
        return None
    q = sb.table("work_schedules").select("id")
    q = apply_scoped_filter(q, scope_filter)
    if q is None:
        return []
    res = q.limit(1000).execute()
    return [r["id"] for r in (res.data or []) if r.get("id")]


def _fetch_schedule_metadata(
    sb: Any,
    assignment_ids: List[str],
) -> Dict[str, dict]:
    """Batch fetch work_schedules metadata for the given assignment_ids.

    Returns {schedule_id: {summary, company_id, factory_id}} map.
    Avoids PostgREST composite-FK embed hint (PGRST200).
    """
    if not assignment_ids:
        return {}
    res = (
        sb.table("work_schedules")
        .select("id, summary, company_id, factory_id")
        .in_("id", assignment_ids)
        .execute()
    )
    return {
        r["id"]: {
            "summary": r.get("summary"),
            "company_id": r.get("company_id"),
            "factory_id": r.get("factory_id"),
        }
        for r in (res.data or [])
        if r.get("id")
    }


def _fetch_inspections(
    sb: Any,
    scope_filter: ScopeFilter,
    factory_id: Optional[str] = None,
) -> List[dict]:
    """Fetch effectively-COMPLETED inspections via scope + resolver.

    Scope: routed through work_schedules (safety_inspections has no company_id column).
    Final inclusion: resolve_inspection_record() is_active=True + inspection_status=COMPLETED.
    Raw status is candidate narrowing only.
    Item fields use effective resolved values (not raw candidate row).
    Schedule metadata fetched via separate batch SELECT (no PostgREST embedded join).
    """
    assignment_ids = _fetch_inspection_assignment_ids(sb, scope_filter)
    if assignment_ids is not None and not assignment_ids:
        return []  # scope has no matching work_schedules

    q = (
        sb.table("safety_inspections")
        .select("id, inspection_date, status_code, factory_id, assignment_id")
        .in_("status_code", list(_INSP_CANDIDATE_STATUSES))
    )
    if assignment_ids is not None:
        q = q.in_("assignment_id", assignment_ids)
    if factory_id:
        q = q.eq("factory_id", factory_id)
    res = q.order("inspection_date", desc=True).limit(500).execute()
    candidates = res.data or []

    # Batch-fetch schedule metadata — avoids PGRST200 from composite FK embed hint
    candidate_assignment_ids = [
        row["assignment_id"] for row in candidates if row.get("assignment_id")
    ]
    schedule_map = _fetch_schedule_metadata(sb, candidate_assignment_ids)
    for row in candidates:
        row["work_schedules"] = schedule_map.get(row.get("assignment_id"), {})

    result = []
    for row in candidates:
        try:
            effective = resolve_inspection_record(row["id"], sb)
        except InspectionRecordError:
            continue  # known domain error → fail-close exclude
        # Unexpected infrastructure/programming errors propagate — do not silently omit
        if effective.get("is_active") and effective.get("inspection_status") == "COMPLETED":
            result.append(_insp_item(row, effective))
    return result


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
    if q is None:
        return []
    if factory_id:
        q = q.eq("factory_id", factory_id)
    res = q.order("work_date", desc=True).limit(500).execute()
    return [_tbm_item(r) for r in (res.data or [])]
