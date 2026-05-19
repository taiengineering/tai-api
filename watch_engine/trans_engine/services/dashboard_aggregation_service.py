"""Dashboard Aggregation Service — 대시보드 전용."""
from __future__ import annotations
from collections import Counter
from typing import Any
from watch_engine.trans_engine.utils.snapshot_utils import get_latest_per_situation
from watch_engine.trans_engine.utils.aggregation_utils import build_overview

async def get_overview(env: str | None = None) -> dict[str, Any]:
    latest = await get_latest_per_situation(env)
    return build_overview(latest)

async def get_worsening(env: str | None = None, limit: int = 20) -> list[dict]:
    latest = await get_latest_per_situation(env)
    ws = [r for r in latest if r.get("delta_type") == "worsening" or r.get("status") == "escalating"]
    ws.sort(key=lambda r: r.get("generated_at", ""), reverse=True)
    return ws[:limit]

async def get_recurring(env: str | None = None, limit: int = 20) -> list[dict]:
    latest = await get_latest_per_situation(env)
    return [r for r in latest if r.get("delta_type") == "recurring"][:limit]

async def get_tenant_risk(env: str | None = None) -> list[dict]:
    latest = await get_latest_per_situation(env)
    tenant_map: dict[str, dict] = {}
    p_order = {"P1": 4, "P2": 3, "P3": 2, "P4": 1}
    s_order = {"escalating": 5, "active": 4, "emerging": 3, "stabilizing": 2, "resolved": 1}
    for r in latest:
        tid = r.get("tenant_id") or "system"
        if tid not in tenant_map:
            tenant_map[tid] = {"tenant_id": tid, "situations": 0, "worst_priority": "P4", "worst_status": "emerging", "risk_score": 0}
        t = tenant_map[tid]; t["situations"] += 1
        cp = p_order.get(r.get("priority", "P4"), 1)
        cs = s_order.get(r.get("status", "emerging"), 1)
        if cp > p_order.get(t["worst_priority"], 1): t["worst_priority"] = r.get("priority", "P4")
        if cs > s_order.get(t["worst_status"], 1): t["worst_status"] = r.get("status", "emerging")
        t["risk_score"] += cp
    return sorted(tenant_map.values(), key=lambda x: x["risk_score"], reverse=True)

async def get_domain_stability(env: str | None = None) -> list[dict]:
    latest = await get_latest_per_situation(env)
    stability_labels = {"accelerating": "unstable", "degrading": "degrading", "stable": "stable", "improving": "healthy"}
    t_order = {"accelerating": 4, "degrading": 3, "stable": 2, "improving": 1}
    domain_map: dict[str, dict] = {}
    for r in latest:
        parts = r.get("situation_id", "").split(":")
        domain = parts[1] if len(parts) >= 2 else "general"
        if domain not in domain_map:
            domain_map[domain] = {"domain": domain, "situations": 0, "worst_trend": "stable", "stability": "stable"}
        d = domain_map[domain]; d["situations"] += 1
        ct = t_order.get(r.get("trend", "stable"), 2)
        if ct > t_order.get(d["worst_trend"], 2):
            d["worst_trend"] = r.get("trend", "stable")
            d["stability"] = stability_labels.get(d["worst_trend"], "stable")
    return sorted(domain_map.values(), key=lambda x: t_order.get(x["worst_trend"], 0), reverse=True)

async def get_lifecycle_map(env: str | None = None) -> tuple[list[dict], int]:
    latest = await get_latest_per_situation(env)
    statuses = Counter(r.get("status", "emerging") for r in latest)
    total = len(latest)
    lifecycle = []
    for s in ["escalating", "active", "emerging", "stabilizing", "resolved"]:
        cnt = statuses.get(s, 0)
        lifecycle.append({"status": s, "count": cnt, "percentage": round(cnt / total * 100, 1) if total else 0})
    return lifecycle, total
