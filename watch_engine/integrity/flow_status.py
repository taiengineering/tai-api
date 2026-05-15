"""Flow Completion Status Calculator.

Determines the completion state of a trace:
- completed: terminal_success step reached with result=success
- failed: terminal_failure step reached with result=failure
- running: still within threshold, not yet terminal
- stuck: beyond threshold, no terminal reached
- abandoned: very old, no terminal reached

This module is the foundation for false positive suppression.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("watch_engine.integrity.flow_status")

# Flow completion states
COMPLETED = "completed"
FAILED = "failed"
RUNNING = "running"
STUCK = "stuck"
ABANDONED = "abandoned"

# Rules that should be suppressed when flow status is FAILED
SUPPRESS_ON_FAILURE = frozenset({"sequence_violation", "stuck_detected"})

# Rules that are NEVER suppressed (data integrity always matters)
NEVER_SUPPRESS = frozenset({"field_mismatch", "timeout_exceeded"})


def compute_flow_status(
    events_by_step: dict[str, list[dict]],
    registered_steps: list[dict],
    stuck_threshold_ms: int = 60000,
    now: Optional[datetime] = None,
) -> dict:
    """Compute flow completion status for a trace.

    Returns:
        {
            "status": "completed" | "failed" | "running" | "stuck" | "abandoned",
            "terminal_step": step_key or None,
            "terminal_result": "success" | "failure" or None,
            "last_step_order": int,
            "max_registered_order": int,
            "elapsed_since_last_ms": int,
        }
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Build terminal step maps
    success_terminals = set()
    failure_terminals = set()
    for s in registered_steps:
        if s.get("is_terminal_success"):
            success_terminals.add(s["step_key"])
        if s.get("is_terminal_failure"):
            failure_terminals.add(s["step_key"])

    max_registered = max(
        (s.get("step_order", 0) for s in registered_steps), default=0
    )

    # Find last event info
    last_step_order = -1
    last_event_time = None
    terminal_step = None
    terminal_result = None

    for step_key, evts in events_by_step.items():
        for e in evts:
            order = e.get("step_order", 0)
            evt_time = _parse_time(e.get("created_at"))
            result = e.get("result")

            if order > last_step_order:
                last_step_order = order
            if evt_time and (last_event_time is None or evt_time > last_event_time):
                last_event_time = evt_time

            # Check terminal success
            if step_key in success_terminals and result == "success":
                terminal_step = step_key
                terminal_result = "success"

            # Check terminal failure
            if step_key in failure_terminals and result == "failure":
                terminal_step = step_key
                terminal_result = "failure"

    # Calculate elapsed
    elapsed_ms = 0
    if last_event_time:
        elapsed_ms = int((now - last_event_time).total_seconds() * 1000)

    # Determine status
    if terminal_result == "success":
        status = COMPLETED
    elif terminal_result == "failure":
        status = FAILED
    elif last_event_time is None:
        status = RUNNING  # No events yet
    elif elapsed_ms > stuck_threshold_ms * 10:  # 10x threshold = abandoned
        status = ABANDONED
    elif elapsed_ms > stuck_threshold_ms:
        status = STUCK
    else:
        status = RUNNING

    return {
        "status": status,
        "terminal_step": terminal_step,
        "terminal_result": terminal_result,
        "last_step_order": last_step_order,
        "max_registered_order": max_registered,
        "elapsed_since_last_ms": elapsed_ms,
    }


def should_suppress(event_type: str, flow_status: str) -> bool:
    """Determine if an integrity event should be suppressed.

    Args:
        event_type: The integrity event type (e.g., 'stuck_detected')
        flow_status: The computed flow status

    Returns:
        True if the event should NOT be recorded.
    """
    # Never suppress data integrity rules
    if event_type in NEVER_SUPPRESS:
        return False

    # Suppress stuck/sequence for failed flows
    if flow_status == FAILED and event_type in SUPPRESS_ON_FAILURE:
        return True

    return False


def _parse_time(val) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
