"""Delta Explainer — delta_type을 운영 언어로 변환."""

from __future__ import annotations
from typing import Any

_DELTA_LABELS: dict[str, dict[str, str]] = {
    "new":         {"badge": "🆕 신규",     "description": "새로운 운영 상황이 감지되었습니다."},
    "worsening":   {"badge": "🔺 악화",     "description": "상황이 악화되고 있습니다. 우선 확인이 필요합니다."},
    "stabilizing": {"badge": "🔻 안정화",   "description": "상황이 점차 안정화되고 있습니다."},
    "resolved":    {"badge": "✅ 해결",      "description": "상황이 해결되었습니다."},
    "recurring":   {"badge": "🔁 재발",     "description": "이전에 해결된 문제가 다시 발생하고 있습니다."},
    "unchanged":   {"badge": "➖ 유지",     "description": "상황에 특별한 변화가 없습니다."},
}


def explain_delta(delta_type: str) -> dict[str, str]:
    """delta_type → 운영 언어."""
    return _DELTA_LABELS.get(
        delta_type,
        {"badge": "❓ 확인", "description": "상황 변화를 확인하세요."},
    )


def explain_delta_full(delta: dict[str, Any]) -> dict[str, Any]:
    """delta dict → 운영 설명 포함 dict."""
    dt = delta.get("delta_type", "unchanged")
    label = explain_delta(dt)
    return {
        **delta,
        "badge": label["badge"],
        "description": label["description"],
    }
