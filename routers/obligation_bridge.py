"""TAI Obligation Bridge v1.0.0
Phase 2: Obligation Management Runtime Bridge.
Legacy → Runtime 의무 관리 흐름 연결.

금지 패턴: semantic, best_match, inferred, guessed, probable,
          recommend, auto_assign, auto_schedule, auto_complete
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import logging

router = APIRouter(prefix="/bridge", tags=["의무 브릿지"])
logger = logging.getLogger("obligation_bridge")


def _audit_log(action: str, entity: str, entity_id: str, user_id: str = "system"):
    """Runtime audit logging"""
    logger.info(f"OBLIGATION_BRIDGE_AUDIT | action={action} entity={entity} id={entity_id} by={user_id}")


def _get_sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# ═══ Obligation Registry ═══

@router.get("/obligations")
def bridge_list_obligations(
    execution_type: Optional[str] = Query(None),
    activation_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Runtime obligation registry 조회"""
    sb = _get_sb()
    q = sb.table("runtime_obligation_registry").select("*")
    if execution_type:
        q = q.eq("execution_type", execution_type)
    if activation_status:
        q = q.eq("activation_status", activation_status)
    offset = (page - 1) * page_size
    q = q.order("created_at", desc=True).range(offset, offset + page_size - 1)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or [], "page": page}


@router.get("/obligations/{obligation_id}")
def bridge_get_obligation(obligation_id: str):
    """Runtime obligation registry 단건 조회"""
    sb = _get_sb()
    r = sb.table("runtime_obligation_registry").select("*").eq("id", obligation_id).execute()
    if not r.data:
        raise HTTPException(404, "Obligation not found")
    return {"status": "success", "source": "runtime", "data": r.data[0]}


# ═══ Obligation Assignments ═══

@router.get("/obligation-assignments")
def bridge_list_assignments(
    factory_id: Optional[str] = Query(None),
    obligation_registry_id: Optional[str] = Query(None),
    review_status: Optional[str] = Query(None),
):
    """의무별 담당자 지정 목록 조회"""
    sb = _get_sb()
    q = sb.table("runtime_obligation_assignment").select("*")
    if factory_id:
        q = q.eq("factory_id", factory_id)
    if obligation_registry_id:
        q = q.eq("obligation_registry_id", obligation_registry_id)
    if review_status:
        q = q.eq("review_status", review_status)
    q = q.order("created_at", desc=True).limit(100)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


@router.post("/obligation-assignments")
def bridge_create_assignment(
    obligation_registry_id: str = Query(...),
    factory_id: str = Query(...),
    assigned_user_id: str = Query(...),
    assigned_role: str = Query(...),
    assigned_by: str = Query(...),
    assignment_reason: str = Query(...),
):
    """담당자 지정 생성. auto assignment / inferred assignment 금지."""
    sb = _get_sb()

    # lifecycle validation: obligation이 ACTIVE여야 assignment 가능
    obl = sb.table("runtime_obligation_registry").select("activation_status").eq("id", obligation_registry_id).execute()
    if not obl.data:
        raise HTTPException(404, "Obligation not found in registry")
    if obl.data[0]["activation_status"] not in ("ACTIVE", "NEEDS_REVIEW"):
        raise HTTPException(400, f"Cannot assign: obligation status is {obl.data[0]['activation_status']}")

    # orphan prevention: assigned_by must exist
    if not assigned_by or assigned_by == "":
        raise HTTPException(400, "assigned_by is required. Implicit assignment is forbidden.")

    row = {
        "obligation_registry_id": obligation_registry_id,
        "factory_id": factory_id,
        "assigned_user_id": assigned_user_id,
        "assigned_role": assigned_role,
        "assigned_by": assigned_by,
        "assignment_reason": assignment_reason,
        "review_status": "PENDING",
        "source_trace": "MANUAL_INPUT",
    }
    r = sb.table("runtime_obligation_assignment").insert(row).execute()
    _audit_log("CREATE_ASSIGNMENT", "obligation_assignment", r.data[0]["id"], assigned_by)
    return {"status": "success", "source": "runtime", "data": r.data[0]}


