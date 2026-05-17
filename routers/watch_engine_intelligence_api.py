# routers/watch_engine_intelligence_api.py — Operational Intelligence API v2
"""
운영 Intelligence 조회 + Event Stream + Incident Lifecycle.
Truth 생성 금지. recommendation / prediction / correlation / awareness 전용.
v2: event-stream, incident-lifecycle 추가 (TASK 43).
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


# ═══ Event Stream (TASK 43) ═══

@router.get("/event-stream")
def get_event_stream(limit: int = 50):
    """최근 운영 이벤트 스트림 (Canonical Event 기반)."""
    try:
        sb = _sb()

        # business_event 최근
        be = sb.table("business_event") \
            .select("id,tenant_id,flow_key,step_key,event_type,result,created_at") \
            .neq("environment", "mock") \
            .order("created_at", desc=True).limit(limit // 2).execute()

        # integrity_event 최근
        ie = sb.table("engine_integrity_event") \
            .select("id,tenant_id,flow_key,event_type,severity,description,created_at") \
            .neq("environment", "mock") \
            .order("created_at", desc=True).limit(limit // 2).execute()

        stream = []
        for e in (be.data or []):
            canonical = f"workflow.{e.get('result', 'unknown')}" if e.get("result") else "workflow.event"
            stream.append({
                "event_type": canonical,
                "source": "workflow",
                "severity": "WARNING" if e.get("result") == "failure" else "INFO",
                "tenant_id": e.get("tenant_id"),
                "flow_key": e.get("flow_key"),
                "step_key": e.get("step_key"),
                "summary": f"{e.get('flow_key', '')}.{e.get('step_key', '')} → {e.get('result', '')}",
                "created_at": e.get("created_at"),
            })

        for e in (ie.data or []):
            stream.append({
                "event_type": f"watch.{e.get('event_type', '')}",
                "source": "control",
                "severity": e.get("severity", "WARNING"),
                "tenant_id": e.get("tenant_id"),
                "flow_key": e.get("flow_key"),
                "summary": e.get("description", "")[:100],
                "created_at": e.get("created_at"),
            })

        stream.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return {"status": "success", "data": stream[:limit], "total": len(stream)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Incident Lifecycle (TASK 43) ═══

@router.get("/incident-lifecycle")
def get_incident_lifecycle(hours: int = 24):
    """Incident 상태별 현황."""
    try:
        sb = _sb()
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        issues = sb.table("engine_integrity_event") \
            .select("id,resolved,ignored,severity,event_type") \
            .neq("environment", "mock") \
            .not_.is_("trace_id", "null") \
            .gte("created_at", since).execute()

        actions = sb.table("incident_action_log") \
            .select("action_type") \
            .gte("created_at", since).execute()

        detected = len(issues.data or [])
        resolved = sum(1 for i in (issues.data or []) if i.get("resolved"))
        ignored = sum(1 for i in (issues.data or []) if i.get("ignored"))
        active = detected - resolved - ignored
        acknowledged = sum(1 for a in (actions.data or []) if a.get("action_type") == "ACKNOWLEDGED")
        escalated = sum(1 for a in (actions.data or []) if a.get("action_type") == "ESCALATED")

        return {"status": "success", "data": {
            "detected": detected,
            "active": active,
            "acknowledged": acknowledged,
            "escalated": escalated,
            "resolved": resolved,
            "ignored": ignored,
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}
