# routers/watch_engine_intelligence_api.py — Operational Intelligence API v3
"""
운영 Intelligence 조회 + Event Stream + Incident Lifecycle + Synthetic Status.
Truth 생성 금지. recommendation / prediction / correlation / awareness 전용.
v3: synthetic-status, operational-density, synthetic-event-stream (TASK 46).
"""

import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watch/intelligence", tags=["운영지능"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/repeated-failures")
def get_repeated_failures(hours: int = 24):
    try:
        from watch_engine.intelligence import analyze_repeated_failures
        results = analyze_repeated_failures(_sb(), hours=hours)
        return {"status": "success", "data": [r.to_dict() for r in results], "total": len(results)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/patterns")
def get_patterns(hours: int = 48):
    try:
        from watch_engine.intelligence import analyze_patterns
        results = analyze_patterns(_sb(), hours=hours)
        return {"status": "success", "data": [r.to_dict() for r in results], "total": len(results)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/tenant-degradation")
def get_tenant_degradation(hours: int = 24):
    try:
        from watch_engine.intelligence import analyze_tenant_degradation
        results = analyze_tenant_degradation(_sb(), hours=hours)
        return {"status": "success", "data": [r.to_dict() for r in results], "total": len(results)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/recovery-recommendations")
def get_recovery_recommendations(event_type: str = None):
    try:
        from watch_engine.intelligence import recommend_recovery
        results = recommend_recovery(_sb(), event_type=event_type)
        return {"status": "success", "data": [r.to_dict() for r in results], "total": len(results)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/summary")
def get_intelligence_summary(hours: int = 24):
    try:
        from watch_engine.intelligence import (
            analyze_repeated_failures, analyze_patterns,
            analyze_tenant_degradation, recommend_recovery,
        )
        sb = _sb()
        repeated = analyze_repeated_failures(sb, hours=hours)
        patterns = analyze_patterns(sb, hours=hours * 2)
        degradation = analyze_tenant_degradation(sb, hours=hours)
        recovery = recommend_recovery(sb)

        critical_repeated = sum(1 for r in repeated if r.severity == "CRITICAL")
        accelerating = sum(1 for p in patterns if p.details.get("trend") == "ACCELERATING")
        degrading_tenants = sum(1 for d in degradation if "악화" in d.summary)
        top_risk = max((r.risk_score for r in repeated), default=0)

        return {"status": "success", "data": {
            "repeated_failures": len(repeated),
            "critical_repeated": critical_repeated,
            "pattern_trends": len(patterns),
            "accelerating_trends": accelerating,
            "tenant_degradations": len(degradation),
            "degrading_tenants": degrading_tenants,
            "recovery_actions": len(recovery),
            "top_risk_score": top_risk,
            "analysis_hours": hours,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Event Stream ═══

@router.get("/event-stream")
def get_event_stream(limit: int = 50, include_mock: bool = False):
    """최근 운영 이벤트 스트림."""
    try:
        sb = _sb()
        q_be = sb.table("business_event") \
            .select("id,tenant_id,flow_key,step_key,event_type,result,environment,created_at") \
            .order("created_at", desc=True).limit(limit // 2)
        q_ie = sb.table("engine_integrity_event") \
            .select("id,tenant_id,flow_key,event_type,severity,description,environment,created_at") \
            .order("created_at", desc=True).limit(limit // 2)

        if not include_mock:
            q_be = q_be.neq("environment", "mock")
            q_ie = q_ie.neq("environment", "mock")

        be = q_be.execute()
        ie = q_ie.execute()

        stream = []
        for e in (be.data or []):
            canonical = f"workflow.{e.get('result', 'unknown')}" if e.get("result") else "workflow.event"
            is_mock = e.get("environment") == "mock"
            stream.append({
                "event_type": canonical, "source": "workflow",
                "severity": "WARNING" if e.get("result") == "failure" else "INFO",
                "tenant_id": e.get("tenant_id"), "flow_key": e.get("flow_key"),
                "step_key": e.get("step_key"),
                "summary": f"{e.get('flow_key','')}.{e.get('step_key','')} → {e.get('result','')}",
                "created_at": e.get("created_at"), "synthetic": is_mock,
            })

        for e in (ie.data or []):
            is_mock = e.get("environment") == "mock"
            stream.append({
                "event_type": f"watch.{e.get('event_type','')}", "source": "control",
                "severity": e.get("severity", "WARNING"),
                "tenant_id": e.get("tenant_id"), "flow_key": e.get("flow_key"),
                "summary": (e.get("description") or "")[:100],
                "created_at": e.get("created_at"), "synthetic": is_mock,
            })

        stream.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return {"status": "success", "data": stream[:limit], "total": len(stream)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Incident Lifecycle ═══

@router.get("/incident-lifecycle")
def get_incident_lifecycle(hours: int = 24):
    try:
        sb = _sb()
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        issues = sb.table("engine_integrity_event") \
            .select("id,resolved,ignored,severity,event_type") \
            .neq("environment", "mock").not_.is_("trace_id", "null") \
            .gte("created_at", since).execute()
        actions = sb.table("incident_action_log") \
            .select("action_type").gte("created_at", since).execute()

        detected = len(issues.data or [])
        resolved = sum(1 for i in (issues.data or []) if i.get("resolved"))
        ignored = sum(1 for i in (issues.data or []) if i.get("ignored"))
        active = detected - resolved - ignored
        acknowledged = sum(1 for a in (actions.data or []) if a.get("action_type") == "ACKNOWLEDGED")
        escalated = sum(1 for a in (actions.data or []) if a.get("action_type") == "ESCALATED")

        return {"status": "success", "data": {
            "detected": detected, "active": active, "acknowledged": acknowledged,
            "escalated": escalated, "resolved": resolved, "ignored": ignored,
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Synthetic Status (TASK 46) ═══

@router.get("/synthetic-status")
def get_synthetic_status(hours: int = 1):
    """Synthetic Runtime 실행 현황."""
    try:
        sb = _sb()
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        # Synthetic business_event
        be = sb.table("business_event").select("id,tenant_id,flow_key,result", count="exact") \
            .eq("environment", "mock").gte("created_at", since).execute()

        # Synthetic integrity_event
        ie = sb.table("engine_integrity_event").select("id,severity,event_type", count="exact") \
            .eq("environment", "mock").gte("created_at", since).execute()

        # Persona 분포
        persona_counts = {}
        for e in (be.data or []):
            tid = e.get("tenant_id", "")
            persona_counts[tid] = persona_counts.get(tid, 0) + 1

        # Flow 분포
        flow_counts = {}
        for e in (be.data or []):
            fk = e.get("flow_key", "unknown")
            flow_counts[fk] = flow_counts.get(fk, 0) + 1

        # Result 분포
        result_counts = {}
        for e in (be.data or []):
            r = e.get("result", "unknown")
            result_counts[r] = result_counts.get(r, 0) + 1

        # Severity 분포 (integrity)
        sev_counts = {}
        for e in (ie.data or []):
            s = e.get("severity", "INFO")
            sev_counts[s] = sev_counts.get(s, 0) + 1

        # Chaos (integrity에서 CHAOS 포함)
        chaos_count = sum(1 for e in (ie.data or []) if "CHAOS" in (e.get("event_type") or "").upper()
                         or "chaos" in (e.get("event_type") or ""))

        # Scheduler 마지막 실행
        cron_logs = sb.table("cron_job_log").select("job_code,status,started_at,duration_seconds") \
            .in_("job_code", ["SYNTHETIC_RUNTIME_TICK", "SYNTHETIC_CHAOS_INJECTION", "CONTROL_BRIDGE_EVALUATE"]) \
            .order("started_at", desc=True).limit(6).execute()

        return {"status": "success", "data": {
            "window_hours": hours,
            "workflow_events": be.count or len(be.data or []),
            "integrity_events": ie.count or len(ie.data or []),
            "active_tenants": len(persona_counts),
            "tenant_distribution": dict(sorted(persona_counts.items(), key=lambda x: -x[1])[:10]),
            "flow_distribution": dict(sorted(flow_counts.items(), key=lambda x: -x[1])),
            "result_distribution": result_counts,
            "severity_distribution": sev_counts,
            "chaos_events": chaos_count,
            "scheduler_recent": cron_logs.data or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Operational Density (TASK 46) ═══

@router.get("/operational-density")
def get_operational_density(hours: int = 1):
    """운영 밀도 KPI."""
    try:
        sb = _sb()
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        be_count = sb.table("business_event").select("id", count="exact") \
            .eq("environment", "mock").gte("created_at", since).execute()
        ie_count = sb.table("engine_integrity_event").select("id", count="exact") \
            .eq("environment", "mock").gte("created_at", since).execute()

        wf_total = be_count.count or 0
        ie_total = ie_count.count or 0

        # WARNING/CRITICAL 카운트
        warnings = sb.table("engine_integrity_event").select("id", count="exact") \
            .eq("environment", "mock").eq("severity", "WARNING").gte("created_at", since).execute()
        criticals = sb.table("engine_integrity_event").select("id", count="exact") \
            .eq("environment", "mock").eq("severity", "CRITICAL").gte("created_at", since).execute()

        return {"status": "success", "data": {
            "window_hours": hours,
            "workflow_per_hour": round(wf_total / max(hours, 1), 1),
            "incident_per_hour": round(ie_total / max(hours, 1), 1),
            "warning_count": warnings.count or 0,
            "critical_count": criticals.count or 0,
            "total_events": wf_total + ie_total,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}
