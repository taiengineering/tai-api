"""매칭 순수 헬퍼 — DB·HTTP 없음."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Set
from services.time import now_kst, serialize_external_utc

STATUS_TRANSITIONS: Dict[str, Set[str]] = {
    "RECEIVED": {"MATCHING", "CANCELLED"},
    "MATCHING": {"PROPOSED", "FAILED", "CANCELLED"},
    "PROPOSED": {"SELECTED", "CANCELLED"},
    "SELECTED": {"CONTRACTING", "DROPPED"},
    "CONTRACTING": {"CONTRACTED", "DROPPED"},
    "CONTRACTED": {"IN_PROGRESS"},
    "IN_PROGRESS": {"CONFIRMING"},
    "CONFIRMING": {"SETTLED"},
    "SETTLED": {"CLOSED"},
}

STATUS_TIMESTAMP_MAP: Dict[str, str] = {
    "MATCHING": "matched_at",
    "SELECTED": "selected_at",
    "CANCELLED": "cancelled_at",
}


def now_iso() -> str:
    return serialize_external_utc(now_kst())


def validate_status_transition(current: str, target: str) -> None:
    allowed = STATUS_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(
            f"'{current}' 상태에서 '{target}'로 변경할 수 없습니다. "
            f"허용 전이: {allowed}"
        )
