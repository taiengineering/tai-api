"""Response Guidance API — 운영 대응 가이드.

Routes:
    GET /response/top-guidance         — 최우선 대응 가이드
    GET /response/situation/{id}       — 특정 상황 대응
    GET /response/checklist/{id}       — 체크리스트
    GET /response/playbook/{type}      — 대응 패턴
    GET /response/playbooks            — 전체 playbook 목록
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, Query
from typing import Any
from watch_engine.trans_engine.guidance_builder import build_response_guidance
from watch_engine.trans_engine.response_playbook import get_playbook, list_playbooks
from watch_engine.trans_engine.situation_snapshot_store import get_snapshot_by_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/response", tags=["Response Guidance"])

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
        logger.error(f"response _latest: {e}")
        return []

@router.get("/top-guidance")
async def api_top_guidance(limit: int = Query(5, ge=1, le=20), environment: str | None = Query(None)):
    snapshots = await _latest(environment)
    guided = []
    for s in snapshots:
        if s.get("status") == "resolved": continue
        g = build_response_guidance(s)
        guided.append({**g, "situation_id": s.get("situation_id"), "title": s.get("title"),
                       "priority": s.get("priority"), "environment": s.get("environment")})
    # sort by guidance level
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    guided.sort(key=lambda x: order.get(x.get("guidance_level", "low"), 3))
    return {"status": "success", "data": guided[:limit]}

@router.get("/situation/{snapshot_id}")
async def api_situation_guidance(snapshot_id: str):
    s = await get_snapshot_by_id(snapshot_id)
    if not s: return {"status": "error", "message": "snapshot not found"}
    g = build_response_guidance(s)
    return {"status": "success", "data": {**g, "situation_id": s.get("situation_id"), "title": s.get("title")}}

@router.get("/checklist/{snapshot_id}")
async def api_checklist(snapshot_id: str):
    s = await get_snapshot_by_id(snapshot_id)
    if not s: return {"status": "error", "message": "snapshot not found"}
    g = build_response_guidance(s)
    return {"status": "success", "data": {
        "recommended_checks": g["recommended_checks"],
        "recommended_order": g["recommended_order"],
        "guidance_level": g["guidance_level"],
    }}

@router.get("/playbook/{situation_type}")
async def api_playbook(situation_type: str):
    pb = get_playbook(situation_type)
    return {"status": "success", "data": {"type": situation_type, **pb}}

@router.get("/playbooks")
async def api_all_playbooks():
    return {"status": "success", "data": list_playbooks()}
