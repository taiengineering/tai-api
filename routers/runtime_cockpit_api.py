"""Runtime Cockpit API — Enriched views for TAI Safe SaaS frontend.

Registered in router_registry/runtime_bridge.py
Read-only. No mutations.
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from typing import Optional

from services.runtime_cockpit_service import get_cockpit_tasks

router = APIRouter(prefix="/runtime/cockpit", tags=["runtime-cockpit"])


@router.get("/tasks")
async def cockpit_tasks(
    tenant_id: str = Query(...),
    facility_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    task_type: Optional[str] = Query(None),
    overdue_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    tasks = await get_cockpit_tasks(
        tenant_id=tenant_id,
        facility_id=facility_id,
        status=status,
        task_type=task_type,
        overdue_only=overdue_only,
        limit=limit,
        offset=offset,
    )
    return {"ok": True, "tasks": tasks, "count": len(tasks)}
