"""TAI Runtime Chaos Testing API v1.0.0
Runtime rollout 중 contamination 검증.

목적: chaos 상황에서 deterministic consistency 유지 검증.
절대 금지: AI 자동복구, production destructive write, semantic fallback.
"""
from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional
import logging
from datetime import datetime

router = APIRouter(prefix="/runtime-chaos", tags=["Runtime Chaos QA"])
logger = logging.getLogger("runtime_chaos")

ALLOWED_ROLES = {"ROLE_ENGINE_ADMIN", "ROLE_SUPER_ADMIN", "admin", "super_admin"}


def _check_admin(request: Request):
    role = getattr(request.state, "user_role", None)
    if role and role not in ALLOWED_ROLES:
        raise HTTPException(403, "Chaos testing is admin-only.")


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


@router.get("/scenarios")
def list_scenarios(request: Request, scenario_type: Optional[str] = Query(None)):
    _check_admin(request)
    sb = _sb()
    q = sb.table("runtime_chaos_scenario").select("*")
    if scenario_type:
        q = q.eq("scenario_type", scenario_type)
    q = q.order("scenario_code").limit(100)
    r = q.execute()
    return {"status": "success", "data": r.data or []}


@router.post("/run-chaos")
def run_chaos_test(request: Request):
    """\uc804\uccb4 chaos \uc2dc\ub098\ub9ac\uc624 \uc2e4\ud589 (sandbox/pilot \ud658\uacbd)"""
    _check_admin(request)
    sb = _sb()
    scenarios = sb.table("runtime_chaos_scenario").select("*").eq("enabled", True).execute()
    all_sc = scenarios.data or []
    results = []

    for sc in all_sc:
        # contamination detection
        contamination = False
        detail = "CLEAN"

        if sc["scenario_type"] == "RUNTIME_SPLIT_BRAIN":
            # Check: multiple active activations for same release
            acts = sb.table("runtime_activation_registry").select("activation_stage").eq("activation_status", "ACTIVE").execute()
            stages = set(a["activation_stage"] for a in (acts.data or []))
            if len(stages) > 1:
                contamination = True
                detail = f"Split-brain: {stages}"

        elif sc["scenario_type"] == "OBLIGATION_DRIFT_INJECTION":
            drift = sb.table("engine_integrity_event").select("id").eq("event_type", "OBLIGATION_DRIFT_DETECTED").eq("resolved", False).execute()
            if drift.data:
                contamination = True
                detail = f"Obligation drift: {len(drift.data)} unresolved"

        elif sc["scenario_type"] == "COMPLETENESS_CORRUPTION":
            comp = sb.table("engine_integrity_event").select("id").in_("event_type", ["COMPLETENESS_DRIFT_DETECTED", "DOCUMENT_COMPLETENESS_DRIFT"]).eq("resolved", False).execute()
            if comp.data:
                contamination = True
                detail = f"Completeness corruption: {len(comp.data)}"

        results.append({
            "scenario": sc["scenario_code"],
            "type": sc["scenario_type"],
            "contamination_detected": contamination,
            "detail": detail,
            "severity": "CRITICAL" if contamination else "INFO",
        })

    contaminated = sum(1 for r in results if r["contamination_detected"])
    if contaminated > 0:
        sb.table("engine_integrity_event").insert({
            "event_type": "RUNTIME_CONTAMINATION_DETECTED",
            "severity": "CRITICAL",
            "domain": "CHAOS_QA",
            "description": f"Chaos QA: {contaminated}/{len(results)} scenarios contaminated",
            "source_trace": "INTEGRITY_MONITOR",
        }).execute()

    logger.info(f"CHAOS_RUN | total={len(results)} contaminated={contaminated}")
    return {
        "status": "success",
        "total_scenarios": len(results),
        "contaminated": contaminated,
        "clean": len(results) - contaminated,
        "results": results,
        "rollout_allowed": contaminated == 0,
    }


@router.get("/contamination-events")
def list_contamination_events(request: Request):
    _check_admin(request)
    sb = _sb()
    r = sb.table("engine_integrity_event").select("*").in_(
        "event_type", ["RUNTIME_CONTAMINATION_DETECTED", "PARTIAL_ROLLOUT_CORRUPTION",
                       "SNAPSHOT_DIVERGENCE", "ROLLBACK_INCONSISTENCY",
                       "RUNTIME_SPLIT_BRAIN", "STALE_RUNTIME_STATE"]
    ).order("created_at", desc=True).limit(50).execute()
    return {"status": "success", "data": r.data or []}


@router.get("/rollback-latency")
def list_rollback_latency(request: Request):
    _check_admin(request)
    sb = _sb()
    r = sb.table("rollback_latency_log").select("*").order("created_at", desc=True).limit(50).execute()
    return {"status": "success", "data": r.data or []}


@router.get("/tenant-isolation")
def check_tenant_isolation(request: Request):
    """Tenant \uac04 runtime contamination \uac80\uc99d"""
    _check_admin(request)
    sb = _sb()
    # cross-tenant check: activation에서 tenant_id 없이 활성화된 것
    no_tenant = sb.table("runtime_activation_registry").select("id").is_("tenant_id", "null").eq("activation_status", "ACTIVE").execute()
    isolation_ok = len(no_tenant.data or []) == 0
    return {
        "status": "success",
        "tenant_isolation": "PASS" if isolation_ok else "WARNING",
        "activations_without_tenant": len(no_tenant.data or []),
    }


@router.get("/status")
def chaos_status():
    sb = _sb()
    sc = sb.table("runtime_chaos_scenario").select("id").eq("enabled", True).execute()
    return {
        "status": "active",
        "engine": "Runtime Chaos Testing v1.0.0",
        "enabled_scenarios": len(sc.data or []),
        "boundary": "SANDBOX_ONLY",
        "production_destructive": False,
    }
