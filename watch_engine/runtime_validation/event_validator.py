"""Event Validator — Runtime Event 통합 검증.

Canonical Registry + Naming + Severity + Ownership + Tenant + Trace.
"""

import re
import logging
from typing import Optional
from datetime import datetime, timezone

from watch_engine.runtime_validation.canonical_registry import (
    is_registered_event, can_runtime_emit, can_runtime_set_severity,
    VALID_SEVERITIES,
)
from watch_engine.runtime_validation.validation_errors import (
    InvalidRuntimeEvent, UnregisteredEventType,
    ForbiddenSeverityMutation, ForbiddenRuntimeMutation,
    InvalidTenantBoundary, InvalidTraceIntegrity,
)

logger = logging.getLogger("watch_engine.runtime_validation")

# Naming: <domain>.<action> or <domain>.<sub_action>
_NAMING_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


def validate_event(
    event: dict,
    runtime: str = "control",
    raise_on_error: bool = True,
) -> dict:
    """Event payload \ud1b5\ud569 \uac80\uc99d.

    Returns: {"valid": bool, "errors": [str], "warnings": [str]}
    """
    errors = []
    warnings = []

    event_type = event.get("event_type", "")
    severity = event.get("severity", "")
    tenant_id = event.get("tenant_id", "")
    trace_id = event.get("trace_id", "")
    environment = event.get("environment") or \
        (event.get("source", {}).get("environment", ""))

    # 1. \ud544\uc218 \ud544\ub4dc
    if not event_type:
        errors.append("event_type is required")
    if not tenant_id:
        errors.append("tenant_id is required")
    if not trace_id:
        warnings.append("trace_id is missing (will be auto-generated)")
    if not event.get("timestamp"):
        warnings.append("timestamp is missing")

    # 2. Naming \uac80\uc99d
    if event_type and not _NAMING_PATTERN.match(event_type):
        errors.append(f"Invalid event naming: '{event_type}'. Must be <domain>.<action> lowercase")

    # 3. Canonical Registry \uac80\uc99d
    if event_type and not is_registered_event(event_type):
        warnings.append(f"Unregistered event type: {event_type}")

    # 4. Severity \uac80\uc99d
    if severity:
        if severity not in VALID_SEVERITIES:
            errors.append(f"Invalid severity: '{severity}'. Must be one of {VALID_SEVERITIES}")
        elif not can_runtime_set_severity(runtime, severity):
            errors.append(f"{runtime} cannot set severity {severity}")

    # 5. Ownership \uac80\uc99d
    if event_type and not can_runtime_emit(runtime, event_type):
        errors.append(f"{runtime} cannot emit {event_type}")

    # 6. Tenant Boundary
    if tenant_id and tenant_id.startswith("mock_") and environment == "production":
        errors.append("Mock tenant cannot emit production events")

    result = {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }

    if errors:
        _log_violation(event, runtime, errors)
        if raise_on_error:
            raise InvalidRuntimeEvent(
                reason="; ".join(errors),
                event_type=event_type,
                runtime=runtime,
            )

    return result


def validate_runtime_event(
    runtime: str,
    event: dict,
    raise_on_error: bool = True,
) -> dict:
    """Runtime Context \uae30\ubc18 \uac80\uc99d (\ub798\ud37c)."""
    return validate_event(event, runtime=runtime, raise_on_error=raise_on_error)


def _log_violation(event: dict, runtime: str, errors: list) -> None:
    """Validation violation \ub85c\uae45."""
    logger.warning(
        "[VALIDATION] runtime=%s event_type=%s tenant=%s errors=%s",
        runtime,
        event.get("event_type", "?"),
        event.get("tenant_id", "?"),
        "; ".join(errors),
    )

    # DB \uae30\ub85d (\uc120\ud0dd\uc801)
    try:
        from db.supabase_client import get_supabase
        sb = get_supabase()
        sb.table("engine_integrity_event").insert({
            "tenant_id": event.get("tenant_id") or "system",
            "environment": "production",
            "service_key": "tai-api",
            "flow_key": "runtime_validation",
            "trace_id": event.get("trace_id") or f"validation_{runtime}",
            "event_type": "watch.sovereignty_violation",
            "severity": "WARNING",
            "integrity_status": "violation",
            "health_status": "warning",
            "domain": "validation",
            "description": f"[VALIDATION] {runtime}: {'; '.join(errors)}",
            "resolved": False,
        }).execute()
    except Exception:
        pass
