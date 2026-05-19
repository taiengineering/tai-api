"""Learning Registry — 운영 학습 패턴 축적."""
from __future__ import annotations
from typing import Any
from .effectiveness_analyzer import analyze_effective_actions, analyze_recurring_patterns

async def build_learning_registry(environment: str | None = None) -> list[dict[str, Any]]:
    effective = await analyze_effective_actions(environment=environment)
    recurring = await analyze_recurring_patterns(environment=environment)
    rec_map = {r["situation_id"]: r for r in recurring}
    registry = []
    for e in effective[:10]:
        registry.append({
            "pattern": e["action"],
            "avg_effectiveness": e["avg_effectiveness"],
            "success_rate": e["success_rate"],
            "total_uses": e["total"],
            "recommended": e["avg_effectiveness"] >= 0.6,
        })
    return registry
