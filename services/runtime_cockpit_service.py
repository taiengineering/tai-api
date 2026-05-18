"""Runtime Cockpit Service — Enriched task views for SaaS frontend.

Ownership: Runtime Projection Layer.
Read-only aggregation. Does NOT modify any data.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from db.supabase_client import get_supabase


async def get_cockpit_tasks(
    tenant_id: str,
    facility_id: Optional[str] = None,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    overdue_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Return enriched task list for Cockpit display.

    Each task includes:
    - required_document_count
    - fulfilled_document_count
    - required_evidence_count
    - fulfilled_evidence_count
    - is_overdue (computed from schedule)
    - next_due_date (from schedule)
    """
    sb = get_supabase()

    # Base task query
    q = sb.table("runtime_task").select("*").eq("tenant_id", tenant_id)
    if facility_id:
        q = q.eq("facility_id", facility_id)
    if status:
        q = q.eq("status", status)
    if task_type:
        q = q.eq("task_type", task_type)
    if overdue_only:
        q = q.eq("status", "overdue")

    q = q.order("created_at", desc=True).range(offset, offset + limit - 1)
    res = q.execute()
    tasks = res.data or []

    if not tasks:
        return []

    task_ids = [t["id"] for t in tasks]

    # Batch fetch document requirements
    doc_res = (
        sb.table("runtime_document_requirement")
        .select("task_id, is_fulfilled")
        .in_("task_id", task_ids)
        .execute()
    )
    doc_map: dict[str, dict] = {}
    for d in (doc_res.data or []):
        tid = d["task_id"]
        if tid not in doc_map:
            doc_map[tid] = {"total": 0, "fulfilled": 0}
        doc_map[tid]["total"] += 1
        if d.get("is_fulfilled"):
            doc_map[tid]["fulfilled"] += 1

    # Batch fetch evidence requirements
    evi_res = (
        sb.table("runtime_evidence_requirement")
        .select("task_id, is_fulfilled")
        .in_("task_id", task_ids)
        .execute()
    )
    evi_map: dict[str, dict] = {}
    for e in (evi_res.data or []):
        tid = e["task_id"]
        if tid not in evi_map:
            evi_map[tid] = {"total": 0, "fulfilled": 0}
        evi_map[tid]["total"] += 1
        if e.get("is_fulfilled"):
            evi_map[tid]["fulfilled"] += 1

    # Batch fetch schedules (nearest due date)
    sched_res = (
        sb.table("runtime_schedule")
        .select("task_id, next_due_date, status")
        .in_("task_id", task_ids)
        .eq("status", "active")
        .execute()
    )
    sched_map: dict[str, dict] = {}
    today = date.today().isoformat()
    for s in (sched_res.data or []):
        tid = s["task_id"]
        ndd = s.get("next_due_date")
        if tid not in sched_map or (ndd and ndd < sched_map[tid].get("next_due_date", "9999")):
            sched_map[tid] = {
                "next_due_date": ndd,
                "is_overdue": bool(ndd and ndd < today),
            }

    # Enrich tasks
    enriched = []
    for t in tasks:
        tid = t["id"]
        doc = doc_map.get(tid, {"total": 0, "fulfilled": 0})
        evi = evi_map.get(tid, {"total": 0, "fulfilled": 0})
        sch = sched_map.get(tid, {})
        enriched.append({
            "id": tid,
            "task_type": t["task_type"],
            "title": t["title"],
            "description": t.get("description"),
            "status": t["status"],
            "priority": t["priority"],
            "due_date": t.get("due_date"),
            "assignee_id": t.get("assignee_id"),
            "source_engine": t["source_engine"],
            "is_overdue": t["status"] == "overdue" or sch.get("is_overdue", False),
            "next_due_date": sch.get("next_due_date"),
            "required_document_count": doc["total"],
            "fulfilled_document_count": doc["fulfilled"],
            "required_evidence_count": evi["total"],
            "fulfilled_evidence_count": evi["fulfilled"],
            "created_at": t["created_at"],
        })

    return enriched
