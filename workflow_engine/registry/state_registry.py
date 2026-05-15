"""State Registry — Workflow 상태 정의 조회."""

import logging
from typing import Optional, List

logger = logging.getLogger("workflow_engine.registry.state")


def get_states(workflow_type: str = "COMMON") -> List[dict]:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        resp = sb.table("workflow_state_registry") \
            .select("*").eq("workflow_type", workflow_type) \
            .order("sort_order").execute()
        return resp.data or []
    except Exception as e:
        logger.error("State registry lookup failed: %s", e)
        return []


def is_valid_state(state_code: str, workflow_type: str = "COMMON") -> bool:
    states = get_states(workflow_type)
    return any(s["state_code"] == state_code for s in states)


def is_terminal(state_code: str, workflow_type: str = "COMMON") -> bool:
    states = get_states(workflow_type)
    for s in states:
        if s["state_code"] == state_code:
            return s.get("is_terminal", False)
    return False
