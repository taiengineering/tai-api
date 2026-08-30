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
from watch_engine.canonical import (
    is_valid_event_name,
    is_valid_actor_kind,
    is_valid_outcome,
    is_tz_aware_datetime,
    PLACEHOLDER_TRACE,
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


def validate_contract_v1(payload: EventPayload) -> tuple[bool, list[str]]:
    """Application-level mirror of be_contract_v1_chk (§17). Never raises.

    A payload is a valid Common Event Contract v1 row iff event_version == 1
    AND the full canonical core is present, non-placeholder, and occurred_at is
    timezone-aware. Legacy payloads (event_version is None) are NOT v1 and
    intentionally return (False, [...]) here; callers use this ONLY to gate v1
    emission, never to reject legacy writes.
    """
    errors: list[str] = []

    if payload.event_version != 1:
        errors.append(f"event_version must be 1, got {payload.event_version!r}")
    if not is_valid_event_name(payload.event_name):
        errors.append(f"event_name invalid/missing: {payload.event_name!r}")
    if not is_valid_actor_kind(payload.actor_kind):
        errors.append(f"actor_kind invalid/missing: {payload.actor_kind!r}")
    if not (isinstance(payload.actor_ref, str) and payload.actor_ref.strip()):
        errors.append("actor_ref is required and must be non-empty")

    # §12 occurred_at: required, parseable, timezone-aware.
    if not payload.occurred_at:
        errors.append("occurred_at is required")
    elif not is_tz_aware_datetime(payload.occurred_at):
        errors.append(
            f"occurred_at must be timezone-aware: {payload.occurred_at!r}"
        )

    tid = payload.trace_id
    if not (isinstance(tid, str) and tid.strip()) or tid in PLACEHOLDER_TRACE:
        errors.append(f"trace_id missing or placeholder: {tid!r}")
    for field_name in ("service_key", "tenant_id", "environment"):
        val = getattr(payload, field_name, None)
        if not (isinstance(val, str) and val.strip()):
            errors.append(f"{field_name} is required")

    if not is_valid_outcome(payload.outcome):
        errors.append(f"outcome invalid: {payload.outcome!r}")

    if errors:
        logger.warning("Contract v1 validation failed: %s", errors)

    return (len(errors) == 0, errors)
