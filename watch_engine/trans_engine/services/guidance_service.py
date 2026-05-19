"""Guidance Service — 공통 guidance 조회."""
from __future__ import annotations
from typing import Any
from watch_engine.trans_engine.utils.snapshot_utils import get_latest_per_situation
from watch_engine.trans_engine.guidance_builder import build_response_guidance

async def get_top_guidance(env: str | None = None, limit: int = 5) -> list[dict]:
    snapshots = await get_latest_per_situation(env)
    guided = []
    for s in snapshots:
        if s.get("status") == "resolved": continue
        g = build_response_guidance(s)
        guided.append({**g, "situation_id": s.get("situation_id"), "title": s.get("title"),
                       "priority": s.get("priority"), "environment": s.get("environment")})
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    guided.sort(key=lambda x: order.get(x.get("guidance_level", "low"), 3))
    return guided[:limit]
