"""TAI Staged Runtime Activation API v1.0.0
Publish 후 단계적 runtime rollout 통제.

Publish ≠ 즉시 전체 적용.
흐름: publish → INTERNAL → PILOT → LIMITED → EXPANDED → FULL
절대 금지: 전체 tenant 즉시 활성화, regression 미검증 rollout, AI rollout decision.
"""
from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional
import logging
from datetime import datetime

router = APIRouter(prefix="/runtime-activation", tags=["Runtime Activation"])
logger = logging.getLogger("runtime_activation")

ALLOWED_ROLES = {"ROLE_ENGINE_ADMIN", "ROLE_SUPER_ADMIN", "admin", "super_admin"}
STAGE_ORDER = ["INTERNAL", "PILOT", "LIMITED", "EXPANDED", "FULL"]
STAGE_PCT = {"INTERNAL": 1, "PILOT": 5, "LIMITED": 10, "EXPANDED": 50, "FULL": 100}


def _check_admin(request: Request):
    role = getattr(request.state, "user_role", None)
    if role and role not in ALLOWED_ROLES:
        raise HTTPException(403, "Runtime activation is admin-only.")


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/activations")
def list_activations(request: Request, activation_status: Optional[str] = Query(None), page: int = Query(1, ge=1)):
    _check_admin(request)
    sb = _sb()
    q = sb.table("runtime_activation_registry").select("*")
    if activation_status:
        q = q.eq("activation_status", activation_status)
    offset = (page - 1) * 20
    q = q.order("created_at", desc=True).range(offset, offset + 19)
    r = q.execute()
    return {"status": "success", "data": r.data or [], "page": page}


@router.get("/activation/{activation_id}")
def get_activation(request: Request, activation_id: str):
    _check_admin(request)
    sb = _sb()
    r = sb.table("runtime_activation_registry").select("*").eq("id", activation_id).execute()
    if not r.data:
        raise HTTPException(404, "Activation not found")
    return {"status": "success", "data": r.data[0]}


@router.post("/create-rollout")
def create_rollout(request: Request, release_id: str = Query(...)):
    """Release에 대한 staged rollout 시작 (INTERNAL 단계)"""
    _check_admin(request)
    sb = _sb()
    rel = sb.table("engine_release_registry").select("*").eq("id", release_id).execute()
    if not rel.data:
        raise HTTPException(404, "Release not found")
    if rel.data[0]["publish_status"] != "PUBLISHED":
        raise HTTPException(400, "Release must be PUBLISHED to start rollout")

    row = {
        "release_id": release_id,
        "activation_stage": "INTERNAL",
        "activation_status": "ACTIVE",
        "rollout_percentage": 1,
        "regression_status": "PENDING",
        "drift_status": "CLEAN",
        "activation_started_at": datetime.utcnow().isoformat(),
        "source_trace": "STAGED_ROLLOUT",
    }
    r = sb.table("runtime_activation_registry").insert(row).execute()
    logger.info(f"ROLLOUT_CREATED | release={release_id} stage=INTERNAL")
    return {"status": "success", "data": r.data[0] if r.data else row}


@router.post("/advance-stage/{activation_id}")
def advance_stage(request: Request, activation_id: str):
    """\ub2e4\uc74c rollout stage\ub85c \uc9c4\ud589 (gate validation \ud1b5\uacfc \uc2dc)"""
    _check_admin(request)
    sb = _sb()
    act = sb.table("runtime_activation_registry").select("*").eq("id", activation_id).execute()
    if not act.data:
        raise HTTPException(404, "Activation not found")

    current = act.data[0]
    if current["activation_status"] != "ACTIVE":
        raise HTTPException(400, f"Cannot advance: status is {current['activation_status']}")
    if current["regression_status"] != "PASSED":
        raise HTTPException(400, "Cannot advance: regression not passed")
    if current["drift_status"] in ("DETECTED", "CRITICAL"):
        raise HTTPException(400, f"Cannot advance: drift status is {current['drift_status']}")

    cur_idx = STAGE_ORDER.index(current["activation_stage"]) if current["activation_stage"] in STAGE_ORDER else 0
    if cur_idx >= len(STAGE_ORDER) - 1:
        raise HTTPException(400, "Already at FULL stage")

    next_stage = STAGE_ORDER[cur_idx + 1]
    sb.table("runtime_activation_registry").update({
        "activation_stage": next_stage,
        "rollout_percentage": STAGE_PCT.get(next_stage, 100),
    }).eq("id", activation_id).execute()

    logger.info(f"ROLLOUT_ADVANCED | id={activation_id} stage={next_stage}")
    return {"status": "success", "new_stage": next_stage, "rollout_percentage": STAGE_PCT.get(next_stage, 100)}


