"""Event validation — lightweight, non-blocking.

All validation returns (is_valid, errors) tuple.
Never raises exceptions. Never blocks service flow.
"""

import logging
from watch_engine.types import (
    VALID_RESULTS,
    VALID_ACTOR_TYPES,
    VALID_CONNECTOR_TYPES,
    VALID_ENVIRONMENTS,
    EventPayload,
)

logger = logging.getLogger("watch_engine.validation")


def validate_event(payload: EventPayload) -> tuple[bool, list[str]]:
    """Validate an EventPayload before insert.

    Returns:
        (True, []) if valid
        (False, [error_messages]) if invalid

    Never raises. Never blocks.
    """
    errors = []

    # Required string fields
    for field_name in ("tenant_id", "service_key", "flow_key", "step_key",
                       "trace_id", "event_type"):
        val = getattr(payload, field_name, None)
        if not val or not isinstance(val, str) or not val.strip():
            errors.append(f"{field_name} is required and must be non-empty string")

    # Enum checks
    if payload.result not in VALID_RESULTS:
        errors.append(f"result '{payload.result}' not in {VALID_RESULTS}")
    if payload.actor_type not in VALID_ACTOR_TYPES:
        errors.append(f"actor_type '{payload.actor_type}' not in {VALID_ACTOR_TYPES}")
    if payload.connector_type not in VALID_CONNECTOR_TYPES:
        errors.append(f"connector_type '{payload.connector_type}' not in {VALID_CONNECTOR_TYPES}")
    if payload.environment not in VALID_ENVIRONMENTS:
        errors.append(f"environment '{payload.environment}' not in {VALID_ENVIRONMENTS}")

    # step_order range
    if not isinstance(payload.step_order, int) or payload.step_order < 0:
        errors.append(f"step_order must be >= 0, got {payload.step_order}")

    if errors:
        logger.warning("Event validation failed: %s", errors)

    return (len(errors) == 0, errors)
