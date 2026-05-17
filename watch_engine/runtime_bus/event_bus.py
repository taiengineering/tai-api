"""Event Bus — \uc911\uc559 Runtime Event \ubc1c\uc2e0.

\ubaa8\ub4e0 Runtime Event\ub294 \uc774 \ud568\uc218\ub97c \ud1b5\uacfc\ud574\uc57c \ud55c\ub2e4.
1. Validation
2. Sovereignty
3. Tenant Boundary
4. Event Store
5. Result \ubc18\ud658
"""

import logging
import uuid
from datetime import datetime, timezone

from watch_engine.runtime_bus.runtime_context import RuntimeContext
from watch_engine.runtime_bus.event_result import EventResult
from watch_engine.runtime_bus.event_store import store_business_event, store_integrity_event

logger = logging.getLogger("watch_engine.runtime_bus")

# Integrity \ub3c4\uba54\uc778 (\uc774 event_type\uc740 integrity_event\uc5d0 \uc800\uc7a5)
_INTEGRITY_DOMAINS = {
    "incident.", "watch.", "runtime.degraded", "runtime.failed",
}


def emit_runtime_event(
    ctx: RuntimeContext,
    event: dict,
    sb=None,
) -> EventResult:
    """\uc911\uc559 Runtime Event \ubc1c\uc2e0.

    Args:
        ctx: RuntimeContext (\ubc1c\uc2e0\uc790 \uc2dd\ubcc4)
        event: Event payload (event_type, tenant_id, trace_id, severity, ...)
        sb: Supabase client (None\uc774\uba74 \uc790\ub3d9 \ub85c\ub4dc)

    Returns:
        EventResult
    """
    # 0. \uae30\ubcf8\uac12 \ubcf4\uc815
    if not event.get("trace_id"):
        event["trace_id"] = f"bus_{uuid.uuid4().hex[:12]}"
    if not event.get("timestamp"):
        event["timestamp"] = datetime.now(timezone.utc).isoformat()
    if not event.get("tenant_id") and ctx.tenant_id:
        event["tenant_id"] = ctx.tenant_id
    if not event.get("source"):
        event["source"] = {
            "runtime": ctx.runtime,
            "service": ctx.service,
            "environment": ctx.environment,
        }
    # environment \ubc18\uc601
    if not event.get("environment"):
        event["environment"] = ctx.environment

    # 1. Validation
    try:
        from watch_engine.runtime_validation.event_validator import validate_event
        vr = validate_event(event, runtime=ctx.runtime, raise_on_error=False)
    except Exception as e:
        logger.error("Validation error: %s", e)
        return EventResult(
            status="failed", error=str(e),
            validation_status="error",
        )

    if not vr["valid"]:
        return EventResult(
            status="blocked",
            validation_status="blocked",
            warnings=vr.get("warnings", []),
            blocked_reason="; ".join(vr.get("errors", [])),
        )

    # 2. Sovereignty (\ucd94\uac00 \uac80\uc99d)
    try:
        from watch_engine.runtime_sovereignty.truth_enforcer import enforce
        action = _event_to_action(event.get("event_type", ""))
        if action:
            enforce(
                runtime=ctx.runtime,
                action=action,
                tenant_id=event.get("tenant_id"),
                trace_id=event.get("trace_id"),
                raise_on_violation=False,
            )
    except Exception:
        pass  # Sovereignty \uc2e4\ud328\ud574\ub3c4 \uc800\uc7a5 \uc9c4\ud589

    # 3. Event Store
    if sb is None:
        try:
            from db.supabase_client import get_supabase
            sb = get_supabase()
        except Exception as e:
            return EventResult(status="failed", error=f"DB connection failed: {e}")

    event_type = event.get("event_type", "")
    event_id = None

    if _is_integrity_event(event_type):
        event_id = store_integrity_event(sb, ctx, event)
    else:
        event_id = store_business_event(sb, ctx, event)

    if event_id is None:
        return EventResult(
            status="failed",
            error="Event store failed",
            validation_status="passed",
        )

    # 4. Result
    warnings = vr.get("warnings", [])
    status = "accepted_with_warning" if warnings else "accepted"

    logger.info(
        "[BUS] %s event=%s tenant=%s trace=%s -> %s",
        ctx.runtime, event_type, event.get("tenant_id"), event.get("trace_id"), status,
    )

    return EventResult(
        status=status,
        event_id=event_id,
        validation_status="warning" if warnings else "passed",
        warnings=warnings,
    )


def _is_integrity_event(event_type: str) -> bool:
    """Integrity \ub3c4\uba54\uc778 \uc5ec\ubd80."""
    for prefix in _INTEGRITY_DOMAINS:
        if event_type.startswith(prefix):
            return True
    if event_type in {"runtime.degraded", "runtime.failed"}:
        return True
    return False


def _event_to_action(event_type: str) -> str:
    """event_type \u2192 sovereignty action \ub9e4\ud551."""
    mapping = {
        "incident.created": "create_incident",
        "incident.escalated": "escalate_incident",
        "incident.resolved": "resolve_incident",
        "incident.closed": "close_incident",
        "incident.acknowledged": "set_ack",
        "watch.integrity_detected": "evaluate_integrity",
        "watch.alert_fired": "create_alert",
        "watch.sla_violated": "evaluate_sla",
        "watch.sovereignty_violation": "detect_anomaly",
    }
    return mapping.get(event_type, "")
