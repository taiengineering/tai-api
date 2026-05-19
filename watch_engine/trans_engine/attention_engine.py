"""Attention Engine — 통합 엔트리포인트.

attn score + focus queue + ranking + explainer 통합.
"""
from __future__ import annotations
from typing import Any

from .attention_score import compute_attention_score
from .attention_ranker import rank_by_attention, get_critical_situations
from .focus_queue import build_focus_queue
from .attention_explainer import build_attention_summary


def enrich_snapshot_attention(snapshot: dict[str, Any]) -> dict[str, Any]:
    """snapshot에 attention 정보 추가."""
    att = compute_attention_score(snapshot)
    snapshot["attention_score"] = att["attention_score"]
    snapshot["attention_level"] = att["attention_level"]
    snapshot["requires_attention"] = att["requires_immediate_attention"]
    snapshot["attention_summary"] = build_attention_summary(att)
    return snapshot


def build_attention_overview(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """전체 attention 요약."""
    if not snapshots:
        return {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0,
                "immediate_count": 0, "top_situation": None}
    ranked = rank_by_attention(snapshots)
    levels = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    immediate = 0
    for r in ranked:
        lv = r.get("attention_level", "low")
        levels[lv] = levels.get(lv, 0) + 1
        if r.get("requires_immediate_attention"): immediate += 1
    top = ranked[0] if ranked else None
    return {
        "total": len(ranked),
        **levels,
        "immediate_count": immediate,
        "top_situation": {
            "title": top.get("title", ""),
            "attention_score": top.get("attention_score", 0),
            "attention_level": top.get("attention_level", "low"),
            "situation_id": top.get("situation_id", ""),
        } if top else None,
    }
