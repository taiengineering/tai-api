"""Attention Explainer — attention 수준을 운영 언어로 변환."""
from __future__ import annotations
from typing import Any

_LEVEL_DESC = {
    "critical": {
        "label": "🔴 즉시 확인 필요",
        "description": "즉시 확인이 필요한 상황입니다. 운영 위험이 높습니다.",
    },
    "high": {
        "label": "🟠 우선 확인 필요",
        "description": "우선적으로 확인해야 할 상황입니다.",
    },
    "medium": {
        "label": "🟡 관찰 필요",
        "description": "상황을 지켜볼 필요가 있습니다.",
    },
    "low": {
        "label": "🟢 정보 수준",
        "description": "특별한 조치가 필요하지 않습니다.",
    },
}

def explain_attention_level(level: str) -> dict[str, str]:
    return _LEVEL_DESC.get(level, {"label": "❓", "description": "상황을 확인하세요."})

def build_attention_summary(attention: dict[str, Any]) -> str:
    level = attention.get("attention_level", "low")
    reasons = attention.get("attention_reasons", [])
    label = _LEVEL_DESC.get(level, {}).get("label", "")
    return f"{label} {' '.join(reasons)}"
