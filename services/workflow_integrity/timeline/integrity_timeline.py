"""Integrity Timeline - workflow별 integrity 이벤트 + timeline 상관관계."""
from __future__ import annotations

import logging
from uuid import UUID

from db.supabase_client import get_supabase
from services.workflow_integrity.events.integrity_event_store import (
    get_events_by_workflow,
)
from services.workflow_integrity.schemas import IntegrityTimelineOut

logger = logging.getLogger(__name__)


async def get_integrity_timeline(workflow_id: UUID) -> dict:
    """Integrity Timeline 조회.

    반환: integrity events + triggered rules + workflow timeline events.
    """
    sb = get_supabase()

    # 1. Integrity events
    integrity_events = await get_events_by_workflow(workflow_id)

    # 2. Triggered rules (integrity events에서 참조된 rule_id들)
    rule_ids = list(set(
        e["rule_id"] for e in integrity_events
        if e.get("rule_id")
    ))

    triggered_rules = []
    if rule_ids:
        resp = (
            sb.table("workflow_integrity_rule_registry")
            .select("*")
            .in_("id", rule_ids)
            .execute()
        )
        triggered_rules = resp.data or []

    # 3. Workflow timeline events
    resp = (
        sb.table("workflow_event_log")
        .select("*")
        .eq("workflow_id", str(workflow_id))
        .order("occurred_at", desc=False)
        .execute()
    )
    timeline_events = resp.data or []

    # workflow_type 추론
    wf_type = "COMMON"
    if timeline_events:
        wf_type = timeline_events[0].get("workflow_type", "COMMON")
    elif integrity_events:
        wf_type = integrity_events[0].get("workflow_type", "COMMON")

    return {
        "workflow_id": str(workflow_id),
        "workflow_type": wf_type,
        "integrity_events": integrity_events,
        "triggered_rules": triggered_rules,
        "timeline_events": timeline_events,
    }
