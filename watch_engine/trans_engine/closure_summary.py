"""Closure Summary — 운영 종료 요약 생성."""
from __future__ import annotations
from typing import Any

_TYPE_LABELS = {
    "resolved": "운영자가 해결을 확인했습니다",
    "accepted": "위험을 허용 상태로 승인했습니다",
    "monitoring": "계속 관찰 상태로 설정했습니다",
    "false_alarm": "오탐으로 판단했습니다",
}

def build_closure_summary(
    situation_title: str, resolution_type: str,
    operator_id: str, operator_notes: str = "",
    activities: list[dict] | None = None,
) -> str:
    type_desc = _TYPE_LABELS.get(resolution_type, "종료 처리했습니다")
    parts = [f"{situation_title} 상황을 {type_desc}."]
    if activities:
        act_labels = [a.get("label", a.get("action", "")) for a in activities[:5]]
        parts.append(f"운영자 활동: {', '.join(act_labels)}")
    if operator_notes:
        parts.append(f"메모: {operator_notes}")
    return " ".join(parts)
