"""Capability Registry — Runtime별 허용/금지 권한 정의.

각 Runtime이 수행할 수 있는 action을 명시적으로 등록.
등록되지 않은 action은 기본적으로 금지.
"""

# ═══ Runtime 별 허용 Capability ═══

CAPABILITY_REGISTRY: dict[str, set[str]] = {
    # Control Runtime — Operational Truth Engine (\uc720\uc77c\ud55c Truth Owner)
    "control": {
        "create_incident",
        "set_severity",
        "escalate_incident",
        "resolve_incident",
        "close_incident",
        "set_ack",
        "complete_ack",
        "set_recovery",
        "close_recovery",
        "set_operational_status",
        "set_degradation",
        "set_suppression",
        "detect_anomaly",
        "detect_pattern",
        "compute_stability",
        "compute_tenant_impact",
        "set_workflow_blockage",
        "create_alert",
        "evaluate_integrity",
        "detect_repeated",
        "evaluate_sla",
    },

    # Notification Runtime — Communication Projection
    "notification": {
        "create_projection",
        "map_audience",
        "apply_digest",
        "apply_quiet_hour",
        "apply_fatigue_reduction",
        "apply_cooldown",
        "route_notification",
        "log_delivery",
    },

    # Delivery Runtime — Execution Engine
    "delivery": {
        "enqueue",
        "retry_delivery",
        "execute_transport",
        "timeout_delivery",
        "log_delivery_audit",
        "select_provider",
    },

    # Workflow Runtime — Business Process
    "workflow": {
        "execute_workflow",
        "execute_step",
        "emit_event",
        "transition_state",
        "activate_document",
    },

    # UI Runtime — Projection Surface
    "ui": {
        "request_ack",
        "request_resolve",
        "request_ignore",
        "request_escalate",
        "request_retry",
        "render_projection",
        "filter_sort",
    },

    # Semantic Adapter — Translation Layer
    "adapter": {
        "translate_state",
        "translate_record",
        "invalidate_cache",
    },
}

# ═══ Runtime 별 명시적 금지 Capability ═══

FORBIDDEN_REGISTRY: dict[str, set[str]] = {
    "notification": {
        "create_incident",
        "set_severity",
        "escalate_incident",
        "resolve_incident",
        "close_incident",
        "set_ack",
        "complete_ack",
        "set_recovery",
        "close_recovery",
        "set_operational_status",
        "set_degradation",
        "set_suppression",
        "detect_anomaly",
        "set_workflow_blockage",
    },
    "delivery": {
        "create_incident",
        "set_severity",
        "escalate_incident",
        "resolve_incident",
        "set_ack",
        "set_suppression",
        "map_audience",
    },
    "workflow": {
        "create_incident",
        "set_severity",
        "escalate_incident",
        "resolve_incident",
        "set_ack",
        "complete_ack",
        "set_recovery",
        "set_operational_status",
        "set_degradation",
    },
    "ui": {
        "create_incident",
        "set_severity",
        "escalate_incident",
        "resolve_incident",
        "close_incident",
        "set_ack",
        "complete_ack",
        "set_recovery",
        "set_operational_status",
        "set_suppression",
    },
    "adapter": {
        "create_incident",
        "set_severity",
        "escalate_incident",
        "resolve_incident",
        "set_ack",
        "set_operational_status",
    },
}


def get_capabilities(runtime: str) -> set[str]:
    """Runtime의 허용된 capability 목록."""
    return CAPABILITY_REGISTRY.get(runtime, set())


def is_allowed(runtime: str, action: str) -> bool:
    """Runtime이 action을 수행할 수 있는지."""
    return action in CAPABILITY_REGISTRY.get(runtime, set())


def is_forbidden(runtime: str, action: str) -> bool:
    """Runtime에서 action이 명시적으로 금지되었는지."""
    return action in FORBIDDEN_REGISTRY.get(runtime, set())
