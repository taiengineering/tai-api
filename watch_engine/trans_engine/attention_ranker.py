"""Attention Ranker — 여러 스냅샷을 attention 기준 순위화."""
from __future__ import annotations
from typing import Any
from .attention_score import compute_attention_score

def rank_by_attention(
    snapshots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results = []
    for s in snapshots:
        att = compute_attention_score(s)
        results.append({**s, **att})
    results.sort(key=lambda x: x.get("attention_score", 0), reverse=True)
    return results

def get_critical_situations(
    snapshots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ranked = rank_by_attention(snapshots)
    return [r for r in ranked if r.get("requires_immediate_attention")]
