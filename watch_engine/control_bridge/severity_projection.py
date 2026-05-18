"""Severity Projection — INFO event → Operational Severity."""

import logging
from watch_engine.control_bridge.bridge_rules import BRIDGE_RULES

logger = logging.getLogger("watch_engine.control_bridge.severity")


def project_severity(event_type: str) -> dict:
    """event_type\uc5d0 \ub300\ud55c Control Severity Projection.

    Returns: {severity, escalation_threshold, description} or None
    """
    rule = BRIDGE_RULES.get(event_type)
    if rule:
        return rule.copy()

    # \ubd80\ubd84 \ub9e4\uce6d (failed, timeout, blocked \ud3ec\ud568 event)
    if "failed" in event_type:
        return {"severity": "WARNING", "escalation_threshold": 5, "description": f"{event_type} projection"}
    if "timeout" in event_type:
        return {"severity": "WARNING", "escalation_threshold": 5, "description": f"{event_type} projection"}
    if "blocked" in event_type:
        return {"severity": "CRITICAL", "escalation_threshold": 3, "description": f"{event_type} projection"}

    return None  # INFO \uc720\uc9c0, projection \uc5c6\uc74c
