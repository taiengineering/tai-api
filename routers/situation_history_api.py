"""Situation History API — Operational Situation 이력 + Evolution 조회.

Routes:
    GET /situation/recent                — 최근 상황
    GET /situation/timeline/{sid}        — 상황 timeline
    GET /situation/detail/{id}           — 특정 상황
    GET /situation/history/{sid}         — lifecycle history
    GET /situation/evolution/{id}        — 변화 흐름 (T-06)
    GET /situation/recurring             — 재발 상황 (T-06)
    GET /situation/worsening             — 악화 중 상황 (T-06)
    GET /situation/stabilizing           — 안정화 중 상황 (T-06)
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
from watch_engine.trans_engine.situation_evolution import compute_situation_evolution

router = APIRouter(prefix="/situation", tags=["Situation History"])


# ── T-05 Endpoints ─────────────────────────

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


# ── T-06 Endpoints ─────────────────────────

@router.get("/evolution/{snapshot_id}")
async def api_snapshot_evolution(snapshot_id: str):
    """특정 스냅샷의 변화 흐름 (이전 대비 delta)."""
    current = await get_snapshot_by_id(snapshot_id)
    if not current:
        return {"status": "error", "message": "snapshot not found"}

    previous = None
    prev_id = current.get("previous_snapshot_id")
    if prev_id:
        previous = await get_snapshot_by_id(prev_id)

    evolution = compute_situation_evolution(previous, current)
    return {"status": "success", "data": evolution}


@router.get("/recurring")
async def api_recurring_situations(
    limit: int = Query(20, ge=1, le=100),
    environment: str | None = Query(None),
):
    """재발 상황 목록."""
    data = await _filter_by_delta_type("recurring", limit, environment)
    return {"status": "success", "data": data, "count": len(data)}


@router.get("/worsening")
async def api_worsening_situations(
    limit: int = Query(20, ge=1, le=100),
    environment: str | None = Query(None),
):
    """악화 중 상황 목록."""
    data = await _filter_by_delta_type("worsening", limit, environment)
    return {"status": "success", "data": data, "count": len(data)}


@router.get("/stabilizing")
async def api_stabilizing_situations(
    limit: int = Query(20, ge=1, le=100),
    environment: str | None = Query(None),
):
    """안정화 중 상황 목록."""
    data = await _filter_by_delta_type("stabilizing", limit, environment)
    return {"status": "success", "data": data, "count": len(data)}


async def _filter_by_delta_type(
    delta_type: str, limit: int, environment: str | None,
) -> list[dict[str, Any]]:
    """delta_type으로 필터링."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        q = (
            sb.table("operational_situation_snapshot")
            .select("*")
            .eq("delta_type", delta_type)
            .order("generated_at", desc=True)
            .limit(limit)
        )
        if environment:
            q = q.eq("environment", environment)
        result = q.execute()
        return result.data or []
    except Exception:
        return []
