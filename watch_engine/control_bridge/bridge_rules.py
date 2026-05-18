"""Bridge Rules — Event → Severity Projection 규칙."""

BRIDGE_RULES = {
    # event_type → {severity, min_count_for_escalation, description}
    "workflow.failed": {
        "severity": "WARNING",
        "escalation_threshold": 5,
        "description": "workflow \uc2e4\ud328",
    },
    "workflow.timeout": {
        "severity": "WARNING",
        "escalation_threshold": 5,
        "description": "workflow \uc2dc\uac04\ucd08\uacfc",
    },
    "workflow.blocked": {
        "severity": "CRITICAL",
        "escalation_threshold": 3,
        "description": "workflow \ucc28\ub2e8",
    },
    "step.failed": {
        "severity": "WARNING",
        "escalation_threshold": 8,
        "description": "\ub2e8\uacc4 \uc2e4\ud328",
    },
    "payment.failed": {
        "severity": "WARNING",
        "escalation_threshold": 3,
        "description": "\uacb0\uc81c \uc2e4\ud328",
    },
    "subscription.failed": {
        "severity": "CRITICAL",
        "escalation_threshold": 2,
        "description": "\uad6c\ub3c5 \uc2e4\ud328",
    },
    "runtime.degraded": {
        "severity": "CRITICAL",
        "escalation_threshold": 1,
        "description": "Runtime \uc131\ub2a5\uc800\ud558",
    },
    "runtime.failed": {
        "severity": "CRITICAL",
        "escalation_threshold": 1,
        "description": "Runtime \uc2e4\ud328",
    },
    "document.failed": {
        "severity": "WARNING",
        "escalation_threshold": 5,
        "description": "\ubb38\uc11c\uc0dd\uc131 \uc2e4\ud328",
    },
}

# Escalation 규\uce59
ESCALATION_RULES = {
    "repeated_failure": {
        "min_count": 3,
        "window_minutes": 60,
        "severity": "WARNING",
        "event_type": "watch.integrity_detected",
        "description": "\ubc18\ubcf5 \uc2e4\ud328 \ud0d0\uc9c0",
    },
    "burst_failure": {
        "min_count": 10,
        "window_minutes": 15,
        "severity": "CRITICAL",
        "event_type": "watch.integrity_detected",
        "description": "\ubc84\uc2a4\ud2b8 \uc2e4\ud328 \ud0d0\uc9c0",
    },
    "multi_tenant_failure": {
        "min_tenants": 3,
        "window_minutes": 30,
        "severity": "CRITICAL",
        "event_type": "watch.integrity_detected",
        "description": "\ub2e4\uc218 \ud14c\ub10c\ud2b8 \ub3d9\uc2dc \uc2e4\ud328",
    },
}
