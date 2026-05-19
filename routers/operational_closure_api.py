"""Operational Closure API.

Routes:
    POST /closure/resolve             — 상황 종료
    GET  /closure/history/{sid}       — 종료 이력
    GET  /closure/open                — 미종료 상황
    GET  /closure/followup            — follow-up 필요
    GET  /closure/operator/{oid}      — 운영자 활동 이력
"""
from __future__ import annotations
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from typing import Any
from watch_engine.trans_engine.operational_closure import close_operational_situation
from watch_engine.trans_engine.closure_workflow import (
    get_open_situations, get_followup_situations,
    get_closure_history, get_operator_history,
)

router = APIRouter(prefix="/closure", tags=["Operational Closure"])

class ResolveRequest(BaseModel):
    situation_id: str
    operator_id: str
    resolution_type: str = Field("resolved", description="resolved|accepted|monitoring|false_alarm")
    resolution_notes: str = ""
    operator_activities: list[dict[str, Any]] | None = None
    requires_followup: bool = False
    followup_notes: str = ""
    snapshot_id: str | None = None
    environment: str = "production"

@router.post("/resolve")
async def api_resolve(req: ResolveRequest):
    result = await close_operational_situation(
        situation_id=req.situation_id, operator_id=req.operator_id,
        resolution_type=req.resolution_type, resolution_notes=req.resolution_notes,
        operator_activities=req.operator_activities, requires_followup=req.requires_followup,
        followup_notes=req.followup_notes, snapshot_id=req.snapshot_id, environment=req.environment,
    )
    if not result: return {"status": "error", "message": "closure save failed"}
    return {"status": "success", "data": result}

@router.get("/history/{situation_id:path}")
async def api_closure_history(situation_id: str):
    data = await get_closure_history(situation_id)
    return {"status": "success", "data": data, "count": len(data)}

@router.get("/open")
async def api_open_situations(environment: str | None = Query(None)):
    data = await get_open_situations(environment=environment)
    # deduplicate by situation_id
    seen = set(); unique = []
    for d in data:
        sid = d.get("situation_id", "")
        if sid not in seen: seen.add(sid); unique.append(d)
    return {"status": "success", "data": unique, "count": len(unique)}

@router.get("/followup")
async def api_followup(environment: str | None = Query(None)):
    data = await get_followup_situations(environment=environment)
    return {"status": "success", "data": data, "count": len(data)}

@router.get("/operator/{operator_id}")
async def api_operator_history(operator_id: str, limit: int = Query(30, ge=1, le=100)):
    data = await get_operator_history(operator_id, limit=limit)
    return {"status": "success", "data": data, "count": len(data)}
