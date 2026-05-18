"""Recurrence Detector — 재발 감지.

동일 situation_id가 resolved → active/escalating/emerging으로 변경되면 recurring 판정.
"""

from __future__ import annotations
from typing import Any


def detect_recurrence(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    """재발 감지."""
    if not previous:
        return {"is_recurring": False, "reason": None}

    prev_status = previous.get("status", "")
    curr_status = current.get("status", "")

    active_states = {"emerging", "active", "escalating"}

    if prev_status == "resolved" and curr_status in active_states:
        return {
            "is_recurring": True,
            "reason": f"이전에 해결된 상황이 다시 {curr_status} 상태로 변경되었습니다.",
            "previous_resolved_at": previous.get("generated_at"),
        }

    if prev_status == "stabilizing" and curr_status in {"active", "escalating"}:
        return {
            "is_recurring": True,
            "reason": "안정화 중이던 상황이 다시 악화되었습니다.",
            "previous_resolved_at": previous.get("generated_at"),
        }

    return {"is_recurring": False, "reason": None}
