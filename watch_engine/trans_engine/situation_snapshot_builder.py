"""Situation Snapshot Builder — Operational Situation → Snapshot 생성.

build_operational_situation 결과를 Snapshot 구조로 변환하고
situation_id, lifecycle status를 계산한다.

절대 원칙:
  - Truth 아님
  - Incident 아님
  - Human Operational Awareness Snapshot만
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .situation_builder import build_operational_situation
from services.time import now_kst, serialize_external_utc


def build_situation_snapshot(
    events: list[dict[str, Any]],
    tenant_id: str | None = None,
    audience: str = "operator",
) -> dict[str, Any]:
    """events → Situation Snapshot dict."""
    situation = build_operational_situation(events, audience)

    situation_id = _compute_situation_id(events, tenant_id)
    status = _compute_lifecycle_status(events, situation)
    environment = _detect_environment(events)
    source_ids = [e.get("event_id") or e.get("id") for e in events if e.get("event_id") or e.get("id")]

    return {
        "id": str(uuid.uuid4()),
        "situation_id": situation_id,
        "tenant_id": tenant_id,
        "title": situation.get("situation_title", ""),
        "summary": situation.get("situation_summary", ""),
        "priority": (situation.get("priority") or {}).get("level", "P4"),
        "urgency": situation.get("urgency", "정보 수준"),
        "trend": situation.get("trend", "stable"),
        "impact": situation.get("impact", ""),
        "storyline": situation.get("storyline", []),
        "recommended_focus": situation.get("recommended_focus", []),
        "status": status,
        "confidence": situation.get("confidence", 0.5),
        "event_count": len(events),
        "source_event_ids": source_ids,
        "generated_at": serialize_external_utc(now_kst()),
        "environment": environment,
    }


def _compute_situation_id(
    events: list[dict[str, Any]],
    tenant_id: str | None,
) -> str:
    """situation_id = {tenant}:{domain}:{flow}:{type}"""
    tenant = tenant_id or "system"

    # domain / flow 추론
    flow_keys = [e.get("flow_key", "") for e in events if e.get("flow_key")]
    if flow_keys:
        first_fk = flow_keys[0]
        parts = first_fk.split("_")
        domain = parts[0] if parts else "general"
        flow = first_fk
    else:
        domain = "general"
        flow = "unknown"

    # situation type
    types = {e.get("event_type", "") for e in events}
    if "escalation" in types:
        sit_type = "escalation"
    elif "degradation" in types or "runtime.degraded" in types:
        sit_type = "degradation"
    elif "repeated_failure" in types:
        sit_type = "repeated_failure"
    elif any(t.endswith(".failed") for t in types):
        sit_type = "failure"
    else:
        sit_type = "anomaly"

    return f"{tenant}:{domain}:{flow}:{sit_type}"


def _compute_lifecycle_status(
    events: list[dict[str, Any]],
    situation: dict[str, Any],
) -> str:
    """이벤트 패턴 + trend로 lifecycle status 계산."""
    types = {e.get("event_type", "") for e in events}
    trend = situation.get("trend", "stable")
    priority = (situation.get("priority") or {}).get("level", "P4")

    if "recovery.completed" in types and trend == "improving":
        return "resolved"
    if trend == "improving":
        return "stabilizing"
    if "escalation" in types or priority == "P1":
        return "escalating"
    if "repeated_failure" in types or any(t.endswith(".failed") for t in types):
        return "active"
    if "degradation" in types or "runtime.degraded" in types:
        return "emerging"
    return "emerging"


def _detect_environment(events: list[dict[str, Any]]) -> str:
    """이벤트에서 환경 감지."""
    for e in events:
        if e.get("is_mock") or e.get("source") == "synthetic":
            return "mock"
    return "production"
