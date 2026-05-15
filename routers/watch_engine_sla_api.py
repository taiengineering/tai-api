# routers/watch_engine_sla_api.py — Workflow SLA & User Impact API
"""
Business SLA 상태 + User Impact 요약.
Cockpit UI에서 업무 완료 품질 확인.
"""

import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watch-engine/sla", tags=["SLA관제"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/status")
def get_sla_status(hours: int = 24):
    """Workflow SLA 현황 + User Impact 요약."""
    try:
        sb = _sb()
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        # SLA registry
        registry = sb.table("workflow_sla_registry") \
            .select("*").eq("enabled", True).order("flow_key").execute()

        # SLA violation events (recent)
        violations = sb.table("engine_integrity_event") \
            .select("flow_key,event_type,severity,trace_id,detail,created_at") \
            .in_("event_type", ["sla_warning", "sla_critical", "workflow_degraded"]) \
            .eq("resolved", False).eq("ignored", False) \
            .gte("created_at", since) \
            .not_.is_("trace_id", "null") \
            .order("created_at", desc=True).execute()

        # Aggregate per flow
        flow_sla = {}
        for reg in (registry.data or []):
            fk = reg["flow_key"]
            flow_sla[fk] = {
                "flow_key": fk,
                "flow_name": reg.get("flow_name", fk),
                "sla_warning_ms": reg["sla_warning_ms"],
                "sla_critical_ms": reg["sla_critical_ms"],
                "impact_level": reg.get("business_impact_level"),
                "warning_count": 0,
                "critical_count": 0,
                "degraded_count": 0,
                "affected_traces": set(),
                "status": "HEALTHY",
            }

        for v in (violations.data or []):
            fk = v.get("flow_key", "")
            if fk not in flow_sla:
                flow_sla[fk] = {
                    "flow_key": fk, "flow_name": fk,
                    "warning_count": 0, "critical_count": 0, "degraded_count": 0,
                    "affected_traces": set(), "status": "UNKNOWN",
                    "sla_warning_ms": None, "sla_critical_ms": None,
                    "impact_level": None,
                }
            et = v.get("event_type")
            if et == "sla_warning":
                flow_sla[fk]["warning_count"] += 1
            elif et == "sla_critical":
                flow_sla[fk]["critical_count"] += 1
            elif et == "workflow_degraded":
                flow_sla[fk]["degraded_count"] += 1
            if v.get("trace_id"):
                flow_sla[fk]["affected_traces"].add(v["trace_id"])

        # Calculate status + user impact
        total_affected_traces = set()
        total_affected_tenants = set()

        result_flows = []
        for fk, data in flow_sla.items():
            traces = data.pop("affected_traces")
            data["affected_trace_count"] = len(traces)
            total_affected_traces.update(traces)

            if data["critical_count"] > 0:
                data["status"] = "CRITICAL"
            elif data["degraded_count"] > 0 or data["warning_count"] > 2:
                data["status"] = "DEGRADED"
            else:
                data["status"] = "HEALTHY"

            result_flows.append(data)

        # Tenant impact from affected traces
        if total_affected_traces:
            tenant_resp = sb.table("business_event") \
                .select("tenant_id") \
                .in_("trace_id", list(total_affected_traces)[:50]) \
                .execute()
            for t in (tenant_resp.data or []):
                if t.get("tenant_id"):
                    total_affected_tenants.add(t["tenant_id"])

        # Sort: CRITICAL first, then DEGRADED, then HEALTHY
        order = {"CRITICAL": 0, "DEGRADED": 1, "HEALTHY": 2, "UNKNOWN": 3}
        result_flows.sort(key=lambda x: order.get(x["status"], 9))

        # Overall
        has_critical = any(f["status"] == "CRITICAL" for f in result_flows)
        has_degraded = any(f["status"] == "DEGRADED" for f in result_flows)

        return {
            "status": "success",
            "data": {
                "overall": "CRITICAL" if has_critical else ("DEGRADED" if has_degraded else "HEALTHY"),
                "flows": result_flows,
                "impact": {
                    "affected_traces": len(total_affected_traces),
                    "affected_tenants": len(total_affected_tenants),
                    "estimated_users": len(total_affected_traces),  # 1 trace \u2248 1 user
                },
                "period_hours": hours,
            }
        }
    except Exception as e:
        logger.error("SLA status: %s", e)
        return {"status": "error", "message": str(e)}


@router.get("/registry")
def get_sla_registry():
    """SLA \uae30\uc900 \ubaa9\ub85d."""
    try:
        resp = _sb().table("workflow_sla_registry") \
            .select("*").order("flow_key").execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


from pydantic import BaseModel
from typing import Optional

class SlaUpdate(BaseModel):
    sla_warning_ms: Optional[int] = None
    sla_critical_ms: Optional[int] = None
    escalation_enabled: Optional[bool] = None
    business_impact_level: Optional[str] = None
    enabled: Optional[bool] = None


@router.patch("/registry/{flow_key}")
def update_sla(flow_key: str, body: SlaUpdate):
    """SLA \uae30\uc900 \uc218\uc815 (UI\uc5d0\uc11c)."""
    try:
        update = {k: v for k, v in body.dict().items() if v is not None}
        update["updated_at"] = datetime.now(timezone.utc).isoformat()
        _sb().table("workflow_sla_registry").update(update).eq("flow_key", flow_key).execute()
        return {"status": "success", "message": f"{flow_key} SLA \uc218\uc815 \uc644\ub8cc"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
