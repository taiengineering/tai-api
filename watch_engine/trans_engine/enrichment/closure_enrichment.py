"""Closure Enrichment."""
from __future__ import annotations
from typing import Any
from watch_engine.trans_engine.closure_workflow import get_closure_history

async def apply_closure_enrichment(snapshot: dict[str, Any]) -> dict[str, Any]:
    try:
        situation_id = snapshot.get("situation_id", "")
        closures = await get_closure_history(situation_id)
        if closures:
            c = closures[0]
            snapshot["closure_status"] = c.get("resolution_type")
            snapshot["resolved_by"] = c.get("operator_id")
            snapshot["resolved_at"] = c.get("closed_at")
            snapshot["closure_summary"] = c.get("resolution_summary", "")
    except Exception:
        pass
    return snapshot
