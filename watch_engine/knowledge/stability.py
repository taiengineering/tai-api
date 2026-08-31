"""Workflow Stability Tracker v1.1 — Production isolation.

v1.1: Mock environment 제외 (TASK 30).
rule-based: STABLE / WATCH / UNSTABLE / CRITICAL.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from services.time import now_kst

logger = logging.getLogger("watch_engine.knowledge.stability")


def compute_stability(sb, hours: int = 24, now: Optional[datetime] = None) -> list[dict]:
    if now is None:
        now = now_kst()
    since = (now - timedelta(hours=hours)).isoformat()

    try:
        # TASK 30: Mock environment 제외
        events = sb.table("engine_integrity_event") \
            .select("flow_key,event_type,severity,resolved") \
            .not_.is_("trace_id", "null") \
            .neq("environment", "mock") \
            .gte("created_at", since).execute()

        browser_types = {"browser_render_failed", "selector_not_found", "button_not_clickable", "page_timeout", "ui_value_mismatch"}
        sla_types = {"sla_warning", "sla_critical", "workflow_degraded"}
        repeat_types = {"repeated_failure", "workflow_instability"}

        flows = {}
        for e in (events.data or []):
            fk = e.get("flow_key", "unknown")
            if fk not in flows:
                flows[fk] = {"total": 0, "critical": 0, "browser": 0, "sla": 0,
                             "repeat": 0, "resolved": 0, "unresolved": 0}
            flows[fk]["total"] += 1
            if e.get("severity") == "CRITICAL":
                flows[fk]["critical"] += 1
            if e.get("event_type") in browser_types:
                flows[fk]["browser"] += 1
            if e.get("event_type") in sla_types:
                flows[fk]["sla"] += 1
            if e.get("event_type") in repeat_types:
                flows[fk]["repeat"] += 1
            if e.get("resolved"):
                flows[fk]["resolved"] += 1
            else:
                flows[fk]["unresolved"] += 1

        results = []
        for fk, d in flows.items():
            score = 0
            score += min(d["total"] * 2, 20)
            score += d["critical"] * 10
            score += d["browser"] * 5
            score += d["sla"] * 8
            score += d["repeat"] * 15
            score -= d["resolved"] * 3
            score = max(score, 0)

            if score >= 50:
                stability = "CRITICAL"
            elif score >= 30:
                stability = "UNSTABLE"
            elif score >= 10:
                stability = "WATCH"
            else:
                stability = "STABLE"

            results.append({
                "flow_key": fk,
                "stability": stability,
                "score": score,
                "details": d,
            })

        order = {"CRITICAL": 0, "UNSTABLE": 1, "WATCH": 2, "STABLE": 3}
        results.sort(key=lambda x: order.get(x["stability"], 9))
        return results

    except Exception as e:
        logger.error("compute_stability failed: %s", e)
        return []


def get_recovery_effectiveness(sb, limit: int = 10) -> list[dict]:
    try:
        actions = sb.table("incident_action_log") \
            .select("action_type,outcome_status") \
            .not_.is_("outcome_status", "null").execute()

        agg = {}
        for a in (actions.data or []):
            at = a["action_type"]
            if at not in agg:
                agg[at] = {"total": 0, "resolved": 0, "unresolved": 0}
            agg[at]["total"] += 1
            if a["outcome_status"] == "resolved":
                agg[at]["resolved"] += 1
            elif a["outcome_status"] == "unresolved":
                agg[at]["unresolved"] += 1

        results = []
        for at, d in agg.items():
            rate = round(d["resolved"] / d["total"] * 100, 1) if d["total"] > 0 else 0
            results.append({"action_type": at, "success_rate": rate, **d})

        results.sort(key=lambda x: x["success_rate"], reverse=True)
        return results[:limit]

    except Exception as e:
        logger.error("get_recovery_effectiveness failed: %s", e)
        return []
