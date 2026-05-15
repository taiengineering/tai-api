"""Workflow Timeline — workflow_id 기반 상태 전이 추적.

Notification Timeline과 분리.
"""

import logging
from typing import Optional

logger = logging.getLogger("workflow_engine.timeline")


def get_workflow_timeline(workflow_id: str) -> Optional[dict]:
    """workflow_id로 상태 전이 히스토리 조회."""
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()

        resp = sb.table("workflow_event_log") \
            .select("*").eq("workflow_id", workflow_id) \
            .order("occurred_at").execute()

        events = resp.data or []

        timeline = []
        for ev in events:
            timeline.append({
                "step": ev.get("transition_name") or ev.get("event_type"),
                "from_state": ev.get("from_state"),
                "to_state": ev.get("to_state"),
                "event_type": ev.get("event_type"),
                "time": ev.get("occurred_at"),
                "trace_id": ev.get("trace_id"),
                "triggered_by": ev.get("triggered_by"),
            })

        current_state = events[-1]["to_state"] if events else None

        # 다음 허용 상태 조회
        allowed_next = []
        if current_state:
            from workflow_engine.registry.transition_registry import get_allowed_next_states
            wf_type = events[-1].get("workflow_type", "COMMON") if events else "COMMON"
            allowed_next = get_allowed_next_states(current_state, wf_type)

        return {
            "workflow_id": workflow_id,
            "current_state": current_state,
            "allowed_next_states": allowed_next,
            "event_count": len(events),
            "timeline": timeline,
            "raw_events": events,
        }

    except Exception as e:
        logger.error("Workflow timeline failed for %s: %s", workflow_id, e)
        return None
