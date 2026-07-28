"""운영 자동화 라우터 (WO-12 AutomationEngine).

Goal: G-ms4je4z3-33eada
- 규칙 CRUD + 수동 발화 + 실행 이력 + 승인 실행. 얇은 위임.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from services.automation_svc import (
    ACTION_TYPES, EVENT_TYPES, AutomationError, approve_run, fire,
)

router = APIRouter(prefix="/automation", tags=["운영자동화"])


class RuleBody(BaseModel):
    rule_code: str
    event_type: str
    action_type: str
    condition_json: Optional[Dict[str, Any]] = None
    action_config_json: Optional[Dict[str, Any]] = None
    require_approval: bool = True
    enabled: bool = True
    memo: Optional[str] = None
    by: Optional[str] = None


class FireBody(BaseModel):
    event_type: str
    payload: Dict[str, Any] = {}
    trigger_ref: Optional[str] = None


@router.get("/rules")
def list_rules(event_type: Optional[str] = Query(None), enabled: Optional[bool] = Query(None)):
    q = get_supabase().table("automation_rule").select("*")
    if event_type:
        q = q.eq("event_type", event_type)
    if enabled is not None:
        q = q.eq("enabled", enabled)
    res = q.order("created_at", desc=True).execute()
    return {"status": "success", "data": res.data or []}


@router.post("/rules")
def create_rule(body: RuleBody):
    if body.event_type not in EVENT_TYPES:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 이벤트: {body.event_type}")
    if body.action_type not in ACTION_TYPES:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 액션: {body.action_type}")
    row = {
        "rule_code": body.rule_code, "event_type": body.event_type,
        "action_type": body.action_type,
        "condition_json": body.condition_json or {},
        "action_config_json": body.action_config_json or {},
        "require_approval": body.require_approval, "enabled": body.enabled,
        "memo": body.memo, "created_by": body.by,
    }
    try:
        res = get_supabase().table("automation_rule").insert(row).execute()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"규칙 생성 실패(중복 rule_code?): {e}")
    return {"status": "success", "data": res.data[0] if res.data else None}


@router.patch("/rules/{rule_id}/toggle")
def toggle_rule(rule_id: str, enabled: bool = Query(...)):
    res = get_supabase().table("automation_rule").update({"enabled": enabled}).eq("id", rule_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="규칙을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.post("/fire")
def fire_event(body: FireBody):
    """수동/외부 이벤트 발화."""
    try:
        result = fire(body.event_type, body.payload, trigger_ref=body.trigger_ref)
    except AutomationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"status": "success", "data": result}


@router.get("/runs")
def list_runs(status: Optional[str] = Query(None), limit: int = Query(default=50, ge=1, le=200)):
    q = get_supabase().table("automation_run_log").select("*")
    if status:
        q = q.eq("status", status)
    res = q.order("created_at", desc=True).limit(limit).execute()
    return {"status": "success", "data": res.data or []}


@router.post("/runs/{run_id}/approve")
def approve(run_id: str, by: Optional[str] = Query(None)):
    """승인 대기 건 실행."""
    try:
        result = approve_run(run_id, actor=by)
    except AutomationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"status": "success", "data": result}
