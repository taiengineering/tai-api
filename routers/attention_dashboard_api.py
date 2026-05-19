"""Attention Dashboard API — 운영자 집중 우선순위.

Routes:
    GET /attention/top       — 상위 집중 대상
    GET /attention/critical  — 즉시 대응 대상
    GET /attention/queue     — focus queue
    GET /attention/summary   — attention 요약
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, Query
from typing import Any
from watch_engine.trans_engine.attention_ranker import rank_by_attention, get_critical_situations
from watch_engine.trans_engine.focus_queue import build_focus_queue
from watch_engine.trans_engine.attention_engine import build_attention_overview

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/attention", tags=["Attention Engine"])

async def _latest(env: str | None) -> list[dict]:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        q = sb.table("operational_situation_snapshot").select("*").order("generated_at", desc=True).limit(500)
        if env: q = q.eq("environment", env)
        rows = (q.execute()).data or []
        seen: dict[str, dict] = {}
        for r in rows:
            sid = r.get("situation_id", "")
            if sid not in seen: seen[sid] = r
        return list(seen.values())
    except Exception as e:
        logger.error(f"attention _latest: {e}")
        return []

@router.get("/top")
async def api_top(limit: int = Query(10, ge=1, le=50), environment: str | None = Query(None)):
    snapshots = await _latest(environment)
    ranked = rank_by_attention(snapshots)
    return {"status": "success", "data": ranked[:limit]}

@router.get("/critical")
async def api_critical(environment: str | None = Query(None)):
    snapshots = await _latest(environment)
    critical = get_critical_situations(snapshots)
    return {"status": "success", "data": critical, "count": len(critical)}

@router.get("/queue")
async def api_queue(limit: int = Query(10, ge=1, le=30), environment: str | None = Query(None)):
    snapshots = await _latest(environment)
    queue = build_focus_queue(snapshots, limit=limit)
    return {"status": "success", "data": queue}

@router.get("/summary")
async def api_summary(environment: str | None = Query(None)):
    snapshots = await _latest(environment)
    overview = build_attention_overview(snapshots)
    return {"status": "success", "data": overview}
