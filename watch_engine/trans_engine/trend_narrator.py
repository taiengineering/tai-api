"""Trend Narrator — 추세를 운영 언어로 서술."""

from __future__ import annotations

from typing import Any


_TREND_DESCRIPTIONS: dict[str, str] = {
    "improving":     "상황이 점차 안정되고 있습니다.",
    "stable":        "현재 상태가 유지되고 있습니다.",
    "degrading":     "서비스 안정성이 점차 낮아지고 있습니다.",
    "accelerating":  "문제가 빠르게 증가하는 추세입니다.",
}


def describe_trend(trend: str) -> str:
    """추세 코드 → 운영 표현."""
    return _TREND_DESCRIPTIONS.get(
        trend.lower(), "운영 추세를 확인하세요."
    )


def infer_trend(events: list[dict[str, Any]]) -> str:
    """이벤트 집합에서 추세를 추론.

    단순 휴리스틱:
    - escalation 있으면 accelerating
    - degradation 있으면 degrading
    - recovery.completed 있으면 improving
    - 그 외 stable
    """
    types = {e.get("event_type", "") for e in events}

    if "escalation" in types:
        return "accelerating"
    if "degradation" in types or "runtime.degraded" in types:
        return "degrading"
    if "recovery.completed" in types:
        return "improving"
    return "stable"
