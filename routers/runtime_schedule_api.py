"""Runtime Schedule API — Create schedules + trigger overdue check.

Registered in router_registry/runtime_bridge.py
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from services import runtime_schedule_service as svc

router = APIRouter(prefix="/runtime/schedules", tags=["runtime"])


class ScheduleCreateRequest(BaseModel):
    tenant_id: str
    facility_id: str
    task_id: str
    schedule_type: str = "periodic"
    recurrence_rule: Optional[str] = None
    next_due_date: str
    inspector_id: Optional[str] = None
    metadata: dict = {}


@router.post("")
async def create_schedule(body: ScheduleCreateRequest):
    try:
        sched = await svc.create_schedule(body.model_dump())
        return {"ok": True, "schedule": sched}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/check-overdue")
async def check_overdue():
    """Manually trigger overdue check (also callable by cron)."""
    events = await svc.check_overdue_schedules()
    return {"ok": True, "overdue_events": len(events), "events": events}