# ═══ Obligation Schedule Policies ═══

@router.get("/obligation-schedule-policies")
def bridge_list_schedule_policies(
    obligation_registry_id: Optional[str] = Query(None),
):
    """의무별 반복주기 정책 조회"""
    sb = _get_sb()
    q = sb.table("runtime_obligation_schedule_policy").select("*")
    if obligation_registry_id:
        q = q.eq("obligation_registry_id", obligation_registry_id)
    q = q.order("created_at", desc=True).limit(100)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


@router.post("/obligation-schedule-policies")
def bridge_create_schedule_policy(
    obligation_registry_id: str = Query(...),
    schedule_type: str = Query(...),
    repeat_cycle: Optional[int] = Query(None),
    repeat_unit: Optional[str] = Query(None),
    created_by: str = Query(...),
):
    """반복주기 정책 생성. guessed cycle / inferred repeat 금지."""
    sb = _get_sb()

    # lifecycle validation
    obl = sb.table("runtime_obligation_registry").select("activation_status").eq("id", obligation_registry_id).execute()
    if not obl.data:
        raise HTTPException(404, "Obligation not found in registry")

    if schedule_type == "RECURRING" and (repeat_cycle is None or repeat_unit is None):
        raise HTTPException(400, "RECURRING schedule requires repeat_cycle and repeat_unit")

    row = {
        "obligation_registry_id": obligation_registry_id,
        "schedule_type": schedule_type,
        "repeat_cycle": repeat_cycle,
        "repeat_unit": repeat_unit,
        "source_trace": "MANUAL_INPUT",
    }
    r = sb.table("runtime_obligation_schedule_policy").insert(row).execute()
    _audit_log("CREATE_SCHEDULE_POLICY", "obligation_schedule_policy", r.data[0]["id"], created_by)
    return {"status": "success", "source": "runtime", "data": r.data[0]}


# ═══ Work Orders ═══

@router.get("/work-orders")
def bridge_list_work_orders(
    factory_id: Optional[str] = Query(None),
    execution_type: Optional[str] = Query(None),
    work_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Operational work order 관리자 조회"""
    sb = _get_sb()
    q = sb.table("runtime_operational_work_order").select("*")
    if execution_type:
        q = q.eq("execution_type", execution_type)
    if work_status:
        q = q.eq("work_status", work_status)
    offset = (page - 1) * page_size
    q = q.order("created_at", desc=True).range(offset, offset + page_size - 1)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or [], "page": page}


@router.get("/my-work-orders")
def bridge_my_work_orders(
    user_id: str = Query(...),
    work_status: Optional[str] = Query(None),
):
    """작업자 본인 work order 조회 (작업자 앱용)"""
    sb = _get_sb()
    q = sb.table("runtime_operational_work_order").select("*").eq("assigned_user_id", user_id)
    if work_status:
        q = q.eq("work_status", work_status)
    q = q.order("due_date", desc=False).limit(50)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


# ═══ Bridge Status ═══

@router.get("/obligation-status")
def bridge_obligation_status():
    """Phase 2 Obligation Bridge 상태"""
    return {
        "status": "active",
        "phase": "Phase 2 — Obligation Runtimeization",
        "bridge_routes": [
            "/bridge/obligations",
            "/bridge/obligations/{id}",
            "/bridge/obligation-assignments",
            "/bridge/obligation-schedule-policies",
            "/bridge/work-orders",
            "/bridge/my-work-orders",
        ],
        "forbidden_patterns": [
            "semantic", "best_match", "inferred", "guessed",
            "probable", "recommend", "auto_assign",
            "auto_schedule", "auto_complete",
        ],
    }
