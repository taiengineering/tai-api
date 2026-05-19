"""Attention Service — 공통 attention 조회."""
from __future__ import annotations
from typing import Any
from watch_engine.trans_engine.utils.snapshot_utils import get_latest_per_situation
from watch_engine.trans_engine.attention_ranker import rank_by_attention, get_critical_situations
from watch_engine.trans_engine.focus_queue import build_focus_queue
from watch_engine.trans_engine.attention_engine import build_attention_overview

async def get_top_attention(env: str | None = None, limit: int = 10) -> list[dict]:
    snapshots = await get_latest_per_situation(env)
    return rank_by_attention(snapshots)[:limit]

async def get_critical_attention(env: str | None = None) -> list[dict]:
    snapshots = await get_latest_per_situation(env)
    return get_critical_situations(snapshots)

async def get_attention_queue(env: str | None = None, limit: int = 10) -> list[dict]:
    snapshots = await get_latest_per_situation(env)
    return build_focus_queue(snapshots, limit=limit)

async def get_attention_summary(env: str | None = None) -> dict[str, Any]:
    snapshots = await get_latest_per_situation(env)
    return build_attention_overview(snapshots)
