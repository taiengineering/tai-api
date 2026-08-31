# routers/control_runtime_gateway_api.py — Control Runtime Gateway
"""
\uc678\ubd80/\ub0b4\ubd80 Runtime Event\uc758 \uc911\uc559 \uc785\uad6c.
Runtime Bus \u2192 Validation \u2192 Sovereignty \u2192 Event Store.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from services.time import now_kst, serialize_external_utc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/control-runtime", tags=["\uad00\uc81c Gateway"])


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# \u2550\u2550\u2550 API Key Registry (\ucd08\uae30: \ud658\uacbd\ubcc0\uc218 + \ud558\ub4dc\ucf54\ub529) \u2550\u2550\u2550

def _get_key_registry() -> dict:
    """API Key \u2192 tenant binding. \ud5a5\ud6c4 DB\ub85c \uc774\uc804."""
    # \ud658\uacbd\ubcc0\uc218\uc5d0\uc11c \uac00\uc838\uc624\uac70\ub098 \uae30\ubcf8\uac12
    internal_key = os.environ.get("INTERNAL_API_SECRET", "")
    keys = {}
    if internal_key:
        keys[internal_key] = {"tenant_id": "tai", "namespace": "internal", "runtime": "control"}
    # \uac1c\ubc1c\uc6a9
    keys["dev_test_key"] = {"tenant_id": "dev", "namespace": "external.test", "runtime": "workflow"}
    return keys


def _authenticate(api_key: str) -> dict:
    """API Key \uac80\uc99d \u2192 tenant context."""
    if not api_key:
        raise HTTPException(status_code=401, detail="X-Control-API-Key required")
    registry = _get_key_registry()
    binding = registry.get(api_key)
    if not binding:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return binding


# \u2550\u2550\u2550 Event Push \u2550\u2550\u2550

class EventPayload(BaseModel):
    event_type: str
    tenant_id: Optional[str] = None
    trace_id: Optional[str] = None
    flow_key: Optional[str] = None
    step_key: Optional[str] = None
    step_order: Optional[int] = None
    severity: str = "INFO"
    timestamp: Optional[str] = None
    description: Optional[str] = None
    payload: Optional[dict] = None
    source: Optional[dict] = None
    connector_type: Optional[str] = "api"


@router.post("/events")
def push_event(
    body: EventPayload,
    x_control_api_key: str = Header(default="", alias="X-Control-API-Key"),
):
    """\ud45c\uc900 Event Push \u2014 \uc678\ubd80/\ub0b4\ubd80 Runtime \uacf5\ud1b5."""
    binding = _authenticate(x_control_api_key)

    from watch_engine.runtime_bus import emit_runtime_event, make_context
    ctx = make_context(
        runtime=binding.get("runtime", "workflow"),
        tenant_id=body.tenant_id or binding["tenant_id"],
        environment="production",
    )

    event = body.dict(exclude_none=True)
    if not event.get("tenant_id"):
        event["tenant_id"] = binding["tenant_id"]

    result = emit_runtime_event(ctx, event, sb=_sb())

    if result.status == "blocked":
        raise HTTPException(status_code=400, detail={
            "status": "blocked",
            "validation_status": result.validation_status,
            "blocked_reason": result.blocked_reason,
            "warnings": result.warnings,
        })

    return {"status": result.status, "data": result.to_dict()}


# \u2550\u2550\u2550 Workflow Push \u2550\u2550\u2550

class WorkflowPayload(BaseModel):
    flow_key: str
    event_type: str = "workflow.completed"
    trace_id: Optional[str] = None
    step_key: Optional[str] = None
    severity: str = "INFO"
    payload: Optional[dict] = None


@router.post("/workflows")
def push_workflow(
    body: WorkflowPayload,
    x_control_api_key: str = Header(default="", alias="X-Control-API-Key"),
):
    """Workflow \uc0c1\ud0dc Push."""
    binding = _authenticate(x_control_api_key)

    from watch_engine.runtime_bus import emit_runtime_event, make_context
    ctx = make_context(
        runtime="workflow",
        tenant_id=binding["tenant_id"],
    )

    event = {
        "event_type": body.event_type,
        "flow_key": body.flow_key,
        "trace_id": body.trace_id,
        "step_key": body.step_key,
        "severity": body.severity,
        "tenant_id": binding["tenant_id"],
        "payload": body.payload,
    }
    event = {k: v for k, v in event.items() if v is not None}

    result = emit_runtime_event(ctx, event, sb=_sb())

    if result.status == "blocked":
        raise HTTPException(status_code=400, detail={
            "status": "blocked",
            "blocked_reason": result.blocked_reason,
        })

    return {"status": result.status, "data": result.to_dict()}


# \u2550\u2550\u2550 Heartbeat \u2550\u2550\u2550

class HeartbeatPayload(BaseModel):
    runtime: str = "external"
    service: str = "unknown"
    status: str = "healthy"


@router.post("/heartbeat")
def push_heartbeat(
    body: HeartbeatPayload,
    x_control_api_key: str = Header(default="", alias="X-Control-API-Key"),
):
    """\uc678\ubd80 Runtime \uc0dd\uc874 \uc2e0\ud638."""
    binding = _authenticate(x_control_api_key)
    logger.info(
        "[HEARTBEAT] runtime=%s service=%s status=%s tenant=%s",
        body.runtime, body.service, body.status, binding["tenant_id"],
    )
    return {
        "status": "ok",
        "tenant_id": binding["tenant_id"],
        "received_at": serialize_external_utc(now_kst()),
    }


# \u2550\u2550\u2550 Health \u2550\u2550\u2550

@router.get("/health")
def gateway_health():
    """Gateway \uc0c1\ud0dc."""
    checks = {}

    # Runtime Bus
    try:
        from watch_engine.runtime_bus import emit_runtime_event
        checks["runtime_bus"] = "ok"
    except Exception:
        checks["runtime_bus"] = "error"

    # Validation
    try:
        from watch_engine.runtime_validation import validate_event
        checks["validation"] = "ok"
    except Exception:
        checks["validation"] = "error"

    # Sovereignty
    try:
        from watch_engine.runtime_sovereignty import enforce
        checks["sovereignty"] = "ok"
    except Exception:
        checks["sovereignty"] = "error"

    # DB
    try:
        _sb().table("business_event").select("id", count="exact").limit(1).execute()
        checks["event_store"] = "ok"
    except Exception:
        checks["event_store"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
        "timestamp": serialize_external_utc(now_kst()),
    }
