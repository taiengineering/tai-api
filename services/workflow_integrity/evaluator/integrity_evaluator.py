"""Integrity Evaluator Engine.

역할: Workflow Timeline 기반 정상성 평가.
- timeline 조회
- rule 조회
- 이상 탐지 (각 detector 호출)
- integrity event 생성

절대 금지: 자동 수정, 상태 변경, Notification 직접 호출.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from db.supabase_client import get_supabase
from services.workflow_integrity.schemas import (
    DetectionResult,
    EvaluationReport,
    IntegrityEventCreate,
)
from services.workflow_integrity.registry.rule_registry import (
    get_enabled_rules,
    get_rules_by_type,
)
from services.workflow_integrity.events.integrity_event_store import (
    create_integrity_event,
)
from services.workflow_integrity.detectors.timeout_detector import detect_timeout
from services.workflow_integrity.detectors.invalid_transition_detector import (
    detect_invalid_transition,
)
from services.workflow_integrity.detectors.sequence_violation_detector import (
    detect_sequence_violation,
)
from services.workflow_integrity.detectors.missing_step_detector import (
    detect_missing_step,
)
from services.workflow_integrity.detectors.stuck_detector import detect_stuck
from services.workflow_integrity.hooks.alert_hook import emit_integrity_alert
from services.time import now_kst

logger = logging.getLogger(__name__)


async def _fetch_timeline(workflow_id: UUID, order_desc: bool = True) -> list[dict]:
    """workflow_event_log에서 timeline 조회."""
    sb = get_supabase()
    resp = (
        sb.table("workflow_event_log")
        .select("*")
        .eq("workflow_id", str(workflow_id))
        .order("occurred_at", desc=order_desc)
        .execute()
    )
    return resp.data or []


async def _fetch_allowed_transitions(workflow_type: str) -> list[dict]:
    """workflow_transition_registry에서 허용 전이 조회."""
    sb = get_supabase()
    resp = (
        sb.table("workflow_transition_registry")
        .select("*")
        .eq("workflow_type", workflow_type)
        .execute()
    )
    return resp.data or []


async def evaluate_workflow(
    workflow_id: UUID,
    workflow_type: str = "COMMON",
    persist_events: bool = True,
) -> EvaluationReport:
    """단일 workflow에 대한 전체 Integrity 평가.

    Args:
        workflow_id: 평가 대상 workflow ID
        workflow_type: workflow 유형
        persist_events: True면 탐지 결과를 integrity_event로 저장

    Returns:
        EvaluationReport
    """
    # 1. Timeline 조회
    timeline_desc = await _fetch_timeline(workflow_id, order_desc=True)
    timeline_asc = list(reversed(timeline_desc))

    # 2. 규칙 조회
    rules = await get_enabled_rules(workflow_type)

    # 3. 허용 전이 조회 (INVALID_TRANSITION용)
    allowed_transitions = await _fetch_allowed_transitions(workflow_type)

    # 4. 각 detector 실행
    detections: list[DetectionResult] = []

    for rule in rules:
        rt = rule.get("rule_type")

        if rt == "TIMEOUT":
            result = detect_timeout(timeline_desc, rule)
            detections.append(result)

        elif rt == "INVALID_TRANSITION":
            results = detect_invalid_transition(
                timeline_asc, allowed_transitions, rule
            )
            detections.extend(results)

        elif rt == "SEQUENCE_VIOLATION":
            result = detect_sequence_violation(timeline_asc, rule)
            detections.append(result)

        elif rt == "MISSING_STEP":
            result = detect_missing_step(timeline_asc, rule)
            detections.append(result)

        elif rt == "STUCK":
            result = detect_stuck(timeline_desc, rule)
            detections.append(result)

    # 5. 위반 건만 필터
    violations = [d for d in detections if d.detected]

    # 6. Integrity Event 저장 + Alert Hook
    if persist_events:
        for v in violations:
            # 해당 rule의 DB id 찾기
            matching_rule = next(
                (r for r in rules if r.get("rule_code") == v.rule_code),
                None,
            )
            rule_id = matching_rule.get("id") if matching_rule else None

            event = IntegrityEventCreate(
                workflow_id=workflow_id,
                workflow_type=workflow_type,
                rule_id=rule_id,
                integrity_type=v.integrity_type,
                severity=v.severity,
                payload=v.payload,
            )
            await create_integrity_event(event)

            # Alert Hook (interface only, no direct notification)
            await emit_integrity_alert(
                workflow_id=workflow_id,
                rule_code=v.rule_code,
                severity=v.severity,
                message=v.message,
                payload=v.payload,
            )

    return EvaluationReport(
        workflow_id=workflow_id,
        workflow_type=workflow_type,
        evaluated_at=now_kst(),
        total_rules_checked=len(rules),
        violations_found=len(violations),
        detections=detections,
    )
