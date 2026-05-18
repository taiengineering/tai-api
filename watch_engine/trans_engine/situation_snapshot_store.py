"""Situation Snapshot Store — Supabase 저장/조회.

operational_situation_snapshot 테이블 CRUD.
"""

from __future__ import annotations

import logging
from typing import Any

from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

TABLE = "operational_situation_snapshot"


async def save_snapshot(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Snapshot 저장."""
    try:
        sb = get_supabase()
        result = sb.table(TABLE).insert(snapshot).execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        logger.error(f"save_snapshot error: {e}")
        return None


async def get_recent_snapshots(
    limit: int = 20,
    environment: str | None = None,
) -> list[dict[str, Any]]:
    """최근 스냅샷 조회."""
    try:
        sb = get_supabase()
        q = sb.table(TABLE).select("*").order("generated_at", desc=True).limit(limit)
        if environment:
            q = q.eq("environment", environment)
        result = q.execute()
        return result.data or []
    except Exception as e:
        logger.error(f"get_recent_snapshots error: {e}")
        return []


async def get_snapshot_timeline(
    situation_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """situation_id 기준 timeline 조회."""
    try:
        sb = get_supabase()
        result = (
            sb.table(TABLE)
            .select("id,situation_id,title,summary,priority,urgency,trend,status,confidence,event_count,environment,generated_at")
            .eq("situation_id", situation_id)
            .order("generated_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"get_snapshot_timeline error: {e}")
        return []


async def get_snapshot_by_id(snapshot_id: str) -> dict[str, Any] | None:
    """특정 스냅샷 조회."""
    try:
        sb = get_supabase()
        result = sb.table(TABLE).select("*").eq("id", snapshot_id).limit(1).execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        logger.error(f"get_snapshot_by_id error: {e}")
        return None


async def get_situation_history(
    situation_id: str,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """situation_id의 lifecycle history."""
    try:
        sb = get_supabase()
        result = (
            sb.table(TABLE)
            .select("id,situation_id,title,priority,trend,status,confidence,event_count,environment,generated_at")
            .eq("situation_id", situation_id)
            .order("generated_at", desc=False)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"get_situation_history error: {e}")
        return []
