"""Situation History API — Operational Situation 이력 조회.

Routes:
    GET /situation/recent          — 최근 상황
    GET /situation/timeline/{sid}  — 상황 timeline
    GET /situation/{id}            — 특정 상황
    GET /situation/{sid}/history   — lifecycle history
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from typing import Any

from watch_engine.trans_engine.situation_snapshot_store import (
    get_recent_snapshots,
    get_snapshot_by_id,
    get_snapshot_timeline,
    get_situation_history,
)

router = APIRouter(prefix="/situation", tags=["Situation History"])


@router.get("/recent")
async def api_recent_snapshots(
    limit: int = Query(20, ge=1, le=100),
    environment: str | None = Query(None),
):
    """최근 운영 상황 스냅샷."""
    data = await get_recent_snapshots(limit=limit, environment=environment)
    return {"status": "success", "data": data, "count": len(data)}


@router.get("/timeline/{situation_id:path}")
async def api_snapshot_timeline(
    situation_id: str,
    limit: int = Query(50, ge=1, le=200),
):
    """situation_id 기준 timeline."""
    data = await get_snapshot_timeline(situation_id=situation_id, limit=limit)
    return {"status": "success", "data": data, "count": len(data)}


@router.get("/detail/{snapshot_id}")
async def api_get_snapshot(snapshot_id: str):
    """특정 스냅샷 상세."""
    data = await get_snapshot_by_id(snapshot_id)
    if not data:
        return {"status": "error", "message": "snapshot not found"}
    return {"status": "success", "data": data}


@router.get("/history/{situation_id:path}")
async def api_situation_history(
    situation_id: str,
    limit: int = Query(30, ge=1, le=100),
):
    """situation_id의 lifecycle history (시간순)."""
    data = await get_situation_history(situation_id=situation_id, limit=limit)
    return {"status": "success", "data": data, "count": len(data)}
