"""Runtime Schedule Service — Create schedules + overdue detection.

Ownership: Runtime Projection Layer.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from db.supabase_client import get_supabase
from watch_engine.runtime_bus.event_envelope import (
    EventEnvelope, create_envelope, emit_envelope,
)


async def create_schedule(data: dict[str, Any]) -> dict:
    sb = get_supabase()
    row = {
        "id": str(uuid.uuid4()),
        "tenant_id": data["tenant_id"],
        "facility_id": data["facility_id"],
        "task_id": data["task_id"],
        "schedule_type": data.get("schedule_type", "periodic"),
        "recurrence_rule": data.get("recurrence_rule"),
        "next_due_date": data["next_due_date"],
        "inspector_id": data.get("inspector_id"),
        "status": "active",
        "metadata": data.get("metadata", {}),
    }
    res = sb.table("runtime_schedule").insert(row).execute()
    return res.data[0] if res.data else row


async def check_overdue_schedules() -> list[dict]:
    """Find active schedules past due date and emit overdue events.

    Intended to be called by a scheduler/cron.
    """
    sb = get_supabase()
    today = date.today().isoformat()
    res = (
        sb.table("runtime_schedule")
        .select("*, runtime_task!inner(id, tenant_id, title, status)")
        .eq("status", "active")
        .lt("next_due_date", today)
        .execute()
    )
    overdue = res.data or []
    events_emitted: list[dict] = []

    for sched in overdue:
        task = sched.get("runtime_task", {})
        if not task or task.get("status") == "completed":
            continue

        # Mark task overdue (if not already)
        if task.get("status") not in ("completed", "overdue"):
            sb.table("runtime_task").update(
                {"status": "overdue"}
            ).eq("id", task["id"]).execute()

        # Emit overdue event
        envelope = create_envelope(
            event_type="runtime.schedule_overdue",
            tenant_id=sched["tenant_id"],
            source="runtime",
            payload={
                "schedule_id": sched["id"],
                "task_id": task["id"],
                "task_title": task.get("title"),
                "next_due_date": sched["next_due_date"],
                "overdue_since": today,
            },
        )
        await emit_envelope(envelope)
        events_emitted.append(envelope.model_dump(mode="json"))

    return events_emitted
