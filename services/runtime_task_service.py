"""Runtime Task Service — CRUD + status transition.

Ownership: Runtime Projection Layer.
Does NOT modify engine truth.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from db.supabase_client import get_supabase

# ----- Status transition rules -----
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "candidate": {"assigned"},
    "assigned": {"in_progress", "overdue"},
    "in_progress": {"completed", "overdue"},
    "completed": set(),
    "overdue": {"in_progress", "completed"},
}


def validate_transition(current: str, target: str) -> bool:
    return target in _VALID_TRANSITIONS.get(current, set())


# ----- CRUD -----

async def create_task(data: dict[str, Any]) -> dict:
    sb = get_supabase()
    row = {
        "id": str(uuid.uuid4()),
        "tenant_id": data["tenant_id"],
        "facility_id": data["facility_id"],
        "source_engine": data.get("source_engine", "manual"),
        "source_ref_id": data.get("source_ref_id"),
        "source_event_id": data.get("source_event_id"),
        "trace_id": data.get("trace_id", str(uuid.uuid4())),
        "task_type": data["task_type"],
        "title": data["title"],
        "description": data.get("description"),
        "status": "candidate",
        "priority": data.get("priority", "medium"),
        "assignee_id": data.get("assignee_id"),
        "due_date": data.get("due_date"),
        "metadata": data.get("metadata", {}),
    }
    res = sb.table("runtime_task").insert(row).execute()
    return res.data[0] if res.data else row


async def list_tasks(
    tenant_id: str,
    facility_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    sb = get_supabase()
    q = sb.table("runtime_task").select("*").eq("tenant_id", tenant_id)
    if facility_id:
        q = q.eq("facility_id", facility_id)
    if status:
        q = q.eq("status", status)
    q = q.order("created_at", desc=True).range(offset, offset + limit - 1)
    res = q.execute()
    return res.data or []


async def get_task(task_id: str) -> Optional[dict]:
    sb = get_supabase()
    res = sb.table("runtime_task").select("*").eq("id", task_id).execute()
    return res.data[0] if res.data else None


async def update_task_status(task_id: str, new_status: str) -> dict:
    task = await get_task(task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")
    if not validate_transition(task["status"], new_status):
        raise ValueError(
            f"Invalid transition: {task['status']} → {new_status}"
        )
    sb = get_supabase()
    res = (
        sb.table("runtime_task")
        .update({"status": new_status})
        .eq("id", task_id)
        .execute()
    )
    return res.data[0] if res.data else task
