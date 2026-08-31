"""Timeout Detector - Workflow 정지 탐지.

예: APPROVAL_PENDING 상태 1시간 초과.
detect only. auto transition 금지.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.workflow_integrity.schemas import DetectionResult
from services.time import now_kst

logger = logging.getLogger(__name__)


def detect_timeout(
    timeline_events: list[dict],
    rule: dict,
) -> DetectionResult:
    """타임아웃 탐지.

    Args:
        timeline_events: workflow_event_log 이벤트 목록 (occurred_at DESC)
        rule: integrity rule (config.target_state, evaluation_window_sec)

    Returns:
        DetectionResult
    """
    config = rule.get("config") or {}
    target_state = config.get("target_state")
    window_sec = rule.get("evaluation_window_sec", 3600)
    rule_code = rule.get("rule_code", "UNKNOWN")

    if not target_state or not timeline_events:
        return DetectionResult(
            detected=False,
            rule_code=rule_code,
            integrity_type="TIMEOUT",
            severity=rule.get("severity", "WARNING"),
            message="평가 불가: target_state 또는 timeline 없음",
        )

    # 가장 최근 이벤트의 to_state가 target_state인지 확인
    latest = timeline_events[0]
    current_state = latest.get("to_state")

    if current_state != target_state:
        return DetectionResult(
            detected=False,
            rule_code=rule_code,
            integrity_type="TIMEOUT",
            severity=rule.get("severity", "WARNING"),
            message=f"현재 상태({current_state})가 target({target_state})과 불일치",
        )

    # 경과 시간 계산
    occurred_at_str = latest.get("occurred_at", "")
    try:
        occurred_at = datetime.fromisoformat(occurred_at_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return DetectionResult(
            detected=False,
            rule_code=rule_code,
            integrity_type="TIMEOUT",
            severity=rule.get("severity", "WARNING"),
            message="occurred_at 파싱 실패",
        )

    now = now_kst()
    elapsed_sec = (now - occurred_at).total_seconds()

    if elapsed_sec > window_sec:
        return DetectionResult(
            detected=True,
            rule_code=rule_code,
            integrity_type="TIMEOUT",
            severity=rule.get("severity", "WARNING"),
            message=f"{target_state} 상태 {int(elapsed_sec)}초 경과 (기준: {window_sec}초)",
            payload={
                "target_state": target_state,
                "elapsed_sec": int(elapsed_sec),
                "threshold_sec": window_sec,
                "since": occurred_at_str,
            },
        )

    return DetectionResult(
        detected=False,
        rule_code=rule_code,
        integrity_type="TIMEOUT",
        severity=rule.get("severity", "WARNING"),
        message=f"{target_state} 상태 {int(elapsed_sec)}초 경과 (기준 이내)",
    )
