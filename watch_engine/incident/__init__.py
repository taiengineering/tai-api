"""Incident Priority Engine — 운영 우선순위 판단.

Rule-based priority: P1~P4.
무엇을 먼저 봐야 하는가.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("watch_engine.incident.priority")


def calculate_priority(
    event_type: str,
    severity: str,
    impact_level: str = "MEDIUM",
    repeat_count: int = 0,
    affected_traces: int = 0,
    browser_affected: bool = False,
    sla_affected: bool = False,
) -> str:
    """Rule-based incident priority.

    Returns: P1 | P2 | P3 | P4
    """
    score = 0

    # Severity
    sev_score = {"CRITICAL": 40, "HIGH": 25, "WARNING": 10, "INFO": 0}
    score += sev_score.get(severity, 5)

    # Impact level
    imp_score = {"CRITICAL": 30, "HIGH": 20, "MEDIUM": 10, "LOW": 0}
    score += imp_score.get(impact_level, 5)

    # Repeat count
    if repeat_count >= 5:
        score += 20
    elif repeat_count >= 3:
        score += 10

    # Affected traces
    if affected_traces >= 10:
        score += 15
    elif affected_traces >= 3:
        score += 5

    # Browser = user-facing
    if browser_affected:
        score += 10

    # SLA = business commitment
    if sla_affected:
        score += 15

    # Event type boosts
    critical_types = {"sla_critical", "stuck_detected", "workflow_instability", "repeated_failure"}
    if event_type in critical_types:
        score += 10

    # Map to priority
    if score >= 70:
        return "P1"
    elif score >= 45:
        return "P2"
    elif score >= 25:
        return "P3"
    else:
        return "P4"


def compute_risk_score(
    issue_count_24h: int = 0,
    critical_count: int = 0,
    browser_failure_count: int = 0,
    sla_violation_count: int = 0,
    repeat_failure: bool = False,
) -> str:
    """Workflow risk score.

    Returns: LOW | MEDIUM | HIGH | CRITICAL
    """
    score = 0
    score += min(issue_count_24h * 3, 30)
    score += critical_count * 15
    score += browser_failure_count * 8
    score += sla_violation_count * 12
    if repeat_failure:
        score += 20

    if score >= 60:
        return "CRITICAL"
    elif score >= 35:
        return "HIGH"
    elif score >= 15:
        return "MEDIUM"
    else:
        return "LOW"


def get_recommended_action(
    priority: str,
    event_type: str,
    browser_affected: bool = False,
    sla_affected: bool = False,
    repeat_count: int = 0,
) -> str:
    """운영 추천 액션."""
    if priority == "P1":
        if event_type in ("sla_critical", "workflow_instability"):
            return "\uc989\uc2dc \ud655\uc778 \ud544\uc694 \u2014 \uc5c5\ubb34 SLA \uc704\ubc18"
        if browser_affected:
            return "\uc989\uc2dc \ud655\uc778 \ud544\uc694 \u2014 \ube0c\ub77c\uc6b0\uc800 UI \uc7a5\uc560"
        return "\uc989\uc2dc \ud655\uc778 \ud544\uc694"
    if priority == "P2":
        if repeat_count >= 3:
            return "\ubc18\ubcf5 \uc7a5\uc560 \ud655\uc778 \ud544\uc694"
        if sla_affected:
            return "SLA threshold \uc870\uc815 \uac80\ud1a0"
        return "\ub2e4\uc74c \uc6b4\uc601 \uc810\uac80 \uc2dc \ud655\uc778"
    if priority == "P3":
        return "\ubaa8\ub2c8\ud130\ub9c1 \uc720\uc9c0"
    return "\ubb34\uc2dc \uac00\ub2a5"
