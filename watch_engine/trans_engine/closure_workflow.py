"""Closure Workflow — 종료 흐름 관리."""
from __future__ import annotations
import logging
from typing import Any
from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)
TABLE = "operational_situation_closure"

async def get_open_situations(environment: str | None = None) -> list[dict]:
    """미종료 상황 (closure 없는 active snapshot)."""
    try:
        sb = get_supabase()
        q = (sb.table("operational_situation_snapshot")
             .select("situation_id,title,status,priority,trend,attention_level,environment,generated_at")
             .in_("status", ["active", "escalating", "emerging"])
             .is_("closure_status", "null")
             .order("generated_at", desc=True).limit(100))
        if environment: q = q.eq("environment", environment)
        return (q.execute()).data or []
    except Exception as e:
        logger.error(f"get_open_situations: {e}")
        return []

async def get_followup_situations(environment: str | None = None) -> list[dict]:
    try:
        sb = get_supabase()
        q = sb.table(TABLE).select("*").eq("requires_followup", True).order("closed_at", desc=True).limit(50)
        if environment: q = q.eq("environment", environment)
        return (q.execute()).data or []
    except Exception as e:
        logger.error(f"get_followup: {e}"); return []

async def get_closure_history(situation_id: str) -> list[dict]:
    try:
        sb = get_supabase()
        return (sb.table(TABLE).select("*").eq("situation_id", situation_id)
                .order("closed_at", desc=True).limit(20).execute()).data or []
    except Exception as e:
        logger.error(f"get_closure_history: {e}"); return []

async def get_operator_history(operator_id: str, limit: int = 30) -> list[dict]:
    try:
        sb = get_supabase()
        return (sb.table(TABLE).select("*").eq("operator_id", operator_id)
                .order("closed_at", desc=True).limit(limit).execute()).data or []
    except Exception as e:
        logger.error(f"get_operator_history: {e}"); return []
