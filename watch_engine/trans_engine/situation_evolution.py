"""Situation Evolution — 전체 변화 해석 통합.

situation_delta + lifecycle_transition + recurrence_detector
→ 통합 evolution 결과
"""

from __future__ import annotations
from typing import Any

from .situation_delta import compute_situation_delta
from .lifecycle_transition import compute_lifecycle_transition
from .recurrence_detector import detect_recurrence
from .delta_explainer import explain_delta


def compute_situation_evolution(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    """previous + current snapshot → evolution 해석."""
    delta = compute_situation_delta(previous, current)
    transition = compute_lifecycle_transition(previous, current)
    recurrence = detect_recurrence(previous, current)

    # recurring이면 delta_type override
    if recurrence["is_recurring"] and delta["delta_type"] != "recurring":
        delta["delta_type"] = "recurring"
        delta["summary"] = "이전 문제가 다시 발생하고 있습니다."
        delta["change_description"] = "상황 재발"

    label = explain_delta(delta["delta_type"])

    return {
        "situation_id": current.get("situation_id", ""),
        "current_status": current.get("status", "emerging"),
        "delta_type": delta["delta_type"],
        "delta_badge": label["badge"],
        "lifecycle_transition": transition.get("transition"),
        "transition_description": transition.get("description", ""),
        "is_significant": transition.get("is_significant", False),
        "is_recurring": recurrence["is_recurring"],
        "story": delta["summary"],
        "change_summary": delta["change_description"],
        "risk_direction": delta["risk_direction"],
        "priority_changed": delta["priority_changed"],
        "trend_changed": delta["trend_changed"],
        "event_delta": delta["event_delta"],
        "recommended_attention": delta["recommended_attention"],
    }
