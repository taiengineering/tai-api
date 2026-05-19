"""Operational Memory — 과거 운영 경험 기억."""
from __future__ import annotations
from typing import Any
from .response_feedback import get_feedback_for_situation
from .feedback_tracker import get_situation_feedback_summary

async def build_operational_memory(situation_id: str) -> dict[str, Any]:
    summary = await get_situation_feedback_summary(situation_id)
    feedbacks = await get_feedback_for_situation(situation_id, limit=10)
    recurrence_count = summary.get("outcomes", {}).get("recurring", 0)
    total = summary.get("total", 0)
    rec_risk = "low"
    if total > 0:
        rate = recurrence_count / total
        if rate >= 0.5: rec_risk = "critical"
        elif rate >= 0.3: rec_risk = "high"
        elif rate >= 0.1: rec_risk = "medium"
    top_actions = summary.get("top_actions", [])
    effective_actions = [a["action"] for a in top_actions if a.get("avg_effectiveness", 0) >= 0.6]
    notes = []
    if recurrence_count > 0:
        notes.append(f"이 상황 유형은 최근 {recurrence_count}회 재발했습니다.")
    if effective_actions:
        notes.append(f"효과적이었던 대응: {', '.join(effective_actions[:3])}")
    if not notes:
        notes.append("아직 축적된 운영 경험이 없습니다.")
    return {
        "situation_id": situation_id,
        "total_responses": total,
        "recurrence_count": recurrence_count,
        "recurrence_risk": rec_risk,
        "avg_effectiveness": summary.get("avg_effectiveness", 0),
        "effective_actions": effective_actions,
        "outcomes": summary.get("outcomes", {}),
        "memory_notes": notes,
        "learned_effectiveness": summary.get("avg_effectiveness", 0),
    }

def compute_recurrence_risk(feedback_count: int, recurrence_count: int) -> str:
    if feedback_count == 0: return "low"
    rate = recurrence_count / feedback_count
    if rate >= 0.5: return "critical"
    if rate >= 0.3: return "high"
    if rate >= 0.1: return "medium"
    return "low"
