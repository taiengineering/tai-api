"""stuck_detected rule: Detect flows that started but never completed.

Checks if last event in a trace is older than stuck_threshold_ms
and the flow has not reached its final step.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from services.time import now_kst

logger = logging.getLogger("watch_engine.integrity.stuck_detected")


def check_stuck_detected(
    flow_reg: dict,
    events_by_step: dict[str, list[dict]],
    trace_id: str,
    registered_steps: list[dict],
    now: Optional[datetime] = None,
) -> Optional[dict]:
    """Check if a flow is stuck (no progress beyond threshold).

    Args:
        flow_reg: Row from flow_registry
        events_by_step: {step_key: [event_rows]} for this trace
        trace_id: Current trace_id
        registered_steps: Rows from flow_step_registry for this flow
        now: Current time (injectable for testing)

    Returns:
        engine_integrity_event dict if stuck, None if ok.
    """
    if now is None:
        now = now_kst()

    threshold_ms = flow_reg.get("stuck_threshold_ms") or 60000
    threshold = timedelta(milliseconds=threshold_ms)

    # Find max step_order in registry (expected final step)
    max_registered = max(
        (s.get("step_order", 0) for s in registered_steps), default=0
    )

    # Find max step_order actually reached
    max_actual = -1
    last_event_time = None
    for step_key, evts in events_by_step.items():
        for e in evts:
            order = e.get("step_order", 0)
            if order > max_actual:
                max_actual = order
            evt_time = e.get("created_at")
            if evt_time:
                if isinstance(evt_time, str):
                    try:
                        evt_time = datetime.fromisoformat(evt_time.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        continue
                if last_event_time is None or evt_time > last_event_time:
                    last_event_time = evt_time

    # Flow completed (reached final step) — not stuck
    if max_actual >= max_registered:
        return None

    # No events at all
    if last_event_time is None:
        return None

    # Check if enough time has passed
    elapsed = now - last_event_time
    if elapsed < threshold:
        return None  # Still within threshold

    return {
        "tenant_id": flow_reg.get("tenant_id"),
        "environment": flow_reg.get("environment"),
        "service_key": flow_reg.get("service_key"),
        "flow_key": flow_reg.get("flow_key"),
        "trace_id": trace_id,
        "event_type": "stuck_detected",
        "severity": "CRITICAL",
        "integrity_status": "violation",
        "health_status": "critical",
        "domain": flow_reg.get("flow_key"),
        "description": f"Flow stuck at step_order {max_actual}/{max_registered}, elapsed {int(elapsed.total_seconds())}s > threshold {threshold_ms}ms",
        "detail": {
            "last_step_order": max_actual,
            "expected_final_order": max_registered,
            "elapsed_seconds": int(elapsed.total_seconds()),
            "threshold_ms": threshold_ms,
        },
    }
