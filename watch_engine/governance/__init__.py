"""Tenant Impact Engine v1.1 — Production isolation.

v1.1: Mock environment/tenant 제외 (TASK 30).
rule-based: HEALTHY / WATCH / RISK / CRITICAL.
Escalation: L1~L4.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger("watch_engine.governance.tenant_impact")

BROWSER_TYPES = {"browser_render_failed", "selector_not_found", "button_not_clickable", "page_timeout", "ui_value_mismatch"}
SLA_TYPES = {"sla_warning", "sla_critical", "workflow_degraded"}
REPEAT_TYPES = {"repeated_failure", "workflow_instability"}


def compute_tenant_impact(
    sb, hours: int = 24, now: Optional[datetime] = None
) -> list[dict]:
    """Compute per-tenant operational impact."""
    if now is None:
        now = datetime.now(timezone.utc)
    since = (now - timedelta(hours=hours)).isoformat()

    try:
        # TASK 30: Mock environment 제외
        events = sb.table("engine_integrity_event") \
            .select("tenant_id,flow_key,event_type,severity,resolved,ignored") \
            .not_.is_("trace_id", "null") \
            .neq("environment", "mock") \
            .gte("created_at", since).execute()

        tenants = {}
        for e in (events.data or []):
            tid = e.get("tenant_id", "unknown")
            # TASK 30: Mock tenant 제외
            if tid.startswith("mock_"):
                continue
            if tid not in tenants:
                tenants[tid] = {"total": 0, "critical": 0, "browser": 0, "sla": 0,
                                "repeat": 0, "active": 0, "flows": set()}
            tenants[tid]["total"] += 1
            if not e.get("resolved") and not e.get("ignored"):
                tenants[tid]["active"] += 1
            if e.get("severity") == "CRITICAL":
                tenants[tid]["critical"] += 1
            if e.get("event_type") in BROWSER_TYPES:
                tenants[tid]["browser"] += 1
            if e.get("event_type") in SLA_TYPES:
                tenants[tid]["sla"] += 1
            if e.get("event_type") in REPEAT_TYPES:
                tenants[tid]["repeat"] += 1
            if e.get("flow_key"):
                tenants[tid]["flows"].add(e["flow_key"])

        reg_resp = sb.table("tenant_operational_registry").select("tenant_id,tenant_name") \
            .not_.like("tenant_id", "mock_%").execute()
        names = {r["tenant_id"]: r.get("tenant_name", r["tenant_id"]) for r in (reg_resp.data or [])}

        results = []
        for tid, d in tenants.items():
            stability, escalation = _calc_status(d)
            flow_count = len(d["flows"])

            try:
                sb.table("tenant_operational_registry").upsert({
                    "tenant_id": tid,
                    "tenant_name": names.get(tid, tid),
                    "active_issue_count": d["active"],
                    "critical_issue_count": d["critical"],
                    "affected_workflow_count": flow_count,
                    "browser_failure_count": d["browser"],
                    "sla_violation_count": d["sla"],
                    "stability_status": stability,
                    "escalation_level": escalation,
                    "last_incident_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }, on_conflict="tenant_id").execute()
            except Exception:
                pass

            results.append({
                "tenant_id": tid,
                "tenant_name": names.get(tid, tid),
                "stability_status": stability,
                "escalation_level": escalation,
                "active_issue_count": d["active"],
                "critical_issue_count": d["critical"],
                "affected_workflow_count": flow_count,
                "browser_failure_count": d["browser"],
                "sla_violation_count": d["sla"],
                "repeat_failure_count": d["repeat"],
                "affected_flows": list(d["flows"]),
            })

        order = {"CRITICAL": 0, "RISK": 1, "WATCH": 2, "HEALTHY": 3}
        results.sort(key=lambda x: order.get(x["stability_status"], 9))
        return results

    except Exception as e:
        logger.error("compute_tenant_impact failed: %s", e)
        return []


def _calc_status(d: dict) -> tuple[str, str]:
    score = 0
    score += d["critical"] * 15
    score += d["browser"] * 8
    score += d["sla"] * 10
    score += d["repeat"] * 12
    score += len(d["flows"]) * 3

    if score >= 50:
        stability = "CRITICAL"
    elif score >= 30:
        stability = "RISK"
    elif score >= 10:
        stability = "WATCH"
    else:
        stability = "HEALTHY"

    if d["critical"] > 0 and len(d["flows"]) >= 2:
        escalation = "L4"
    elif d["browser"] > 0 and d["sla"] > 0:
        escalation = "L3"
    elif d["repeat"] > 0 or d["sla"] > 1:
        escalation = "L2"
    else:
        escalation = "L1"

    return stability, escalation
