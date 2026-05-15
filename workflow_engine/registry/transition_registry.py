"""Transition Registry — 허용 가능한 상태 전이 정의 + validation.

현재 단계: transition validation only. orchestration 금지.
"""

import logging
from typing import Optional, List

logger = logging.getLogger("workflow_engine.registry.transition")


def get_transitions(workflow_type: str = "COMMON") -> List[dict]:
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        resp = sb.table("workflow_transition_registry") \
            .select("*").eq("workflow_type", workflow_type).execute()
        return resp.data or []
    except Exception as e:
        logger.error("Transition registry lookup failed: %s", e)
        return []


def is_valid_transition(
    from_state: str, to_state: str, workflow_type: str = "COMMON"
) -> bool:
    """from_state → to_state 전이가 허용되는지 검증."""
    transitions = get_transitions(workflow_type)
    return any(
        t["from_state"] == from_state and t["to_state"] == to_state
        for t in transitions
    )


def get_allowed_next_states(
    from_state: str, workflow_type: str = "COMMON"
) -> List[str]:
    """현재 상태에서 전이 가능한 다음 상태 목록."""
    transitions = get_transitions(workflow_type)
    return [t["to_state"] for t in transitions if t["from_state"] == from_state]


def get_transition_detail(
    from_state: str, to_state: str, workflow_type: str = "COMMON"
) -> Optional[dict]:
    transitions = get_transitions(workflow_type)
    for t in transitions:
        if t["from_state"] == from_state and t["to_state"] == to_state:
            return t
    return None
