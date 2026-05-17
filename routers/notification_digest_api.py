"""Notification Digest API.

GET  /notification-engine/digest-policies    — Digest 정책 목록
GET  /notification-engine/digest-candidates  — Digest 후보 목록
POST /notification-engine/digest-test        — Digest 테스트 append
"""

from fastapi import APIRouter, Query
from services.notification_engine.digest_runtime import (
    list_digest_policies,
    list_digest_candidates,
    check_and_append,
)
from pydantic import BaseModel
from typing import Optional, Dict, Any

router = APIRouter(prefix="/notification-engine", tags=["notification-digest"])


@router.get("/digest-policies")
async def get_digest_policies(enabled_only: bool = Query(False)):
    """Digest 정책 목록."""
    data = await list_digest_policies(enabled_only=enabled_only)
    return {"status": "success", "data": data, "count": len(data)}


@router.get("/digest-candidates")
async def get_digest_candidates(
    status: str = Query("PENDING"),
    limit: int = Query(50, le=200),
):
    """Digest 후보 목록."""
    data = await list_digest_candidates(status=status, limit=limit)
    return {"status": "success", "data": data, "count": len(data)}


class DigestTestRequest(BaseModel):
    source_type: Optional[str] = None
    event_type: Optional[str] = None
    trace_id: Optional[str] = None
    event_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@router.post("/digest-test")
async def test_digest(req: DigestTestRequest):
    """Digest 테스트 (shadow mode append)."""
    result = await check_and_append(
        source_type=req.source_type,
        event_type=req.event_type,
        trace_id=req.trace_id,
        event_id=req.event_id,
        metadata=req.metadata,
    )
    return {"status": "success", "data": result}
