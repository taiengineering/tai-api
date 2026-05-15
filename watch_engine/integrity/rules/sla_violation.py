"""sla_violation rule: Business Workflow SLA 위반 탐지.

trace 시작 → terminal event 시간 기준 duration 계산.
completed인데 느림 / stuck / abandoned 모두 포함.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("watch_engine.integrity.rules.sla_violation")


def check_sla_violation(
    sla_reg: dict,
    events_by_step: dict[str, list[dict]],
    trace_id: str,
    flow_status: dict,
) -> list[dict]:
    """Check workflow SLA against registry thresholds.

    Args:
        sla_reg: Row from workflow_sla_registry
        events_by_step: {step_key: [event_rows]}
        trace_id: Current trace_id
        flow_status: From compute_flow_status()

    Returns:
        List of engine_integrity_event dicts (0~2: warning + critical)
    """
    if not sla_reg or not sla_reg.get("enabled"):
        return []

    flow_key = sla_reg.get("flow_key", "")
    warning_ms = sla_reg.get("sla_warning_ms", 10000)
    critical_ms = sla_reg.get("sla_critical_ms", 60000)

    # Calculate duration: first event -> last event
    first_time = None
    last_time = None
    tenant_id = None
    environment = None
    service_key = None

    for step_key, evts in events_by_step.items():
        for e in evts:
            t = _parse_time(e.get("created_at"))
            if t is None:
                continue
            if first_time is None or t < first_time:
                first_time = t
            if last_time is None or t > last_time:
                last_time = t
            if not tenant_id:
                tenant_id = e.get("tenant_id")
                environment = e.get("environment", "production")
                service_key = e.get("service_key", "tai-api")

    if first_time is None or last_time is None:
        return []

    duration_ms = int((last_time - first_time).total_seconds() * 1000)
    status = flow_status.get("status", "running")

    # running flows: not yet complete, skip SLA check
    if status == "running":
        return []

    issues = []
    base = {
        "tenant_id": tenant_id,
        "environment": environment,
        "service_key": service_key,
        "flow_key": flow_key,
        "trace_id": trace_id,
        "domain": flow_key,
    }

    # Critical check first (superset of warning)
    if duration_ms >= critical_ms:
        issues.append({
            **base,
            "event_type": "sla_critical",
            "severity": "CRITICAL",
            "integrity_status": "violation",
            "health_status": "critical",
            "description": f"SLA CRITICAL: {flow_key} {duration_ms}ms (\uae30\uc900 {critical_ms}ms), \uc0c1\ud0dc={status}",
            "detail": {
                "flow_key": flow_key,
                "duration_ms": duration_ms,
                "threshold_ms": critical_ms,
                "flow_status": status,
                "impact_level": sla_reg.get("business_impact_level"),
            },
        })
    elif duration_ms >= warning_ms:
        issues.append({
            **base,
            "event_type": "sla_warning",
            "severity": "WARNING",
            "integrity_status": "degraded",
            "health_status": "warning",
            "description": f"SLA WARNING: {flow_key} {duration_ms}ms (\uae30\uc900 {warning_ms}ms), \uc0c1\ud0dc={status}",
            "detail": {
                "flow_key": flow_key,
                "duration_ms": duration_ms,
                "threshold_ms": warning_ms,
                "flow_status": status,
                "impact_level": sla_reg.get("business_impact_level"),
            },
        })

    # stuck/abandoned = workflow_degraded
    if status in ("stuck", "abandoned") and not any(i["event_type"] == "sla_critical" for i in issues):
        issues.append({
            **base,
            "event_type": "workflow_degraded",
            "severity": "CRITICAL" if status == "abandoned" else "WARNING",
            "integrity_status": "degraded",
            "health_status": "critical" if status == "abandoned" else "warning",
            "description": f"Workflow degraded: {flow_key} \uc0c1\ud0dc={status}, {duration_ms}ms \uacbd\uacfc",
            "detail": {
                "flow_key": flow_key,
                "duration_ms": duration_ms,
                "flow_status": status,
            },
        })

    return issues


def _parse_time(val) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
