# routers/watch_engine_control_api.py — Operational Control Surface API
"""
Message Template + Notification Routing + Workflow Visual Registry.
운영자가 UI에서 조정 가능한 레이어.
P0 흐름(Payment/SaaS/Document) 영향 없음.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from services.time import now_kst, serialize_external_utc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watch-engine/control", tags=["운영제어"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# ═══ Message Templates ═══

@router.get("/templates")
def list_templates(category: str = None):
    try:
        q = _sb().table("message_template_registry").select("*").order("category,template_key")
        if category:
            q = q.eq("category", category)
        return {"status": "success", "data": q.execute().data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


class TemplateUpdate(BaseModel):
    template_name: Optional[str] = None
    title_template: Optional[str] = None
    body_template: Optional[str] = None
    enabled: Optional[bool] = None
    audience_type: Optional[str] = None
    channel: Optional[str] = None


@router.patch("/templates/{template_key}")
def update_template(template_key: str, body: TemplateUpdate):
    try:
        update = {k: v for k, v in body.dict().items() if v is not None}
        update["updated_at"] = serialize_external_utc(now_kst())
        _sb().table("message_template_registry").update(update).eq("template_key", template_key).execute()
        return {"status": "success", "message": f"{template_key} \uc218\uc815 \uc644\ub8cc"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Notification Routing ═══

@router.get("/routing")
def list_routing():
    try:
        resp = _sb().table("notification_routing_registry").select("*").order("severity,event_type").execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


class RoutingUpdate(BaseModel):
    audience_key: Optional[str] = None
    channel: Optional[str] = None
    template_key: Optional[str] = None
    cooldown_minutes: Optional[int] = None
    escalation_level: Optional[str] = None
    enabled: Optional[bool] = None


@router.patch("/routing/{route_key}")
def update_routing(route_key: str, body: RoutingUpdate):
    try:
        update = {k: v for k, v in body.dict().items() if v is not None}
        update["updated_at"] = serialize_external_utc(now_kst())
        _sb().table("notification_routing_registry").update(update).eq("route_key", route_key).execute()
        return {"status": "success", "message": f"{route_key} \uc218\uc815 \uc644\ub8cc"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Workflow Visual ═══

@router.get("/workflows")
def list_workflows(category: str = None):
    try:
        q = _sb().table("workflow_visual_registry").select("*").order("category,flow_key")
        if category:
            q = q.eq("category", category)
        return {"status": "success", "data": q.execute().data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/workflows/{flow_key}")
def get_workflow_detail(flow_key: str):
    try:
        sb = _sb()
        wf = sb.table("workflow_visual_registry").select("*").eq("flow_key", flow_key).limit(1).execute()
        if not wf.data:
            return {"status": "error", "message": "workflow \uc5c6\uc74c"}
        steps = sb.table("flow_step_registry").select("step_key,step_order,step_name,connector_type,is_required,timeout_ms") \
            .eq("flow_key", flow_key).order("step_order").execute()
        rules = sb.table("flow_integrity_rule_registry").select("rule_key,rule_type,severity_on_fail,description") \
            .eq("flow_key", flow_key).eq("is_active", True).execute()
        sla = sb.table("workflow_sla_registry").select("sla_warning_ms,sla_critical_ms,business_impact_level") \
            .eq("flow_key", flow_key).limit(1).execute()
        return {"status": "success", "data": {
            "workflow": wf.data[0],
            "steps": steps.data or [],
            "rules": rules.data or [],
            "sla": sla.data[0] if sla.data else None,
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Summary ═══

@router.get("/summary")
def get_control_summary():
    try:
        sb = _sb()
        tpl = sb.table("message_template_registry").select("template_key", count="exact").eq("enabled", True).execute()
        routes = sb.table("notification_routing_registry").select("route_key", count="exact").eq("enabled", True).execute()
        wf = sb.table("workflow_visual_registry").select("flow_key", count="exact").eq("enabled", True).execute()
        return {"status": "success", "data": {
            "templates": tpl.count or 0,
            "routing_rules": routes.count or 0,
            "workflows": wf.count or 0,
        }}
    except Exception as e:
        return {"status": "error", "message": str(e)}
