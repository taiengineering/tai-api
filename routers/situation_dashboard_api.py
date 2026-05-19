"""Situation Dashboard API — Operational Situation 전장 시각화.

Routes:
    GET /situation/dashboard/overview          — 전체 상황 요약
    GET /situation/dashboard/worsening         — 악화 중
    GET /situation/dashboard/recurring         — 재발 상황
    GET /situation/dashboard/tenant-risk       — tenant 위험도
    GET /situation/dashboard/domain-stability  — domain 안정성
    GET /situation/dashboard/lifecycle-map     — lifecycle 분포
"""

from __future__ import annotations

import logging
from collections import Counter
from fastapi import APIRouter, Query
from typing import Any

from db.supabase_client import get_supabase

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/situation/dashboard", tags=["Situation Dashboard"])

TABLE = "operational_situation_snapshot"


async def _recent(env: str | None, limit: int = 200) -> list[dict]:
    try:
        sb = get_supabase()
        q = sb.table(TABLE).select("*").order("generated_at", desc=True).limit(limit)
        if env:
            q = q.eq("environment", env)
        return (q.execute()).data or []
    except Exception as e:
        logger.error(f"dashboard _recent: {e}")
        return []


async def _latest_per_situation(env: str | None) -> list[dict]:
    """situation_id별 최신 1건만."""
    rows = await _recent(env, 500)
    seen: dict[str, dict] = {}
    for r in rows:
        sid = r.get("situation_id", "")
        if sid not in seen:
            seen[sid] = r
    return list(seen.values())


@router.get("/overview")
async def api_overview(environment: str | None = Query(None)):
    """전체 운영 상황 요약."""
    latest = await _latest_per_situation(environment)
    if not latest:
        return {"status": "success", "data": _empty_overview()}

    statuses = Counter(r.get("status", "emerging") for r in latest)
    deltas = Counter(r.get("delta_type", "new") for r in latest)
    priorities = Counter(r.get("priority", "P4") for r in latest)

    # top risk domain / tenant
    domain_risk: dict[str, int] = {}
    tenant_risk: dict[str, int] = {}
    p_score = {"P1": 4, "P2": 3, "P3": 2, "P4": 1}
    for r in latest:
        sid = r.get("situation_id", "")
        parts = sid.split(":")
        ps = p_score.get(r.get("priority", "P4"), 1)
        if len(parts) >= 2:
            domain_risk[parts[1]] = domain_risk.get(parts[1], 0) + ps
        if len(parts) >= 1:
            tenant_risk[parts[0]] = tenant_risk.get(parts[0], 0) + ps

    top_domain = max(domain_risk, key=domain_risk.get) if domain_risk else None
    top_tenant = max(tenant_risk, key=tenant_risk.get) if tenant_risk else None

    active_count = statuses.get("active", 0) + statuses.get("escalating", 0) + statuses.get("emerging", 0)

    return {"status": "success", "data": {
        "total_situations": len(latest),
        "active_situations": active_count,
        "worsening": deltas.get("worsening", 0),
        "recurring": deltas.get("recurring", 0),
        "stabilizing": deltas.get("stabilizing", 0) + statuses.get("stabilizing", 0),
        "resolved": statuses.get("resolved", 0),
        "critical": priorities.get("P1", 0),
        "lifecycle": dict(statuses),
        "priorities": dict(priorities),
        "delta_types": dict(deltas),
        "top_risk_domain": top_domain,
        "top_risk_tenant": top_tenant,
    }}


@router.get("/worsening")
async def api_worsening(environment: str | None = Query(None), limit: int = Query(20, ge=1, le=100)):
    """악화 중 상황."""
    latest = await _latest_per_situation(environment)
    worsening = [r for r in latest if r.get("delta_type") == "worsening" or r.get("status") == "escalating"]
    worsening.sort(key=lambda r: r.get("generated_at", ""), reverse=True)
    return {"status": "success", "data": worsening[:limit], "count": len(worsening)}


