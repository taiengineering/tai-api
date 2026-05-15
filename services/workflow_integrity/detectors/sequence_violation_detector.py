"""Sequence Violation Detector - Workflow 흐름 순서 이상 탐지.

예: APPROVED 없이 COMPLETED.
"""
from __future__ import annotations

import logging

from services.workflow_integrity.schemas import DetectionResult

logger = logging.getLogger(__name__)


def detect_sequence_violation(
    timeline_events: list[dict],
    rule: dict,
) -> DetectionResult:
    """순서 위반 탐지.

    Args:
        timeline_events: workflow_event_log (occurred_at ASC)
        rule: integrity rule (config.required_before, config.target_state)

    Returns:
        DetectionResult
    """
    config = rule.get("config") or {}
    required_before = config.get("required_before")
    target_state = config.get("target_state")
    rule_code = rule.get("rule_code", "UNKNOWN")
    severity = rule.get("severity", "CRITICAL")

    if not required_before or not target_state:
        return DetectionResult(
            detected=False,
            rule_code=rule_code,
            integrity_type="SEQUENCE_VIOLATION",
            severity=severity,
            message="평가 불가: config 누락",
        )

    # timeline에서 to_state 순서 추출
    state_sequence = [e.get("to_state") for e in timeline_events]

    if target_state not in state_sequence:
        return DetectionResult(
            detected=False,
            rule_code=rule_code,
            integrity_type="SEQUENCE_VIOLATION",
            severity=severity,
            message=f"target_state({target_state})가 timeline에 없음",
        )

    target_idx = state_sequence.index(target_state)
    preceding_states = state_sequence[:target_idx]

    if required_before not in preceding_states:
        return DetectionResult(
            detected=True,
            rule_code=rule_code,
            integrity_type="SEQUENCE_VIOLATION",
            severity=severity,
            message=f"{required_before} 없이 {target_state} 도달",
            payload={
                "required_before": required_before,
                "target_state": target_state,
                "actual_sequence": state_sequence[:target_idx + 1],
            },
        )

    return DetectionResult(
        detected=False,
        rule_code=rule_code,
        integrity_type="SEQUENCE_VIOLATION",
        severity=severity,
        message=f"정상: {required_before} → {target_state} 순서 확인",
    )
