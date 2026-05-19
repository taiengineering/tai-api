"""Focus Queue — 운영자 집중 대기열 생성."""
from __future__ import annotations
from typing import Any
from .attention_score import compute_attention_score

def build_focus_queue(
    snapshots: list[dict[str, Any]],
    limit: int = 10,
) -> list[dict[str, Any]]:
    scored = []
    for s in snapshots:
        if s.get("status") in ("resolved",): continue
        att = compute_attention_score(s)
        scored.append({"snapshot": s, "attention": att})
    scored.sort(key=lambda x: x["attention"]["attention_score"], reverse=True)
    queue = []
    for rank, item in enumerate(scored[:limit], 1):
        s = item["snapshot"]
        a = item["attention"]
        queue.append({
            "rank": rank,
            "situation_id": s.get("situation_id", ""),
            "title": s.get("title", ""),
            "attention_level": a["attention_level"],
            "attention_score": a["attention_score"],
            "requires_immediate": a["requires_immediate_attention"],
            "why_now": " ".join(a["attention_reasons"]),
            "recommended_focus": s.get("recommended_focus", []),
            "estimated_risk_direction": s.get("risk_direction", "stable"),
            "next_check_recommendation": a["recommended_focus_time"],
            "priority": s.get("priority", "P4"),
            "trend": s.get("trend", "stable"),
            "delta_type": s.get("delta_type", ""),
            "environment": s.get("environment", "production"),
        })
    return queue
