"""sequence_violation rule: Verify step_order continuity in a trace.

Detects:
- Missing required steps (gap in sequence)
- Out-of-order steps
"""

import logging
from typing import Optional

logger = logging.getLogger("watch_engine.integrity.sequence_violation")


def check_sequence_violation(
    rule: dict,
    events_by_step: dict[str, list[dict]],
    trace_id: str,
    registered_steps: list[dict],
) -> Optional[dict]:
    """Check step_order sequence integrity.

    Args:
        rule: Row from flow_integrity_rule_registry
        events_by_step: {step_key: [event_rows]} for this trace
        trace_id: Current trace_id
        registered_steps: Rows from flow_step_registry for this flow

    Returns:
        engine_integrity_event dict if violation found, None if pass.
    """
    required_steps = [
        s for s in registered_steps if s.get("is_required", True)
    ]
    required_steps.sort(key=lambda s: s.get("step_order", 0))

    # Collect actual step_orders from events
    actual_orders = set()
    for step_key, evts in events_by_step.items():
        for e in evts:
            actual_orders.add(e.get("step_order", -1))

    # Check for missing required steps
    missing = []
    for step in required_steps:
        step_key = step.get("step_key")
        if step_key not in events_by_step:
            missing.append({
                "step_key": step_key,
                "step_order": step.get("step_order"),
            })

    # Check for order violations (non-monotonic)
    actual_list = sorted(actual_orders)
    out_of_order = False
    all_event_orders = []
    for step_key, evts in events_by_step.items():
        for e in evts:
            all_event_orders.append((
                e.get("created_at", ""),
                e.get("step_order", 0),
            ))
    all_event_orders.sort(key=lambda x: x[0])  # Sort by time
    prev_order = -1
    for _, order in all_event_orders:
        if order < prev_order:
            out_of_order = True
            break
        prev_order = order

    if not missing and not out_of_order:
        return None  # PASS

    desc_parts = []
    if missing:
        names = [m["step_key"] for m in missing]
        desc_parts.append(f"Missing required steps: {names}")
    if out_of_order:
        desc_parts.append("Step order violation detected")

    return {
        "tenant_id": rule.get("tenant_id"),
        "environment": rule.get("environment"),
        "service_key": rule.get("service_key"),
        "flow_key": rule.get("flow_key"),
        "trace_id": trace_id,
        "event_type": "sequence_violation",
        "severity": rule.get("severity_on_fail", "CRITICAL"),
        "integrity_status": rule.get("integrity_status_on_fail", "violation"),
        "health_status": rule.get("health_status_on_fail", "critical"),
        "domain": rule.get("flow_key"),
        "description": "; ".join(desc_parts),
        "detail": {
            "rule_key": rule.get("rule_key"),
            "missing_steps": missing,
            "out_of_order": out_of_order,
            "actual_sequence": actual_list,
        },
    }
