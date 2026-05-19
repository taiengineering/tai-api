"""Operator Activity — 운영자 행동 기록."""
from __future__ import annotations
from typing import Any

_ACTIVITY_LABELS = {
    "acknowledge": "상황 확인",
    "investigate": "영향 분석",
    "compare_recovery": "recovery 비교",
    "check_timeout": "timeout 확인",
    "check_tenant": "tenant 영향 확인",
    "check_deployment": "배포 확인",
    "escalate": "담당자 전달",
    "monitor": "관찰 중",
    "approve_closure": "종료 승인",
}

def build_activity_entry(action: str, operator_id: str, notes: str = "") -> dict[str, Any]:
    from datetime import datetime, timezone
    return {
        "action": action,
        "label": _ACTIVITY_LABELS.get(action, action),
        "operator_id": operator_id,
        "notes": notes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

def get_activity_labels() -> dict[str, str]:
    return dict(_ACTIVITY_LABELS)
