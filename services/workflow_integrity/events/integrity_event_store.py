"""Integrity Event Store - 이상 탐지 결과 저장.

역할: workflow_integrity_event 테이블 CRUD.
상태 변경 금지 (Event 기록만 수행).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from db.supabase_client import get_supabase
from services.workflow_integrity.schemas import IntegrityEventCreate

logger = logging.getLogger(__name__)


async def create_integrity_event(event: IntegrityEventCreate) -> dict:
    """Integrity 이벤트 생성."""
    sb = get_supabase()
    row = {
        "workflow_id": str(event.workflow_id),
        "workflow_type": event.workflow_type,
        "integrity_type": event.integrity_type,
        "severity": event.severity,
        "payload": event.payload,
    }
    if event.rule_id:
        row["rule_id"] = str(event.rule_id)
    if event.trace_id:
        row["trace_id"] = event.trace_id

    resp = sb.table("workflow_integrity_event").insert(row).execute()
    logger.info(
        "Integrity event created: workflow=%s type=%s severity=%s",
        event.workflow_id, event.integrity_type, event.severity,
    )
    return resp.data[0] if resp.data else {}


async def get_events_by_workflow(workflow_id: UUID) -> list[dict]:
    """특정 workflow의 integrity 이벤트 조회."""
    sb = get_supabase()
    resp = (
        sb.table("workflow_integrity_event")
        .select("*")
        .eq("workflow_id", str(workflow_id))
        .order("detected_at", desc=True)
        .execute()
    )
    return resp.data or []


async def get_unresolved_events(workflow_id: UUID) -> list[dict]:
    """미해결 이벤트 조회."""
    sb = get_supabase()
    resp = (
        sb.table("workflow_integrity_event")
        .select("*")
        .eq("workflow_id", str(workflow_id))
        .eq("resolved", False)
        .order("detected_at", desc=True)
        .execute()
    )
    return resp.data or []


async def resolve_event(event_id: UUID) -> dict | None:
    """이벤트 해결 처리."""
    sb = get_supabase()
    resp = (
        sb.table("workflow_integrity_event")
        .update({
            "resolved": True,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        })
        .eq("id", str(event_id))
        .execute()
    )
    return resp.data[0] if resp.data else None