@router.post("/verify-drift/{activation_id}")
def verify_drift(request: Request, activation_id: str):
    """Rollout 후 drift 검증"""
    _check_admin(request)
    sb = _sb()
    act = sb.table("runtime_activation_registry").select("*").eq("id", activation_id).execute()
    if not act.data:
        raise HTTPException(404, "Activation not found")

    # drift 검사 (integrity events 기반)
    critical = sb.table("engine_integrity_event").select("id").in_(
        "severity", ["CRITICAL", "HIGH"]
    ).eq("resolved", False).execute()
    drift_count = len(critical.data or [])

    drift_status = "CLEAN" if drift_count == 0 else "WARNING" if drift_count < 3 else "DETECTED" if drift_count < 10 else "CRITICAL"
    regression_status = "PASSED" if drift_count < 3 else "FAILED"

    sb.table("runtime_activation_registry").update({
        "drift_status": drift_status,
        "regression_status": regression_status,
        "activation_status": "BLOCKED" if drift_status == "CRITICAL" else "ACTIVE",
    }).eq("id", activation_id).execute()

    if drift_status == "CRITICAL":
        sb.table("engine_integrity_event").insert({
            "event_type": "ACTIVATION_DRIFT_DETECTED",
            "severity": "CRITICAL",
            "domain": "RUNTIME_ACTIVATION",
            "description": f"Rollout drift CRITICAL: {drift_count} unresolved events",
            "source_trace": "INTEGRITY_MONITOR",
        }).execute()

    return {"status": "success", "drift_status": drift_status, "regression_status": regression_status, "unresolved_events": drift_count}


@router.post("/rollback/{activation_id}")
def rollback_activation(request: Request, activation_id: str):
    _check_admin(request)
    sb = _sb()
    act = sb.table("runtime_activation_registry").select("*").eq("id", activation_id).execute()
    if not act.data:
        raise HTTPException(404, "Activation not found")
    if not act.data[0].get("rollback_available"):
        raise HTTPException(400, "Rollback not available")

    sb.table("runtime_activation_registry").update({
        "activation_status": "ROLLED_BACK",
        "activation_completed_at": datetime.utcnow().isoformat(),
    }).eq("id", activation_id).execute()

    sb.table("engine_integrity_event").insert({
        "event_type": "ROLLBACK_TRIGGERED",
        "severity": "HIGH",
        "domain": "RUNTIME_ACTIVATION",
        "description": f"Activation {activation_id} rolled back",
        "source_trace": "INTEGRITY_MONITOR",
    }).execute()

    return {"status": "success", "rolled_back": True}


@router.get("/tenant-risk")
def list_tenant_risk(request: Request):
    _check_admin(request)
    sb = _sb()
    r = sb.table("tenant_risk_profile").select("*").order("rollout_priority").limit(100).execute()
    return {"status": "success", "data": r.data or []}


@router.get("/status")
def activation_status():
    sb = _sb()
    acts = sb.table("runtime_activation_registry").select("id", count="exact").execute()
    active = sb.table("runtime_activation_registry").select("id").eq("activation_status", "ACTIVE").execute()
    return {
        "status": "active",
        "engine": "Staged Runtime Activation v1.0.0",
        "total_activations": len(acts.data or []),
        "active_rollouts": len(active.data or []),
        "stages": STAGE_ORDER,
        "boundary": "DETERMINISTIC_ONLY",
    }
