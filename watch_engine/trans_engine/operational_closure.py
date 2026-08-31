"""Operational Closure — 상황 종료 통합 엔트리포인트."""
from __future__ import annotations
import uuid, logging
from datetime import datetime, timezone
from typing import Any
from db.supabase_client import get_supabase
from .closure_summary import build_closure_summary
from services.time import now_kst, serialize_external_utc

logger = logging.getLogger(__name__)

async def close_operational_situation(
    situation_id: str, operator_id: str,
    resolution_type: str = "resolved",
    resolution_notes: str = "",
    operator_activities: list[dict] | None = None,
    requires_followup: bool = False,
    followup_notes: str = "",
    snapshot_id: str | None = None,
    environment: str = "production",
) -> dict[str, Any] | None:
    now = serialize_external_utc(now_kst())
    # 최신 snapshot에서 title 가져오기
    title = ""
    try:
        sb = get_supabase()
        snaps = (sb.table("operational_situation_snapshot")
                 .select("id,title").eq("situation_id", situation_id)
                 .order("generated_at", desc=True).limit(1).execute()).data or []
        if snaps:
            title = snaps[0].get("title", "")
            if not snapshot_id: snapshot_id = snaps[0].get("id")
    except Exception: pass

    summary = build_closure_summary(title, resolution_type, operator_id, resolution_notes, operator_activities)

    closure = {
        "id": str(uuid.uuid4()),
        "situation_id": situation_id,
        "snapshot_id": snapshot_id,
        "operator_id": operator_id,
        "resolution_type": resolution_type,
        "resolution_summary": summary,
        "operator_notes": resolution_notes,
        "operator_activities": operator_activities or [],
        "requires_followup": requires_followup,
        "followup_notes": followup_notes,
        "closed_at": now,
        "environment": environment,
    }
    try:
        sb = get_supabase()
        result = sb.table("operational_situation_closure").insert(closure).execute()
        if not result.data: return None
        # snapshot closure_status 업데이트
        if snapshot_id:
            try:
                sb.table("operational_situation_snapshot").update({
                    "closure_status": resolution_type,
                    "resolved_by": operator_id,
                    "resolved_at": now,
                    "closure_summary": summary,
                }).eq("id", snapshot_id).execute()
            except Exception: pass
        return result.data[0]
    except Exception as e:
        logger.error(f"close_operational_situation: {e}")
        return None
