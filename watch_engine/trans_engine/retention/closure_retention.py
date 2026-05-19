"""Closure Retention."""
from __future__ import annotations
import logging
from typing import Any
from db.supabase_client import get_supabase
from .archive_policy import DEFAULT_POLICY

logger = logging.getLogger(__name__)

async def cleanup_old_closures() -> dict[str, Any]:
    try:
        sb = get_supabase()
        old = (sb.table("operational_situation_closure")
               .select("id", count="exact")
               .lt("closed_at", f"now() - interval '{DEFAULT_POLICY.archive_days} days'")
               .execute())
        old_count = old.count if hasattr(old, 'count') else len(old.data or [])
        return {"table": "operational_situation_closure", "old_records": old_count}
    except Exception as e:
        logger.error(f"closure retention: {e}")
        return {"table": "operational_situation_closure", "error": str(e)}
