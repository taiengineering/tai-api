"""Notification Event Wiring API.

GET  /notification-engine/wirings       — Wiring 목록
GET  /notification-engine/policies      — Policy 목록
POST /notification-engine/wirings/test  — Wiring 테스트 발송
"""

from fastapi import APIRouter, Query
from services.notification_engine.event_wiring import (
    list_wirings,
    list_policies,
    wire_and_emit,
)
from pydantic import BaseModel
from typing import Optional, Dict, Any

router = APIRouter(prefix="/notification-engine", tags=["notification-wiring"])


@router.get("/wirings")
async def get_wirings(enabled_only: bool = Query(True)):
    """Wiring 목록 조회."""
    data = await list_wirings(enabled_only=enabled_only)
    return {"status": "success", "data": data, "count": len(data)}


@router.get("/policies")
async def get_policies():
    """정책 목록 조회."""
    data = await list_policies()
    return {"status": "success", "data": data, "count": len(data)}


class WiringTestRequest(BaseModel):
    event_type: str
    payload: Optional[Dict[str, Any]] = None
    override_channel: Optional[str] = None
    override_severity: Optional[str] = None


@router.post("/wirings/test")
async def test_wiring(req: WiringTestRequest):
    """Wiring 테스트 발송."""
    result = await wire_and_emit(
        event_type=req.event_type,
        payload=req.payload,
        override_channel=req.override_channel,
        override_severity=req.override_severity,
    )
    return {"status": "success", "data": result}
