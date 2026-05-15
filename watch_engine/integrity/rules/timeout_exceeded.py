"""timeout_exceeded rule: Detect steps that took longer than timeout_ms.

Compares created_at between consecutive steps.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("watch_engine.integrity.timeout_exceeded")


def check_timeout_exceeded(
    events_by_step: dict[str, list[dict]],
    trace_id: str,
    registered_steps: list[dict],
    flow_key: str,
    tenant_id: str,
    environment: str = "production",
    service_key: str = "tai-api",
) -> list[dict]:
    """Check each step for timeout violations.

    Returns list of engine_integrity_event dicts (0 or more).
    """
    results = []

    # Build step timeout map
    step_timeout = {}
    for s in registered_steps:
        if s.get("timeout_ms"):
            step_timeout[s["step_key"]] = s["timeout_ms"]

    if not step_timeout:
        return []

    # Flatten events sorted by step_order then created_at
    all_events = []
    for step_key, evts in events_by_step.items():
        for e in evts:
            all_events.append(e)
    all_events.sort(key=lambda e: (e.get("step_order", 0), e.get("created_at", "")))

    # Check duration between consecutive steps
    for i in range(1, len(all_events)):
        curr = all_events[i]
        prev = all_events[i - 1]
        curr_step = curr.get("step_key")

        timeout_ms = step_timeout.get(curr_step)
        if not timeout_ms:
            continue

        prev_time = _parse_time(prev.get("created_at"))
        curr_time = _parse_time(curr.get("created_at"))
        if not prev_time or not curr_time:
            continue

        elapsed_ms = (curr_time - prev_time).total_seconds() * 1000

        if elapsed_ms <= timeout_ms:
            continue  # Within threshold

        results.append({
            "tenant_id": tenant_id,
            "environment": environment,
            "service_key": service_key,
            "flow_key": flow_key,
            "step_key": curr_step,
            "trace_id": trace_id,
            "event_type": "timeout_exceeded",
            "severity": "WARNING",
            "integrity_status": "violation",
            "health_status": "warning",
            "domain": flow_key,
            "description": f"Step {curr_step} took {int(elapsed_ms)}ms, threshold {timeout_ms}ms",
            "detail": {
                "step_key": curr_step,
                "elapsed_ms": int(elapsed_ms),
                "threshold_ms": timeout_ms,
            },
            "source_event_id": curr.get("id"),
        })

    return results


def _parse_time(val) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
