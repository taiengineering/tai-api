"""Operational Learning API.

Routes:
    GET  /learning/effective-actions    — 효과 높은 대응
    GET  /learning/recurring-patterns   — 재발 패턴
    GET  /learning/situation/{id}       — 특정 상황 학습
    POST /learning/feedback             — 운영자 대응 기록
    GET  /learning/memory               — 운영 경험 메모리
"""
from __future__ import annotations
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from typing import Any
from watch_engine.trans_engine.response_feedback import record_response_feedback
from watch_engine.trans_engine.effectiveness_analyzer import analyze_effective_actions, analyze_recurring_patterns
from watch_engine.trans_engine.operational_memory import build_operational_memory
from watch_engine.trans_engine.learning_registry import build_learning_registry

router = APIRouter(prefix="/learning", tags=["Operational Learning"])

class FeedbackRequest(BaseModel):
    situation_id: str
    operator_action: str
    outcome: str = Field("unchanged", description="improved|unchanged|worsened|recurring")
    snapshot_id: str | None = None
    environment: str = "production"

@router.post("/feedback")
async def api_record_feedback(req: FeedbackRequest):
    result = await record_response_feedback(
        situation_id=req.situation_id, operator_action=req.operator_action,
        outcome=req.outcome, snapshot_id=req.snapshot_id, environment=req.environment,
    )
    if not result: return {"status": "error", "message": "feedback save failed"}
    return {"status": "success", "data": result}

@router.get("/effective-actions")
async def api_effective_actions(environment: str | None = Query(None)):
    data = await analyze_effective_actions(environment=environment)
    return {"status": "success", "data": data}

@router.get("/recurring-patterns")
async def api_recurring_patterns(environment: str | None = Query(None)):
    data = await analyze_recurring_patterns(environment=environment)
    return {"status": "success", "data": data}

@router.get("/situation/{situation_id:path}")
async def api_situation_learning(situation_id: str):
    data = await build_operational_memory(situation_id)
    return {"status": "success", "data": data}

@router.get("/memory")
async def api_learning_registry(environment: str | None = Query(None)):
    data = await build_learning_registry(environment=environment)
    return {"status": "success", "data": data}
