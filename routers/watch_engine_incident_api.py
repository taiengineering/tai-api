# routers/watch_engine_incident_api.py — Incident Intelligence API v1.1
"""
운영 우선순위 + 반복 실패 + Workflow Risk.
v1.1: Mock environment 제외 (TASK 30).
"""

import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watch-engine/incidents", tags=["인시던트"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/priority")
def get_incident_priority(hours: int = 24):
    """운영 우선순위 정렬 이슈 목록."""
    try:
        from watch_engine.incident import calculate_priority, get_recommended_action
        sb = _sb()
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        # TASK 30: Mock 제외
        issues = sb.table("engine_integrity_event") \
            .select("id,flow_key,event_type,severity,trace_id,description,detail,created_at") \
            .eq("resolved", False).eq("ignored", False) \
            .not_.is_("trace_id", "null") \
            .neq("environment", "mock") \
            .gte("created_at", since) \
            .order("created_at", desc=True).limit(50).execute()

        risk_resp = sb.table("workflow_risk_registry") \
            .select("flow_key,business_impact_level,escalation_priority").eq("enabled", True).execute()
        risk_map = {r["flow_key"]: r for r in (risk_resp.data or [])}

        sla_types = {"sla_warning", "sla_critical", "workflow_degraded"}
        browser_types = {"browser_render_failed", "selector_not_found", "button_not_clickable", "page_timeout", "ui_value_mismatch"}

        flow_counts = {}
        for i in (issues.data or []):
            fk = i.get("flow_key", "")
            flow_counts[fk] = flow_counts.get(fk, 0) + 1

        enriched = []
        for i in (issues.data or []):
            fk = i.get("flow_key", "")
            et = i.get("event_type", "")
            sev = i.get("severity", "WARNING")
            risk = risk_map.get(fk, {})
            impact = risk.get("business_impact_level", "MEDIUM")
            browser = et in browser_types or fk.endswith("_browser")
            sla = et in sla_types
            repeat = flow_counts.get(fk, 0)

            priority = calculate_priority(
                event_type=et, severity=sev, impact_level=impact,
                repeat_count=repeat, browser_affected=browser, sla_affected=sla,
            )
            action = get_recommended_action(
                priority=priority, event_type=et,
                browser_affected=browser, sla_affected=sla, repeat_count=repeat,
            )

            enriched.append({
                "id": i["id"],
                "priority": priority,
                "flow_key": fk,
                "event_type": et,
                "severity": sev,
                "impact_level": impact,
                "repeat_count": repeat,
                "browser_affected": browser,
                "sla_affected": sla,
                "recommended_action": action,
                "description": i.get("description"),
                "created_at": i.get("created_at"),
            })

        p_order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
        enriched.sort(key=lambda x: (p_order.get(x["priority"], 9), x.get("created_at", "")))

        return {"status": "success", "data": enriched, "total": len(enriched)}
    except Exception as e:
        logger.error("Incident priority: %s", e)
        return {"status": "error", "message": str(e)}


@router.get("/risk")
def get_workflow_risk(hours: int = 24):
    """Flow별 운영 위험도."""
    try:
        from watch_engine.incident import compute_risk_score
        sb = _sb()
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        # TASK 30: Mock 제외
        issues = sb.table("engine_integrity_event") \
            .select("flow_key,event_type,severity") \
            .eq("resolved", False).eq("ignored", False) \
            .not_.is_("trace_id", "null") \
            .neq("environment", "mock") \
            .gte("created_at", since).execute()

        sla_types = {"sla_warning", "sla_critical", "workflow_degraded"}
        browser_types = {"browser_render_failed", "selector_not_found", "button_not_clickable", "page_timeout", "ui_value_mismatch"}
        repeat_types = {"repeated_failure", "workflow_instability"}

        flows = {}
        for i in (issues.data or []):
            fk = i.get("flow_key", "unknown")
            if fk not in flows:
                flows[fk] = {"total": 0, "critical": 0, "browser": 0, "sla": 0, "repeat": False}
            flows[fk]["total"] += 1
            if i.get("severity") == "CRITICAL":
                flows[fk]["critical"] += 1
            if i.get("event_type") in browser_types:
                flows[fk]["browser"] += 1
            if i.get("event_type") in sla_types:
                flows[fk]["sla"] += 1
            if i.get("event_type") in repeat_types:
                flows[fk]["repeat"] = True

        risk_resp = sb.table("workflow_risk_registry") \
            .select("flow_key,flow_name,business_impact_level").eq("enabled", True).execute()
        risk_map = {r["flow_key"]: r for r in (risk_resp.data or [])}

        result = []
        all_flows = set(list(flows.keys()) + list(risk_map.keys()))
        for fk in all_flows:
            fd = flows.get(fk, {"total": 0, "critical": 0, "browser": 0, "sla": 0, "repeat": False})
            rm = risk_map.get(fk, {})
            risk = compute_risk_score(
                issue_count_24h=fd["total"],
                critical_count=fd["critical"],
                browser_failure_count=fd["browser"],
                sla_violation_count=fd["sla"],
                repeat_failure=fd["repeat"],
            )
            result.append({
                "flow_key": fk,
                "flow_name": rm.get("flow_name", fk),
                "risk_score": risk,
                "issue_count_24h": fd["total"],
                "critical_count": fd["critical"],
                "browser_failure_count": fd["browser"],
                "sla_violation_count": fd["sla"],
                "repeat_failure": fd["repeat"],
                "impact_level": rm.get("business_impact_level", "MEDIUM"),
            })

        order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        result.sort(key=lambda x: order.get(x["risk_score"], 9))

        return {"status": "success", "data": result}
    except Exception as e:
        logger.error("Workflow risk: %s", e)
        return {"status": "error", "message": str(e)}


@router.get("/repeated")
def get_repeated_failures(hours: int = 24):
    """반복 실패 이슈 목록."""
    try:
        sb = _sb()
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        # TASK 30: Mock 제외
        resp = sb.table("engine_integrity_event") \
            .select("*") \
            .in_("event_type", ["repeated_failure", "workflow_instability"]) \
            .eq("resolved", False).eq("ignored", False) \
            .neq("environment", "mock") \
            .gte("created_at", since) \
            .order("created_at", desc=True).limit(20).execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/detect-repeated")
def run_repeated_detection():
    """반복 실패 탐지 수동 실행."""
    try:
        from watch_engine.incident.repeated import detect_repeated_failures
        sb = _sb()
        result = detect_repeated_failures(sb)
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}
