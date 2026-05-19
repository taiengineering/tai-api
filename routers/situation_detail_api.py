"""Situation Detail API — 상황 상세 조회.

Routes:
    GET /situation/detail-full/{id}       — 전체 상세
    GET /situation/lifecycle/{id}         — lifecycle timeline
    GET /situation/guidance-history/{id}  — guidance history
    GET /situation/activity/{id}         — operator activity
    GET /situation/learning/{id}         — learning memory
"""
from __future__ import annotations
from fastapi import APIRouter, Query
from typing import Any
from watch_engine.trans_engine.situation_snapshot_store import get_snapshot_by_id, get_situation_history
from watch_engine.trans_engine.services.learning_service import get_situation_learning
from watch_engine.trans_engine.services.closure_service import get_history as get_closure_hist
from watch_engine.trans_engine.guidance_builder import build_response_guidance

router = APIRouter(prefix="/situation", tags=["Situation Detail"])

@router.get("/detail-full/{snapshot_id}")
async def api_detail_full(snapshot_id: str):
    s = await get_snapshot_by_id(snapshot_id)
    if not s: return {"status": "error", "message": "not found"}
    sid = s.get("situation_id", "")
    guidance = build_response_guidance(s)
    learning = await get_situation_learning(sid)
    closures = await get_closure_hist(sid)
    history = await get_situation_history(sid, limit=20)
    return {"status": "success", "data": {
        "snapshot": s, "guidance": guidance, "learning": learning,
        "closures": closures, "lifecycle_history": history,
    }}

@router.get("/lifecycle/{situation_id:path}")
async def api_lifecycle(situation_id: str, limit: int = Query(30, ge=1, le=100)):
    data = await get_situation_history(situation_id, limit=limit)
    return {"status": "success", "data": data}

@router.get("/guidance-history/{situation_id:path}")
async def api_guidance_history(situation_id: str, limit: int = Query(20, ge=1, le=100)):
    history = await get_situation_history(situation_id, limit=limit)
    guided = []
    for s in history:
        if s.get("guidance_level"):
            guided.append({"generated_at": s.get("generated_at"), "guidance_level": s.get("guidance_level"),
                           "guidance_summary": s.get("guidance_summary", ""), "priority": s.get("priority")})
    return {"status": "success", "data": guided}

@router.get("/activity/{situation_id:path}")
async def api_activity(situation_id: str):
    closures = await get_closure_hist(situation_id)
    activities = []
    for c in closures:
        for a in (c.get("operator_activities") or []):
            activities.append({**a, "closure_id": c.get("id"), "resolution_type": c.get("resolution_type")})
    return {"status": "success", "data": activities}

@router.get("/learning-detail/{situation_id:path}")
async def api_learning_detail(situation_id: str):
    data = await get_situation_learning(situation_id)
    return {"status": "success", "data": data}
