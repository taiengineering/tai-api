"""Synthetic Timeline - trace_id 기반 실행 이력 + 연관 정보."""
from __future__ import annotations

import logging

from db.supabase_client import get_supabase
from services.browser_synthetic.events.execution_log_store import (
    get_executions_by_trace,
)

logger = logging.getLogger(__name__)


async def get_synthetic_timeline(trace_id: str) -> dict:
    """Synthetic Timeline 조회.

    반환: executions + related workflow + related alerts.
    """
    # 1. Synthetic executions
    executions = await get_executions_by_trace(trace_id)

    # 2. Related workflow (execution에서 workflow_id 추출)
    workflow_id = None
    for ex in executions:
        if ex.get("workflow_id"):
            workflow_id = ex["workflow_id"]
            break

    # 3. Related alerts (integrity events with matching trace_id)
    sb = get_supabase()
    related_alerts = []
    try:
        resp = (
            sb.table("workflow_integrity_event")
            .select("*")
            .eq("trace_id", trace_id)
            .order("detected_at", desc=True)
            .execute()
        )
        related_alerts = resp.data or []
    except Exception as e:
        logger.warning("Failed to fetch related alerts: %s", e)

    return {
        "trace_id": trace_id,
        "executions": executions,
        "related_workflow_id": workflow_id,
        "related_alerts": related_alerts,
    }
