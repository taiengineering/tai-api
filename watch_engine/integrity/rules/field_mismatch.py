"""field_mismatch rule: Compare field values between two steps in the same trace.

Detects cases like submit.process_type='KCSC' vs read.process_type='kcsc'.
"""

import logging
from typing import Optional

logger = logging.getLogger("watch_engine.integrity.field_mismatch")


def check_field_mismatch(
    rule: dict,
    events_by_step: dict[str, list[dict]],
    trace_id: str,
) -> Optional[dict]:
    """Check if source_step and target_step field values match.

    Args:
        rule: Row from flow_integrity_rule_registry
        events_by_step: {step_key: [event_rows]} for this trace
        trace_id: Current trace_id

    Returns:
        engine_integrity_event dict if mismatch found, None if pass.
    """
    source_step = rule.get("source_step_key")
    target_step = rule.get("target_step_key")
    source_field = rule.get("source_field_path")
    target_field = rule.get("target_field_path")

    if not all([source_step, target_step, source_field, target_field]):
        return None

    source_events = events_by_step.get(source_step, [])
    target_events = events_by_step.get(target_step, [])

    if not source_events or not target_events:
        return None  # Steps not present, skip (may be incomplete flow)

    # Use last successful event for each step
    source_evt = _last_success(source_events)
    target_evt = _last_success(target_events)
    if not source_evt or not target_evt:
        return None

    source_payload = source_evt.get("payload_summary") or {}
    target_payload = target_evt.get("payload_summary") or {}

    source_val = source_payload.get(source_field)
    target_val = target_payload.get(target_field)

    if source_val is None or target_val is None:
        return None  # Field not present, skip

    # Compare (strict equality — case-sensitive)
    if str(source_val) == str(target_val):
        return None  # PASS

    # MISMATCH detected
    return {
        "tenant_id": rule.get("tenant_id"),
        "environment": rule.get("environment"),
        "service_key": rule.get("service_key"),
        "flow_key": rule.get("flow_key"),
        "step_key": target_step,
        "trace_id": trace_id,
        "event_type": "field_mismatch",
        "severity": rule.get("severity_on_fail", "WARNING"),
        "integrity_status": rule.get("integrity_status_on_fail", "mismatch"),
        "health_status": rule.get("health_status_on_fail", "warning"),
        "domain": rule.get("flow_key"),
        "description": f"Field mismatch: {source_step}.{source_field}='{source_val}' vs {target_step}.{target_field}='{target_val}'",
        "detail": {
            "rule_key": rule.get("rule_key"),
            "source_step": source_step,
            "target_step": target_step,
            "field": source_field,
            "submitted": source_val,
            "stored": target_val,
        },
        "source_event_id": target_evt.get("id"),
    }


def _last_success(events: list[dict]) -> Optional[dict]:
    """Get last event with result='success'."""
    for e in reversed(events):
        if e.get("result") == "success":
            return e
    return events[-1] if events else None
