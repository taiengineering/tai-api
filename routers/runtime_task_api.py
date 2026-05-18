"""Runtime Task API — CRUD endpoints.

Registered in router_registry/runtime_bridge.py
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from services import runtime_task_service as svc

router = APIRouter(prefix="/runtime/tasks", tags=["runtime"])


# ----- Schemas -----

class TaskCreateRequest(BaseModel):
    tenant_id: str
    facility_id: str
    source_engine: str = "manual"
    source_ref_id: Optional[str] = None
    source_event_id: Optional[str] = None
    trace_id: Optional[str] = None
    task_type: str
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    assignee_id: Optional[str] = None
    due_date: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class StatusUpdateRequest(BaseModel):
    status: str


# ----- Endpoints -----

@router.post("")
async def create_task(body: TaskCreateRequest):
    try:
        task = await svc.create_task(body.model_dump())
        return {"ok": True, "task": task}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_tasks(
    tenant_id: str = Query(...),
    facility_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    tasks = await svc.list_tasks(
        tenant_id=tenant_id,
        facility_id=facility_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {"ok": True, "tasks": tasks, "count": len(tasks)}


@router.get("/{task_id}")
async def get_task(task_id: str):
    task = await svc.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True, "task": task}


@router.patch("/{task_id}/status")
async def update_status(task_id: str, body: StatusUpdateRequest):
    try:
        task = await svc.update_task_status(task_id, body.status)
        return {"ok": True, "task": task}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
