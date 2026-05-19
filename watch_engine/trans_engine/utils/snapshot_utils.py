"""Snapshot Utils — 공통 스냅샷 조회/그룹화 유틸."""
from __future__ import annotations
import logging
from typing import Any
from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)
TABLE = "operational_situation_snapshot"

async def get_latest_per_situation(environment: str | None = None, limit: int = 500) -> list[dict]:
    try:
        sb = get_supabase()
        q = sb.table(TABLE).select("*").order("generated_at", desc=True).limit(limit)
        if environment: q = q.eq("environment", environment)
        rows = (q.execute()).data or []
        seen: dict[str, dict] = {}
        for r in rows:
            sid = r.get("situation_id", "")
            if sid not in seen: seen[sid] = r
        return list(seen.values())
    except Exception as e:
        logger.error(f"get_latest_per_situation: {e}")
        return []

def group_by_situation(rows: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        sid = r.get("situation_id", "")
        if sid not in groups: groups[sid] = []
        groups[sid].append(r)
    return groups

def filter_by_status(rows: list[dict], statuses: list[str]) -> list[dict]:
    return [r for r in rows if r.get("status") in statuses]

def filter_by_delta(rows: list[dict], delta_type: str) -> list[dict]:
    return [r for r in rows if r.get("delta_type") == delta_type]
