"""Synthetic Event Contract.

Synthetic → Platform Event 규약 정의.
실제 스키마는 schemas.py의 SyntheticEvent 사용.
이 모듈은 contract 유효성 검증 유틸리티.
"""
from __future__ import annotations

from services.browser_synthetic.schemas import SyntheticEvent

# 필수 필드
REQUIRED_FIELDS = {
    "synthetic_check",
    "workflow_type",
    "execution_status",
    "occurred_at",
}

# 허용 execution_status
ALLOWED_STATUSES = {"SUCCESS", "FAILED", "TIMEOUT", "ERROR", "SKIPPED"}


def validate_synthetic_event(event: SyntheticEvent) -> list[str]:
    """이벤트 contract 유효성 검증.

    Returns:
        오류 메시지 리스트 (빈 리스트 = 유효)
    """
    errors: list[str] = []

    if not event.synthetic_check:
        errors.append("synthetic_check is required")
    if not event.workflow_type:
        errors.append("workflow_type is required")
    if event.execution_status not in ALLOWED_STATUSES:
        errors.append(
            f"Invalid execution_status: {event.execution_status}. "
            f"Allowed: {ALLOWED_STATUSES}"
        )
    if not event.occurred_at:
        errors.append("occurred_at is required")

    return errors
