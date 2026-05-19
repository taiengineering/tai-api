"""Snapshot Retention — 스냅샷 보존 정쇅."""
from __future__ import annotations
import logging
from typing import Any
from db.supabase_client import get_supabase
from .archive_policy import DEFAULT_POLICY

logger = logging.getLogger(__name__)

async def cleanup_old_snapshots() -> dict[str, Any]:
    try:
        sb = get_supabase()
        # Delete > 180 days
        del_result = sb.rpc("exec_sql", {"query": f"""
            DELETE FROM operational_situation_snapshot
            WHERE generated_at < now() - interval '{DEFAULT_POLICY.delete_days} days'
        """}).execute() if False else None  # Safety: disabled by default
        # For now, just count old records
        old = (sb.table("operational_situation_snapshot")
               .select("id", count="exact")
               .lt("generated_at", f"now() - interval '{DEFAULT_POLICY.archive_days} days'")
               .execute())
        old_count = old.count if hasattr(old, 'count') else len(old.data or [])
        return {"table": "operational_situation_snapshot", "old_records": old_count, "policy": "archive_30d"}
    except Exception as e:
        logger.error(f"snapshot retention: {e}")
        return {"table": "operational_situation_snapshot", "error": str(e)}
