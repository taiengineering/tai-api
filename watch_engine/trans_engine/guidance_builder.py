"""Guidance Builder — 통합 대응 가이드 생성."""
from __future__ import annotations
from typing import Any
from .response_playbook import match_playbook
from .response_priority import compute_guidance_level
from .response_explainer import build_guidance_summary, build_why_recommended

def build_response_guidance(snapshot: dict[str, Any]) -> dict[str, Any]:
    playbook = match_playbook(snapshot)
    level = compute_guidance_level(snapshot)
    summary = build_guidance_summary(snapshot, playbook, level)
    why = build_why_recommended(snapshot)
    return {
        "guidance_level": level,
        "recommended_actions": playbook.get("actions", []),
        "recommended_checks": playbook.get("checks", []),
        "recommended_order": playbook.get("order", []),
        "estimated_effectiveness": _estimate_effectiveness(snapshot),
        "why_recommended": why,
        "operator_notes": [summary],
        "requires_human_decision": True,
        "playbook_title": playbook.get("title", ""),
        "guidance_summary": summary,
    }

def _estimate_effectiveness(snapshot: dict[str, Any]) -> float:
    """TODO: recovery_feedback 연동. 현재는 휴리스틱."""
    conf = snapshot.get("confidence", 0.5) or 0.5
    dt = snapshot.get("delta_type", "")
    if dt == "stabilizing": return round(min(conf + 0.2, 1.0), 2)
    if dt == "recurring": return round(max(conf - 0.1, 0.3), 2)
    return round(conf, 2)
