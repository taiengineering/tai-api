"""Workflow Alert API Router — v1.0.0

운영 Alert 관리: 평가, ACK, Resolve, Timeline.
Notification Runtime API와 완전 분리.
"""

import logging
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workflow/alerts", tags=["운영알러트"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# ═══ Alert Rules ═══

@router.get("/rules")
def list_alert_rules():
    try:
        resp = _sb().table("alert_rule_registry_v2") \
            .select("*").order("rule_code").execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Manual Evaluate ═══

class EvaluateBody(BaseModel):
    integrity_type: str
    workflow_id: Optional[str] = None
    integrity_event_id: Optional[str] = None
    trace_id: Optional[str] = None
    tenant_id: Optional[str] = None
    workflow_type: str = "COMMON"
    payload: dict = {}

@router.post("/evaluate")
def evaluate_alert(body: EvaluateBody):
    try:
        from workflow_alert.evaluator import evaluate_integrity_event
        result = evaluate_integrity_event(
            integrity_type=body.integrity_type,
            workflow_id=body.workflow_id,
            integrity_event_id=body.integrity_event_id,
            trace_id=body.trace_id,
            tenant_id=body.tenant_id,
            payload=body.payload,
            workflow_type=body.workflow_type,
        )
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Alert 목록 ═══

@router.get("")
def list_alerts(
    severity: Optional[str] = None,
    resolved: Optional[bool] = None,
    limit: int = Query(20, ge=1, le=100),
):
    try:
        q = _sb().table("workflow_alert_event") \
            .select("*").order("created_at", desc=True).limit(limit)
        if severity:
            q = q.eq("severity", severity)
        if resolved is not None:
            q = q.eq("resolved", resolved)
        resp = q.execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Timeline (workflow_id) ═══

@router.get("/timeline/{workflow_id}")
def alert_timeline(workflow_id: str):
    try:
        from workflow_alert.timeline import get_alert_timeline
        result = get_alert_timeline(workflow_id)
        if result is None:
            return {"status": "error", "message": "Not found"}
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ ACK ═══

@router.post("/{alert_id}/ack")
def ack_alert(alert_id: str):
    try:
        from workflow_alert.lifecycle import ack_alert as _ack
        return _ack(alert_id)
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Resolve ═══

@router.post("/{alert_id}/resolve")
def resolve_alert(alert_id: str):
    try:
        from workflow_alert.lifecycle import resolve_alert as _resolve
        return _resolve(alert_id)
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Open Alert Summary ═══

@router.get("/summary")
def alert_summary():
    try:
        sb = _sb()
        total = sb.table("workflow_alert_event") \
            .select("id", count="exact").execute()
        open_alerts = sb.table("workflow_alert_event") \
            .select("id", count="exact").eq("resolved", False).execute()
        critical = sb.table("workflow_alert_event") \
            .select("id", count="exact") \
            .eq("severity", "CRITICAL").eq("resolved", False).execute()
        unacked = sb.table("workflow_alert_event") \
            .select("id", count="exact") \
            .eq("acknowledged", False).eq("resolved", False).execute()

        return {
            "status": "success",
            "data": {
                "total": total.count or 0,
                "open": open_alerts.count or 0,
                "critical_open": critical.count or 0,
                "unacknowledged": unacked.count or 0,
            },
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