@router.get("/recurring")
async def api_recurring(environment: str | None = Query(None), limit: int = Query(20, ge=1, le=100)):
    """재발 상황."""
    latest = await _latest_per_situation(environment)
    recurring = [r for r in latest if r.get("delta_type") == "recurring"]
    recurring.sort(key=lambda r: r.get("generated_at", ""), reverse=True)
    return {"status": "success", "data": recurring[:limit], "count": len(recurring)}


@router.get("/tenant-risk")
async def api_tenant_risk(environment: str | None = Query(None)):
    """Tenant별 위험도."""
    latest = await _latest_per_situation(environment)
    tenant_map: dict[str, dict] = {}
    for r in latest:
        tid = r.get("tenant_id") or "system"
        if tid not in tenant_map:
            tenant_map[tid] = {"tenant_id": tid, "situations": 0, "worst_priority": "P4", "worst_status": "emerging", "risk_score": 0}
        t = tenant_map[tid]
        t["situations"] += 1
        p_order = {"P1": 4, "P2": 3, "P3": 2, "P4": 1}
        s_order = {"escalating": 5, "active": 4, "emerging": 3, "stabilizing": 2, "resolved": 1}
        cp = p_order.get(r.get("priority", "P4"), 1)
        cs = s_order.get(r.get("status", "emerging"), 1)
        if cp > p_order.get(t["worst_priority"], 1):
            t["worst_priority"] = r.get("priority", "P4")
        if cs > s_order.get(t["worst_status"], 1):
            t["worst_status"] = r.get("status", "emerging")
        t["risk_score"] += cp

    tenants = sorted(tenant_map.values(), key=lambda x: x["risk_score"], reverse=True)
    return {"status": "success", "data": tenants}


@router.get("/domain-stability")
async def api_domain_stability(environment: str | None = Query(None)):
    """Domain별 안정성."""
    latest = await _latest_per_situation(environment)
    domain_map: dict[str, dict] = {}
    stability_labels = {"accelerating": "unstable", "degrading": "degrading", "stable": "stable", "improving": "healthy"}
    t_order = {"accelerating": 4, "degrading": 3, "stable": 2, "improving": 1}

    for r in latest:
        sid = r.get("situation_id", "")
        parts = sid.split(":")
        domain = parts[1] if len(parts) >= 2 else "general"
        if domain not in domain_map:
            domain_map[domain] = {"domain": domain, "situations": 0, "worst_trend": "stable", "stability": "stable"}
        d = domain_map[domain]
        d["situations"] += 1
        ct = t_order.get(r.get("trend", "stable"), 2)
        if ct > t_order.get(d["worst_trend"], 2):
            d["worst_trend"] = r.get("trend", "stable")
            d["stability"] = stability_labels.get(d["worst_trend"], "stable")

    domains = sorted(domain_map.values(), key=lambda x: t_order.get(x["worst_trend"], 0), reverse=True)
    return {"status": "success", "data": domains}


@router.get("/lifecycle-map")
async def api_lifecycle_map(environment: str | None = Query(None)):
    """Lifecycle 상태 분포."""
    latest = await _latest_per_situation(environment)
    statuses = Counter(r.get("status", "emerging") for r in latest)
    total = len(latest)
    lifecycle = []
    for s in ["escalating", "active", "emerging", "stabilizing", "resolved"]:
        cnt = statuses.get(s, 0)
        lifecycle.append({"status": s, "count": cnt, "percentage": round(cnt / total * 100, 1) if total else 0})
    return {"status": "success", "data": lifecycle, "total": total}


def _empty_overview() -> dict:
    return {
        "total_situations": 0, "active_situations": 0, "worsening": 0, "recurring": 0,
        "stabilizing": 0, "resolved": 0, "critical": 0, "lifecycle": {}, "priorities": {},
        "delta_types": {}, "top_risk_domain": None, "top_risk_tenant": None,
    }
