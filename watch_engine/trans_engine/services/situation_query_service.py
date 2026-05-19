"""Situation Query Service — 공통 조회 서비스."""
from __future__ import annotations
from typing import Any
from watch_engine.trans_engine.utils.snapshot_utils import (
    get_latest_per_situation, filter_by_status, filter_by_delta,
)
from watch_engine.trans_engine.utils.aggregation_utils import build_overview

async def get_dashboard_overview(environment: str | None = None) -> dict[str, Any]:
    latest = await get_latest_per_situation(environment)
    return build_overview(latest)

async def get_worsening_situations(environment: str | None = None, limit: int = 20) -> list[dict]:
    latest = await get_latest_per_situation(environment)
    ws = [r for r in latest if r.get("delta_type") == "worsening" or r.get("status") == "escalating"]
    ws.sort(key=lambda r: r.get("generated_at", ""), reverse=True)
    return ws[:limit]

async def get_recurring_situations(environment: str | None = None, limit: int = 20) -> list[dict]:
    latest = await get_latest_per_situation(environment)
    return filter_by_delta(latest, "recurring")[:limit]

async def get_active_situations(environment: str | None = None) -> list[dict]:
    latest = await get_latest_per_situation(environment)
    return filter_by_status(latest, ["active", "escalating", "emerging"])
