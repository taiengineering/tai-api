"""Feedback Tracker — 대응 결과 추적 유틸."""
from __future__ import annotations
from typing import Any
from .response_feedback import get_feedback_for_situation

async def get_situation_feedback_summary(situation_id: str) -> dict[str, Any]:
    feedbacks = await get_feedback_for_situation(situation_id, limit=50)
    if not feedbacks:
        return {"total": 0, "outcomes": {}, "avg_effectiveness": 0, "top_actions": []}
    outcomes: dict[str, int] = {}
    eff_sum = 0.0
    action_eff: dict[str, list[float]] = {}
    for f in feedbacks:
        o = f.get("outcome", "unchanged")
        outcomes[o] = outcomes.get(o, 0) + 1
        e = f.get("effectiveness", 0.5)
        eff_sum += e
        act = f.get("operator_action", "")
        if act not in action_eff: action_eff[act] = []
        action_eff[act].append(e)
    avg = round(eff_sum / len(feedbacks), 3) if feedbacks else 0
    top = sorted(action_eff.items(), key=lambda x: sum(x[1])/len(x[1]), reverse=True)
    return {
        "total": len(feedbacks),
        "outcomes": outcomes,
        "avg_effectiveness": avg,
        "top_actions": [{"action": a, "avg_effectiveness": round(sum(e)/len(e), 3), "count": len(e)} for a, e in top[:5]],
    }
