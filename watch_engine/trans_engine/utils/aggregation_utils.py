"""Aggregation Utils — 공통 집계."""
from __future__ import annotations
from collections import Counter
from typing import Any

_P_SCORE = {"P1": 4, "P2": 3, "P3": 2, "P4": 1}

def count_by_field(rows: list[dict], field: str) -> dict[str, int]:
    return dict(Counter(r.get(field, "unknown") for r in rows))

def compute_top_risk(rows: list[dict], field: str, id_field: str) -> str | None:
    scores: dict[str, int] = {}
    for r in rows:
        key = r.get(id_field, "")
        ps = _P_SCORE.get(r.get("priority", "P4"), 1)
        scores[key] = scores.get(key, 0) + ps
    return max(scores, key=scores.get) if scores else None

def build_overview(latest: list[dict]) -> dict[str, Any]:
    if not latest:
        return {"total_situations": 0, "active_situations": 0, "worsening": 0, "recurring": 0,
                "stabilizing": 0, "resolved": 0, "critical": 0, "lifecycle": {}, "priorities": {},
                "delta_types": {}, "top_risk_domain": None, "top_risk_tenant": None}
    statuses = count_by_field(latest, "status")
    deltas = count_by_field(latest, "delta_type")
    priorities = count_by_field(latest, "priority")
    active = statuses.get("active", 0) + statuses.get("escalating", 0) + statuses.get("emerging", 0)
    # domain from situation_id parts[1]
    domain_scores: dict[str, int] = {}
    tenant_scores: dict[str, int] = {}
    for r in latest:
        parts = r.get("situation_id", "").split(":")
        ps = _P_SCORE.get(r.get("priority", "P4"), 1)
        if len(parts) >= 2: domain_scores[parts[1]] = domain_scores.get(parts[1], 0) + ps
        if len(parts) >= 1: tenant_scores[parts[0]] = tenant_scores.get(parts[0], 0) + ps
    return {
        "total_situations": len(latest), "active_situations": active,
        "worsening": deltas.get("worsening", 0), "recurring": deltas.get("recurring", 0),
        "stabilizing": deltas.get("stabilizing", 0) + statuses.get("stabilizing", 0),
        "resolved": statuses.get("resolved", 0), "critical": priorities.get("P1", 0),
        "lifecycle": statuses, "priorities": priorities, "delta_types": deltas,
        "top_risk_domain": max(domain_scores, key=domain_scores.get) if domain_scores else None,
        "top_risk_tenant": max(tenant_scores, key=tenant_scores.get) if tenant_scores else None,
    }
