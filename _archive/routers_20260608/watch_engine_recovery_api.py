# routers/watch_engine_recovery_api.py — Recovery & Action API
"""
운영 대응/복구 기록 + 추천.
자동 복구 금지. 모든 action은 human-driven.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/watch-engine/recovery", tags=["복구대응"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# ═══ Recovery Recommendations ═══

@router.get("/recommendations")
def get_recovery_recommendations(limit: int = 20):
    """활성 이슈별 복구 추천."""
    try:
        from watch_engine.recovery import get_recovery_recommendation
        sb = _sb()

        issues = sb.table("engine_integrity_event") \
            .select("id,flow_key,event_type,severity,description,created_at") \
            .eq("resolved", False).eq("ignored", False) \
            .not_.is_("trace_id", "null") \
            .order("created_at", desc=True).limit(limit).execute()

        results = []
        for i in (issues.data or []):
            rec = get_recovery_recommendation(sb, i["flow_key"], i["event_type"])

            # Last action
            last_action = sb.table("incident_action_log") \
                .select("action_type,action_result,created_at") \
                .eq("incident_id", i["id"]) \
                .order("created_at", desc=True).limit(1).execute()

            action_count = sb.table("incident_action_log") \
                .select("id", count="exact") \
                .eq("incident_id", i["id"]).execute()

            results.append({
                "incident_id": i["id"],
                "flow_key": i["flow_key"],
                "event_type": i["event_type"],
                "severity": i["severity"],
                "description": i["description"],
                "created_at": i["created_at"],
                "recovery": rec,
                "last_action": last_action.data[0] if last_action.data else None,
                "action_count": action_count.count or 0,
            })

        return {"status": "success", "data": results}
    except Exception as e:
        logger.error("Recovery recommendations: %s", e)
        return {"status": "error", "message": str(e)}


# ═══ Action Log API ═══

class ActionBody(BaseModel):
    action_type: str
    action_note: Optional[str] = None
    operator: str = "founder"


@router.post("/incidents/{incident_id}/action")
def record_action(incident_id: str, body: ActionBody):
    """운영 조치 기록."""
    try:
        sb = _sb()
        sb.table("incident_action_log").insert({
            "incident_id": incident_id,
            "action_type": body.action_type,
            "action_result": "RECORDED",
            "action_by": body.operator,
            "action_note": body.action_note,
        }).execute()

        # ACK/RESOLVE/IGNORE 시 integrity event도 업데이트
        if body.action_type == "ACKNOWLEDGED":
            sb.table("engine_integrity_event").update({
                "acknowledged": True,
                "acknowledged_at": datetime.now(timezone.utc).isoformat(),
                "acknowledged_by": body.operator,
            }).eq("id", incident_id).execute()
        elif body.action_type == "RESOLVED":
            sb.table("engine_integrity_event").update({
                "resolved": True,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "operator_note": body.action_note,
            }).eq("id", incident_id).execute()
        elif body.action_type == "IGNORED":
            sb.table("engine_integrity_event").update({
                "ignored": True,
                "ignored_reason": body.action_note or "\uc6b4\uc601\uc790 \ud310\ub2e8",
            }).eq("id", incident_id).execute()

        return {"status": "success", "message": f"{body.action_type} \uae30\ub85d \uc644\ub8cc"}
    except Exception as e:
        logger.error("Record action failed: %s", e)
        return {"status": "error", "message": str(e)}


@router.get("/incidents/{incident_id}/actions")
def get_actions(incident_id: str):
    """조\uce58 \uc774\ub825."""
    try:
        resp = _sb().table("incident_action_log") \
            .select("*").eq("incident_id", incident_id) \
            .order("created_at", desc=True).execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/registry")
def get_recovery_registry():
    """복\uad6c \ub9e4\ud551 \ubaa9\ub85d."""
    try:
        resp = _sb().table("workflow_recovery_registry") \
            .select("*").eq("enabled", True).order("flow_key").execute()
        return {"status": "success", "data": resp.data or []}
    except Exception as e:
        return {"status": "error", "message": str(e)}
