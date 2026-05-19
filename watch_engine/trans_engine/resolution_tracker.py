"""Resolution Tracker — 종료 후 추적."""
from __future__ import annotations
import logging
from typing import Any
from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)

async def check_recurrence_after_closure(situation_id: str) -> dict[str, Any]:
    """closure 이후 재발 여부 확인."""
    try:
        sb = get_supabase()
        closures = (sb.table("operational_situation_closure")
                    .select("closed_at").eq("situation_id", situation_id)
                    .order("closed_at", desc=True).limit(1).execute()).data or []
        if not closures:
            return {"has_closure": False, "recurred": False}
        last_closed = closures[0]["closed_at"]
        snapshots = (sb.table("operational_situation_snapshot")
                     .select("id,status,generated_at")
                     .eq("situation_id", situation_id)
                     .gt("generated_at", last_closed)
                     .neq("status", "resolved")
                     .limit(5).execute()).data or []
        return {
            "has_closure": True,
            "last_closed_at": last_closed,
            "recurred": len(snapshots) > 0,
            "recurrence_count": len(snapshots),
        }
    except Exception as e:
        logger.error(f"check_recurrence_after_closure: {e}")
        return {"has_closure": False, "recurred": False}
