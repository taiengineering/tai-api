"""Priority Ranker — 운영 우선순위 결정.

판단 요소 (100%):
  customer_impact  40%
  repetition       20%
  escalation       15%
  degradation      15%
  spread           10%

점수 → 등급:
  0.75+ → P1 (즉시 확인 필요)
  0.50+ → P2 (주의 필요)
  0.25+ → P3 (관찰 필요)
  else  → P4 (정보 수준)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PriorityResult:
    score: float
    level: str      # P1~P4
    label: str      # 운영 표현
    factors: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "level": self.level,
            "label": self.label,
            "factors": {k: round(v, 3) for k, v in self.factors.items()},
        }


_CUSTOMER_FACING_PREFIXES = {
    "payment", "subscription", "document",
    "diagnosis", "campaign",
}


def rank_priority(events: list[dict[str, Any]]) -> PriorityResult:
    """이벤트 집합 → 우선순위."""
    if not events:
        return PriorityResult(0.0, "P4", "정보 수준", {})

    types = [e.get("event_type", "") for e in events]
    severities = [e.get("severity", "INFO").upper() for e in events]
    flow_keys = [e.get("flow_key", "") for e in events]
    tenant_ids = {e.get("tenant_id") for e in events if e.get("tenant_id")}

    # customer_impact (0~1)
    customer_facing = any(
        fk.split("_")[0] in _CUSTOMER_FACING_PREFIXES
        for fk in flow_keys if fk
    )
    has_critical = "CRITICAL" in severities or "FATAL" in severities
    customer_impact = 0.0
    if has_critical and customer_facing:
        customer_impact = 1.0
    elif has_critical:
        customer_impact = 0.7
    elif customer_facing:
        customer_impact = 0.5

    # repetition (0~1)
    has_repeated = "repeated_failure" in types
    repetition = 1.0 if has_repeated else (0.5 if len(events) >= 5 else 0.0)

    # escalation (0~1)
    has_escalation = "escalation" in types
    escalation = 1.0 if has_escalation else 0.0

    # degradation (0~1)
    has_degradation = any(t in types for t in ("degradation", "runtime.degraded"))
    degradation = 1.0 if has_degradation else 0.0

    # spread (0~1)
    spread = min(len(tenant_ids) / 5.0, 1.0) if tenant_ids else 0.0

    factors = {
        "customer_impact": customer_impact,
        "repetition": repetition,
        "escalation": escalation,
        "degradation": degradation,
        "spread": spread,
    }

    score = (
        customer_impact * 0.40
        + repetition * 0.20
        + escalation * 0.15
        + degradation * 0.15
        + spread * 0.10
    )

    if score >= 0.75:
        level, label = "P1", "즉시 확인 필요"
    elif score >= 0.50:
        level, label = "P2", "주의 필요"
    elif score >= 0.25:
        level, label = "P3", "관찰 필요"
    else:
        level, label = "P4", "정보 수준"

    return PriorityResult(score, level, label, factors)
