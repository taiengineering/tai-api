"""Canonical Event Registry — Runtime 버전.

TASK 36 문서 Registry를 코드로 변환.
39개 Canonical Event 등록.
"""

# Platform Core Events
CORE_EVENTS = {
    # Workflow
    "workflow.started", "workflow.completed", "workflow.failed",
    "workflow.timeout", "workflow.blocked", "workflow.retried",
    # Step
    "step.started", "step.completed", "step.failed", "step.skipped",
    # Payment
    "payment.pending", "payment.completed", "payment.failed",
    "payment.cancelled", "payment.refunded",
    # Document
    "document.generated", "document.failed",
    "document.template_missing", "document.downloaded",
    # Subscription
    "subscription.activated", "subscription.paused",
    "subscription.cancelled", "subscription.failed", "subscription.ended",
    # Runtime
    "runtime.started", "runtime.degraded", "runtime.recovered", "runtime.failed",
    # Incident (Control \uc804\uc6a9)
    "incident.created", "incident.escalated", "incident.acknowledged",
    "incident.resolved", "incident.closed",
}

# Watch Engine Domain Events
WATCH_EVENTS = {
    "watch.integrity_detected", "watch.alert_fired", "watch.sla_violated",
    "watch.tenant_risk_changed", "watch.stability_changed",
    "watch.pattern_detected", "watch.recovery_recommended",
    "watch.synthetic_completed", "watch.sovereignty_violation",
}

# \uc804\uccb4 Canonical Events
CANONICAL_EVENTS = CORE_EVENTS | WATCH_EVENTS

# Runtime\ubcc4 \uc0dd\uc131 \uac00\ub2a5 Event
RUNTIME_EVENT_OWNERSHIP = {
    "control": CANONICAL_EVENTS,  # Control\uc740 \ubaa8\ub4e0 event \uc0dd\uc131 \uac00\ub2a5
    "workflow": {
        "workflow.started", "workflow.completed", "workflow.failed",
        "workflow.timeout", "workflow.blocked", "workflow.retried",
        "step.started", "step.completed", "step.failed", "step.skipped",
    },
    "notification": set(),  # Truth event \uc0dd\uc131 \ubd88\uac00
    "delivery": set(),
    "ui": set(),
    "adapter": set(),
}

# Severity \uc0dd\uc131 \uad8c\ud55c
SEVERITY_OWNERSHIP = {
    "INFO": {"control", "workflow", "notification", "delivery", "ui", "adapter"},
    "WARNING": {"control"},
    "CRITICAL": {"control"},
    "FATAL": {"control"},
}

VALID_SEVERITIES = {"INFO", "WARNING", "CRITICAL", "FATAL"}


def is_registered_event(event_type: str) -> bool:
    """Canonical Event \ub4f1\ub85d \uc5ec\ubd80."""
    if event_type in CANONICAL_EVENTS:
        return True
    # custom.* / partner.* \ud5c8\uc6a9
    if event_type.startswith(("custom.", "partner.")):
        return True
    return False


def can_runtime_emit(runtime: str, event_type: str) -> bool:
    """Runtime\uc774 \ud574\ub2f9 event\ub97c \uc0dd\uc131\ud560 \uc218 \uc788\ub294\uc9c0."""
    allowed = RUNTIME_EVENT_OWNERSHIP.get(runtime, set())
    if event_type in allowed:
        return True
    # custom.* \ub124\uc784\uc2a4\ud398\uc774\uc2a4\ub294 \ubaa8\ub4e0 runtime \ud5c8\uc6a9
    if event_type.startswith(("custom.", "partner.")):
        return True
    return False


def can_runtime_set_severity(runtime: str, severity: str) -> bool:
    """Runtime\uc774 \ud574\ub2f9 severity\ub97c \uc124\uc815\ud560 \uc218 \uc788\ub294\uc9c0."""
    allowed = SEVERITY_OWNERSHIP.get(severity, set())
    return runtime in allowed


def get_all_events() -> dict:
    """\uc804\uccb4 \ub4f1\ub85d Event \ubaa9\ub85d."""
    return {
        "core": sorted(CORE_EVENTS),
        "watch": sorted(WATCH_EVENTS),
        "total": len(CANONICAL_EVENTS),
    }
