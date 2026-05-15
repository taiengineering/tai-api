# routers/watch_engine_governance_api.py — Tenant Governance API
"""
Tenant 영향도 + 조직 안정성 + SLA 위험 tenant.
"""

import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watch-engine/governance", tags=["거버넌스"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/tenants")
def get_tenant_governance(hours: int = 24):
    """Tenant 영향도 전체 현황."""
    try:
        from watch_engine.governance import compute_tenant_impact
        results = compute_tenant_impact(_sb(), hours=hours)

        has_critical = any(t["stability_status"] == "CRITICAL" for t in results)
        has_risk = any(t["stability_status"] == "RISK" for t in results)

        return {"status": "success", "data": {
            "overall": "CRITICAL" if has_critical else ("RISK" if has_risk else "HEALTHY"),
            "tenants": results,
            "total_tenants": len(results),
            "critical_tenants": sum(1 for t in results if t["stability_status"] == "CRITICAL"),
        }}
    except Exception as e:
        logger.error("Tenant governance: %s", e)
        return {"status": "error", "message": str(e)}


@router.get("/tenant/{tenant_id}")
def get_tenant_detail(tenant_id: str):
    """\ud2b9\uc815 tenant \uc0c1\uc138."""
    try:
        sb = _sb()
        reg = sb.table("tenant_operational_registry") \
            .select("*").eq("tenant_id", tenant_id).limit(1).execute()
        if not reg.data:
            return {"status": "error", "message": "tenant \uc5c6\uc74c"}

        # Recent issues
        issues = sb.table("engine_integrity_event") \
            .select("id,flow_key,event_type,severity,description,created_at,resolved") \
            .eq("tenant_id", tenant_id) \
            .not_.is_("trace_id", "null") \
            .order("created_at", desc=True).limit(10).execute()

        return {"status": "success", "data": {
            "registry": reg.data[0],
            "recent_issues": issues.data or [],
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/top-risk")
def get_top_risk_tenants(limit: int = 5):
    """\uc704\ud5d8 tenant TOP."""
    try:
        resp = _sb().table("tenant_operational_registry") \
            .select("*") \
            .in_("stability_status", ["CRITICAL", "RISK", "WATCH"]) \
            .order("active_issue_count", desc=True) \
            .limit(limit).execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/stability")
def get_org_stability():
    """\uc804\uccb4 \uc870\uc9c1 \uc548\uc815\uc131."""
    try:
        resp = _sb().table("tenant_operational_registry") \
            .select("tenant_id,tenant_name,stability_status,escalation_level,active_issue_count,sla_violation_count") \
            .order("active_issue_count", desc=True).execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}
