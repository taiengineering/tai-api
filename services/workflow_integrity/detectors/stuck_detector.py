"""Stuck Detector - 비종료 상태에서 장시간 이벤트 없음 탐지."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.workflow_integrity.schemas import DetectionResult
from services.time import now_kst

logger = logging.getLogger(__name__)

TERMINAL_STATES = {"COMPLETED", "FAILED", "REJECTED", "TIMEOUT"}


def detect_stuck(
    timeline_events: list[dict],
    rule: dict,
) -> DetectionResult:
    """Stuck 탐지.

    Args:
        timeline_events: workflow_event_log (occurred_at DESC)
        rule: integrity rule (evaluation_window_sec)

    Returns:
        DetectionResult
    """
    rule_code = rule.get("rule_code", "UNKNOWN")
    severity = rule.get("severity", "WARNING")
    window_sec = rule.get("evaluation_window_sec", 7200)

    if not timeline_events:
        return DetectionResult(
            detected=False,
            rule_code=rule_code,
            integrity_type="STUCK",
            severity=severity,
            message="timeline 없음",
        )

    latest = timeline_events[0]
    current_state = latest.get("to_state", "")

    # 종료 상태면 stuck 아님
    if current_state in TERMINAL_STATES:
        return DetectionResult(
            detected=False,
            rule_code=rule_code,
            integrity_type="STUCK",
            severity=severity,
            message=f"종료 상태({current_state}) - stuck 아님",
        )

    occurred_at_str = latest.get("occurred_at", "")
    try:
        occurred_at = datetime.fromisoformat(
            occurred_at_str.replace("Z", "+00:00")
        )
    except (ValueError, AttributeError):
        return DetectionResult(
            detected=False,
            rule_code=rule_code,
            integrity_type="STUCK",
            severity=severity,
            message="occurred_at 파싱 실패",
        )

    now = now_kst()
    elapsed_sec = (now - occurred_at).total_seconds()

    if elapsed_sec > window_sec:
        return DetectionResult(
            detected=True,
            rule_code=rule_code,
            integrity_type="STUCK",
            severity=severity,
            message=f"{current_state} 상태에서 {int(elapsed_sec)}초 정체 (기준: {window_sec}초)",
            payload={
                "current_state": current_state,
                "elapsed_sec": int(elapsed_sec),
                "threshold_sec": window_sec,
                "since": occurred_at_str,
            },
        )

    return DetectionResult(
        detected=False,
        rule_code=rule_code,
        integrity_type="STUCK",
        severity=severity,
        message=f"{current_state} 상태 {int(elapsed_sec)}초 경과 (기준 이내)",
    )
