"""Effectiveness Analyzer — 대응 효과 분석."""
from __future__ import annotations
from typing import Any
from .response_feedback import get_recent_feedback

async def analyze_effective_actions(environment: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    feedbacks = await get_recent_feedback(limit=limit, environment=environment)
    action_stats: dict[str, dict] = {}
    for f in feedbacks:
        act = f.get("operator_action", "")
        if not act: continue
        if act not in action_stats:
            action_stats[act] = {"action": act, "total": 0, "improved": 0, "worsened": 0, "eff_sum": 0.0}
        s = action_stats[act]
        s["total"] += 1
        if f.get("outcome") == "improved": s["improved"] += 1
        if f.get("outcome") == "worsened": s["worsened"] += 1
        s["eff_sum"] += f.get("effectiveness", 0.5)
    results = []
    for s in action_stats.values():
        s["avg_effectiveness"] = round(s["eff_sum"] / s["total"], 3) if s["total"] else 0
        s["success_rate"] = round(s["improved"] / s["total"], 3) if s["total"] else 0
        del s["eff_sum"]
        results.append(s)
    results.sort(key=lambda x: x["avg_effectiveness"], reverse=True)
    return results

async def analyze_recurring_patterns(environment: str | None = None) -> list[dict[str, Any]]:
    feedbacks = await get_recent_feedback(limit=200, environment=environment)
    sit_outcomes: dict[str, list[str]] = {}
    for f in feedbacks:
        sid = f.get("situation_id", "")
        if sid not in sit_outcomes: sit_outcomes[sid] = []
        sit_outcomes[sid].append(f.get("outcome", ""))
    patterns = []
    for sid, outcomes in sit_outcomes.items():
        rec_count = outcomes.count("recurring")
        if rec_count > 0:
            patterns.append({
                "situation_id": sid, "recurrence_count": rec_count,
                "total_responses": len(outcomes),
                "recurrence_rate": round(rec_count / len(outcomes), 3),
            })
    patterns.sort(key=lambda x: x["recurrence_rate"], reverse=True)
    return patterns
