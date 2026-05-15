"""Missing Step Detector - 필수 상태 누락 탐지.

예: 완료된 workflow에서 VALIDATING 단계 누락.
"""
from __future__ import annotations

import logging

from services.workflow_integrity.schemas import DetectionResult

logger = logging.getLogger(__name__)

# 종료 상태 목록
TERMINAL_STATES = {"COMPLETED", "FAILED", "REJECTED", "TIMEOUT"}


def detect_missing_step(
    timeline_events: list[dict],
    rule: dict,
) -> DetectionResult:
    """필수 단계 누락 탐지.

    Args:
        timeline_events: workflow_event_log (occurred_at ASC)
        rule: integrity rule (config.required_step)

    Returns:
        DetectionResult
    """
    config = rule.get("config") or {}
    required_step = config.get("required_step")
    rule_code = rule.get("rule_code", "UNKNOWN")
    severity = rule.get("severity", "CRITICAL")

    if not required_step:
        return DetectionResult(
            detected=False,
            rule_code=rule_code,
            integrity_type="MISSING_STEP",
            severity=severity,
            message="평가 불가: required_step 없음",
        )

    if not timeline_events:
        return DetectionResult(
            detected=False,
            rule_code=rule_code,
            integrity_type="MISSING_STEP",
            severity=severity,
            message="timeline 없음",
        )

    # 마지막 상태가 종료 상태인지 확인
    last_state = timeline_events[-1].get("to_state", "")
    if last_state not in TERMINAL_STATES:
        return DetectionResult(
            detected=False,
            rule_code=rule_code,
            integrity_type="MISSING_STEP",
            severity=severity,
            message=f"workflow 미완료 ({last_state}) - 평가 보류",
        )

    # 거쳐간 모든 상태 수집
    visited_states = set()
    for e in timeline_events:
        if e.get("from_state"):
            visited_states.add(e["from_state"])
        if e.get("to_state"):
            visited_states.add(e["to_state"])

    if required_step not in visited_states:
        return DetectionResult(
            detected=True,
            rule_code=rule_code,
            integrity_type="MISSING_STEP",
            severity=severity,
            message=f"필수 단계 누락: {required_step}",
            payload={
                "required_step": required_step,
                "visited_states": sorted(visited_states),
                "final_state": last_state,
            },
        )

    return DetectionResult(
        detected=False,
        rule_code=rule_code,
        integrity_type="MISSING_STEP",
        severity=severity,
        message=f"정상: {required_step} 단계 확인",
    )
