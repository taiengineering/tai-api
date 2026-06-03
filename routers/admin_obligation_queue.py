"""Phase 9 — Admin Obligation Queue API.

CORRECTION_REQUIRED 의무의 보정 작업 큐 조회/배정/해소. 운영 어드민 전용.
GET    /admin/obligations/queue          목록(상태 필터)
GET    /admin/obligations/queue/{id}      상세
PATCH  /admin/obligations/queue/{id}      상태/담당자 변경
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(tags=["어드민-의무큐"])

_ALLOWED_STATUS = {"OPEN", "IN_PROGRESS", "RESOLVED"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class QueuePatch(BaseModel):
    status: Optional[str] = None
    assigned_to: Optional[str] = None


@router.get("/admin/obligations/queue")
def list_queue(
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    from db.supabase_client import get_supabase
    sb = get_supabase()
    if status is not None and status not in _ALLOWED_STATUS:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(_ALLOWED_STATUS)}")

    q = sb.table("admin_obligation_queue").select("*")
    if status is not None:
        q = q.eq("status", status)
    start = (page - 1) * page_size
    res = q.order("created_at", desc=True).range(start, start + page_size - 1).execute()
    return {"status": "success", "data": res.data or [], "page": page, "page_size": page_size}


@router.get("/admin/obligations/queue/{queue_id}")
def get_queue_item(queue_id: str):
    from db.supabase_client import get_supabase
    sb = get_supabase()
    res = sb.table("admin_obligation_queue").select("*").eq("id", queue_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="queue item not found")
    return {"status": "success", "data": res.data[0]}


@router.patch("/admin/obligations/queue/{queue_id}")
def update_queue_item(queue_id: str, patch: QueuePatch):
    from db.supabase_client import get_supabase
    sb = get_supabase()

    update: dict = {}
    if patch.status is not None:
        if patch.status not in _ALLOWED_STATUS:
            raise HTTPException(status_code=400, detail=f"status must be one of {sorted(_ALLOWED_STATUS)}")
        update["status"] = patch.status
        update["resolved_at"] = _now() if patch.status == "RESOLVED" else None
    if patch.assigned_to is not None:
        update["assigned_to"] = patch.assigned_to
    if not update:
        raise HTTPException(status_code=400, detail="no fields to update")

    res = sb.table("admin_obligation_queue").update(update).eq("id", queue_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="queue item not found")
    return {"status": "success", "data": res.data[0]}
