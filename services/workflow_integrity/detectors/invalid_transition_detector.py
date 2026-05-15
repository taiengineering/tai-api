"""Invalid Transition Detector - 허용되지 않은 상태 전이 탐지.

기준: workflow_transition_registry 참조.
"""
from __future__ import annotations

import logging

from services.workflow_integrity.schemas import DetectionResult

logger = logging.getLogger(__name__)


def detect_invalid_transition(
    timeline_events: list[dict],
    allowed_transitions: list[dict],
    rule: dict,
) -> list[DetectionResult]:
    """허용되지 않은 전이 탐지.

    Args:
        timeline_events: workflow_event_log (occurred_at ASC)
        allowed_transitions: workflow_transition_registry rows
        rule: integrity rule

    Returns:
        위반 건별 DetectionResult 리스트
    """
    rule_code = rule.get("rule_code", "UNKNOWN")
    severity = rule.get("severity", "CRITICAL")

    # 허용된 (from_state, to_state) 집합 구축
    allowed_set = set()
    for t in allowed_transitions:
        allowed_set.add((t["from_state"], t["to_state"]))

    results: list[DetectionResult] = []

    for event in timeline_events:
        from_state = event.get("from_state")
        to_state = event.get("to_state")

        # from_state가 None이면 초기 생성 이벤트 → 건너뜀
        if from_state is None:
            continue

        if (from_state, to_state) not in allowed_set:
            results.append(DetectionResult(
                detected=True,
                rule_code=rule_code,
                integrity_type="INVALID_TRANSITION",
                severity=severity,
                message=f"허용되지 않은 전이: {from_state} → {to_state}",
                payload={
                    "from_state": from_state,
                    "to_state": to_state,
                    "event_id": event.get("id"),
                    "occurred_at": event.get("occurred_at"),
                },
            ))

    return results
