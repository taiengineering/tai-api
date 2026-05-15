"""Workflow Engine API Router — v1.0.0
prefix: /workflow

API:
  GET    /workflow/states                         상태 레지스트리
  GET    /workflow/transitions                    전이 레지스트리
  GET    /workflow/allowed-next/{state}            다음 허용 상태
  POST   /workflow/validate-transition             전이 검증
  POST   /workflow/emit                            이벤트 발행
  GET    /workflow/timeline/{workflow_id}          타임라인
"""

import logging
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/workflow", tags=["워크플로우엔진"])


# ═══ States ═══

@router.get("/states")
def list_states(workflow_type: str = Query("COMMON")):
    try:
        from workflow_engine.registry.state_registry import get_states
        return {"status": "success", "data": get_states(workflow_type)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Transitions ═══

@router.get("/transitions")
def list_transitions(workflow_type: str = Query("COMMON")):
    try:
        from workflow_engine.registry.transition_registry import get_transitions
        return {"status": "success", "data": get_transitions(workflow_type)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Allowed Next ═══

@router.get("/allowed-next/{state}")
def allowed_next_states(state: str, workflow_type: str = Query("COMMON")):
    try:
        from workflow_engine.registry.transition_registry import get_allowed_next_states
        return {"status": "success", "data": get_allowed_next_states(state, workflow_type)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Validate Transition ═══

class TransitionValidateBody(BaseModel):
    from_state: str
    to_state: str
    workflow_type: str = "COMMON"

@router.post("/validate-transition")
def validate_transition(body: TransitionValidateBody):
    try:
        from workflow_engine.registry.transition_registry import (
            is_valid_transition, get_transition_detail,
        )
        valid = is_valid_transition(body.from_state, body.to_state, body.workflow_type)
        detail = get_transition_detail(body.from_state, body.to_state, body.workflow_type) if valid else None
        return {
            "status": "success",
            "data": {"valid": valid, "detail": detail},
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Emit Workflow Event ═══

class WorkflowEmitBody(BaseModel):
    workflow_id: str
    workflow_type: str = "COMMON"
    from_state: Optional[str] = None
    to_state: str
    event_type: str
    transition: Optional[str] = None
    trace_id: Optional[str] = None
    tenant_id: Optional[str] = None
    triggered_by: Optional[str] = None
    payload: dict = {}

@router.post("/emit")
def emit_workflow_event(body: WorkflowEmitBody):
    try:
        from workflow_engine.contracts.event_contract import WorkflowEventContract
        from workflow_engine.events.emitter import emit_workflow_event as _emit

        event = WorkflowEventContract(
            workflow_id=body.workflow_id,
            workflow_type=body.workflow_type,
            workflow_state=body.to_state,
            from_state=body.from_state,
            event_type=body.event_type,
            transition=body.transition,
            trace_id=body.trace_id,
            tenant_id=body.tenant_id,
            triggered_by=body.triggered_by,
            payload=body.payload,
        )

        result = _emit(event)
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ═══ Timeline ═══

@router.get("/timeline/{workflow_id}")
def get_timeline(workflow_id: str):
    try:
        from workflow_engine.timeline.timeline import get_workflow_timeline
        result = get_workflow_timeline(workflow_id)
        if result is None:
            return {"status": "error", "message": "Timeline not found"}
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}
