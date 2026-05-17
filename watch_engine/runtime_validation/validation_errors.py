"""Validation Errors."""


class InvalidRuntimeEvent(Exception):
    """\uc798\ubabb\ub41c Runtime Event."""
    def __init__(self, reason: str, event_type: str = "", runtime: str = ""):
        self.reason = reason
        self.event_type = event_type
        self.runtime = runtime
        super().__init__(f"InvalidRuntimeEvent: {reason} (event={event_type}, runtime={runtime})")


class UnregisteredEventType(InvalidRuntimeEvent):
    """\ubbf8\ub4f1\ub85d Event Type."""
    def __init__(self, event_type: str):
        super().__init__(f"Unregistered event type: {event_type}", event_type)


class ForbiddenSeverityMutation(InvalidRuntimeEvent):
    """\uae08\uc9c0\ub41c Severity \uc0dd\uc131."""
    def __init__(self, runtime: str, severity: str):
        super().__init__(f"{runtime} cannot set severity {severity}", "", runtime)


class ForbiddenRuntimeMutation(InvalidRuntimeEvent):
    """\uae08\uc9c0\ub41c Runtime Event \uc0dd\uc131."""
    def __init__(self, runtime: str, event_type: str):
        super().__init__(f"{runtime} cannot emit {event_type}", event_type, runtime)


class InvalidTenantBoundary(InvalidRuntimeEvent):
    """Tenant Boundary \uc704\ubc18."""
    def __init__(self, reason: str):
        super().__init__(f"Tenant boundary: {reason}")


class InvalidTraceIntegrity(InvalidRuntimeEvent):
    """Trace \ubb34\uacb0\uc131 \uc704\ubc18."""
    def __init__(self, reason: str):
        super().__init__(f"Trace integrity: {reason}")
