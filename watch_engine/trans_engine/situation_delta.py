"""Situation Delta — 스냅샷 간 변화량 계산.

delta_type: new | worsening | stabilizing | resolved | recurring | unchanged
"""

from __future__ import annotations
from typing import Any

_PRIORITY_ORDER = {"P1": 4, "P2": 3, "P3": 2, "P4": 1}
_TREND_SEVERITY = {"accelerating": 4, "degrading": 3, "stable": 2, "improving": 1}


def compute_situation_delta(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    """previous snapshot vs current snapshot → delta."""
    if not previous:
        return {
            "delta_type": "new",
            "priority_changed": False,
            "trend_changed": False,
            "impact_changed": False,
            "event_delta": current.get("event_count", 0),
            "confidence_delta": 0.0,
            "summary": "새로운 운영 상황이 감지되었습니다.",
            "change_description": "새로운 상황 발생",
            "risk_direction": "increasing",
            "recommended_attention": current.get("recommended_focus", []),
        }

    prev_p = _PRIORITY_ORDER.get(previous.get("priority", "P4"), 1)
    curr_p = _PRIORITY_ORDER.get(current.get("priority", "P4"), 1)
    prev_t = _TREND_SEVERITY.get(previous.get("trend", "stable"), 2)
    curr_t = _TREND_SEVERITY.get(current.get("trend", "stable"), 2)

    priority_changed = previous.get("priority") != current.get("priority")
    trend_changed = previous.get("trend") != current.get("trend")
    impact_changed = previous.get("impact") != current.get("impact")
    event_delta = (current.get("event_count", 0) or 0) - (previous.get("event_count", 0) or 0)
    confidence_delta = round((current.get("confidence", 0) or 0) - (previous.get("confidence", 0) or 0), 3)

    delta_type = _determine_delta_type(previous, current, curr_p - prev_p, curr_t - prev_t)
    risk_direction = _determine_risk_direction(curr_p - prev_p, curr_t - prev_t)

    return {
        "delta_type": delta_type,
        "priority_changed": priority_changed,
        "trend_changed": trend_changed,
        "impact_changed": impact_changed,
        "event_delta": event_delta,
        "confidence_delta": confidence_delta,
        "summary": _build_delta_summary(delta_type, previous, current),
        "change_description": _build_change_description(delta_type, priority_changed, trend_changed),
        "risk_direction": risk_direction,
        "recommended_attention": current.get("recommended_focus", []),
    }


def _determine_delta_type(
    prev: dict, curr: dict, p_diff: int, t_diff: int,
) -> str:
    prev_status = prev.get("status", "")
    curr_status = curr.get("status", "")
    if prev_status == "resolved" and curr_status in ("active", "escalating", "emerging"):
        return "recurring"
    if curr_status == "resolved":
        return "resolved"
    if curr_status == "stabilizing" or (t_diff < 0):
        return "stabilizing"
    if p_diff > 0 or t_diff > 0:
        return "worsening"
    if p_diff == 0 and t_diff == 0 and not (prev.get("impact") != curr.get("impact")):
        return "unchanged"
    return "unchanged"


def _determine_risk_direction(p_diff: int, t_diff: int) -> str:
    if p_diff > 0 or t_diff > 0:
        return "increasing"
    if p_diff < 0 or t_diff < 0:
        return "decreasing"
    return "stable"


def _build_delta_summary(delta_type: str, prev: dict, curr: dict) -> str:
    titles = {
        "new": "새로운 운영 상황이 감지되었습니다.",
        "worsening": "상황이 악화되고 있습니다.",
        "stabilizing": "상황이 점차 안정화되고 있습니다.",
        "resolved": "상황이 해결되었습니다.",
        "recurring": "이전 문제가 다시 발생하고 있습니다.",
        "unchanged": "상황에 특별한 변화가 없습니다.",
    }
    return titles.get(delta_type, "상황을 확인하세요.")


def _build_change_description(delta_type: str, p_changed: bool, t_changed: bool) -> str:
    parts = []
    descs = {
        "new": "새로운 상황 발생",
        "worsening": "상황 악화",
        "stabilizing": "상황 안정화",
        "resolved": "상황 해결",
        "recurring": "상황 재발",
        "unchanged": "변화 없음",
    }
    parts.append(descs.get(delta_type, delta_type))
    if p_changed:
        parts.append("우선순위 변경")
    if t_changed:
        parts.append("추세 변경")
    return " · ".join(parts)
