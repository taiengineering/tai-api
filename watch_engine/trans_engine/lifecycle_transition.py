"""Lifecycle Transition — 상태 전이 계산 + 해석."""

from __future__ import annotations
from typing import Any

_TRANSITION_DESCRIPTIONS: dict[str, str] = {
    "emerging→active": "운영 영향이 시작되었습니다",
    "active→escalating": "위험이 증가하고 있습니다",
    "escalating→stabilizing": "상황이 안정화되기 시작했습니다",
    "stabilizing→resolved": "상황이 해결되었습니다",
    "resolved→active": "이전 문제가 재발했습니다",
    "resolved→emerging": "유사한 이상이 다시 감지되었습니다",
    "active→stabilizing": "상황이 안정화되기 시작했습니다",
    "escalating→active": "위험 증가가 멈추었습니다",
    "stabilizing→active": "상황이 다시 악화되고 있습니다",
    "emerging→escalating": "이상이 빠르게 위험으로 전환되었습니다",
    "emerging→resolved": "감지된 이상이 자동 해소되었습니다",
}


def compute_lifecycle_transition(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    """lifecycle 상태 전이 계산."""
    if not previous:
        return {
            "transition": None,
            "from_status": None,
            "to_status": current.get("status", "emerging"),
            "description": "새로운 상황 감지",
            "is_significant": True,
        }

    from_s = previous.get("status", "emerging")
    to_s = current.get("status", "emerging")

    if from_s == to_s:
        return {
            "transition": None,
            "from_status": from_s,
            "to_status": to_s,
            "description": "상태 유지 중",
            "is_significant": False,
        }

    key = f"{from_s}→{to_s}"
    desc = _TRANSITION_DESCRIPTIONS.get(key, f"{from_s}에서 {to_s}(으)로 변경되었습니다")

    is_sig = key in (
        "active→escalating", "escalating→stabilizing",
        "stabilizing→resolved", "resolved→active",
        "emerging→escalating",
    )

    return {
        "transition": key,
        "from_status": from_s,
        "to_status": to_s,
        "description": desc,
        "is_significant": is_sig,
    }
