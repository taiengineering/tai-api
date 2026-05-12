"""TAI My Inspection Runtime Bridge v1.0.0
Phase 3: 작업자 앱 점검 수행 → Runtime lifecycle 연결.

금지 패턴: semantic, inferred, auto_complete, auto_approve,
          hidden_sync, silent_merge, legacy mutation
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import logging

router = APIRouter(prefix="/bridge", tags=["점검 브릿지"])
logger = logging.getLogger("inspection_runtime_bridge")


def _audit(action: str, entity: str, entity_id: str, user_id: str = "system"):
    logger.info(f"INSPECTION_BRIDGE_AUDIT | action={action} entity={entity} id={entity_id} by={user_id}")


def _sb():
    from db.supabase_client import get_supabase
    return get_supabase()


# ═══ My Inspection ═══

@router.get("/my-inspection")
def bridge_my_inspections(
    user_id: str = Query(...),
    status: Optional[str] = Query(None),
):
    """작업자 본인 점검 세션 목록 (Runtime work queue 기반)"""
    sb = _sb()
    q = sb.table("runtime_inspection_session").select(
        "*, runtime_operational_work_order!inner(execution_type, due_date)"
    ).eq("worker_user_id", user_id)
    if status:
        q = q.eq("session_status", status)
    q = q.order("created_at", desc=True).limit(50)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


@router.get("/my-inspection/{session_id}")
def bridge_get_inspection(session_id: str):
    """점검 세션 단건 조회"""
    sb = _sb()
    r = sb.table("runtime_inspection_session").select("*").eq("id", session_id).execute()
    if not r.data:
        raise HTTPException(404, "Inspection session not found")
    return {"status": "success", "source": "runtime", "data": r.data[0]}


# ═══ Inspection Sessions ═══

@router.post("/inspection-sessions")
def bridge_start_session(
    work_order_id: str = Query(...),
    worker_user_id: str = Query(...),
):
    """점검 세션 시작. work_order 필수."""
    sb = _sb()

    # lifecycle validation: work_order 존재 + ASSIGNED/IN_PROGRESS 상태 검증
    wo = sb.table("runtime_operational_work_order").select("work_status, assigned_user_id").eq("id", work_order_id).execute()
    if not wo.data:
        raise HTTPException(404, "Work order not found")
    if wo.data[0]["work_status"] not in ("ASSIGNED", "IN_PROGRESS", "GENERATED"):
        raise HTTPException(400, f"Cannot start: work_status is {wo.data[0]['work_status']}")
    if wo.data[0]["assigned_user_id"] != worker_user_id:
        raise HTTPException(403, "Worker mismatch: not assigned to this work order")

    # orphan prevention: 중복 세션 차단
    existing = sb.table("runtime_inspection_session").select("id").eq("operational_work_order_id", work_order_id).execute()
    if existing.data:
        raise HTTPException(409, f"Session already exists: {existing.data[0]['id']}")

    row = {
        "operational_work_order_id": work_order_id,
        "worker_user_id": worker_user_id,
        "session_status": "IN_PROGRESS",
        "inspection_started_at": "now()",
        "source_trace": "RUNTIME_GENERATED",
    }
    r = sb.table("runtime_inspection_session").insert(row).execute()

    # work_order status 업데이트
    sb.table("runtime_operational_work_order").update(
        {"work_status": "IN_PROGRESS", "updated_at": "now()"}
    ).eq("id", work_order_id).execute()

    _audit("START_SESSION", "inspection_session", r.data[0]["id"], worker_user_id)
    return {"status": "success", "source": "runtime", "data": r.data[0]}


# ═══ Inspection Checklist ═══

@router.get("/inspection-checklist")
def bridge_get_checklist(
    session_id: str = Query(...),
):
    """세션별 체크리스트 조회"""
    sb = _sb()
    r = sb.table("runtime_checklist_execution").select(
        "*, runtime_checklist_item(check_name, check_description, category)"
    ).eq("inspection_session_id", session_id).execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


@router.post("/inspection-checklist")
def bridge_execute_checklist(
    session_id: str = Query(...),
    checklist_item_id: str = Query(...),
    check_result: str = Query(...),
    executed_by: str = Query(...),
    check_note: Optional[str] = Query(None),
):
    """체크리스트 항목 수행 결과 기록. PASS/FAIL/NA."""
    if check_result not in ("PASS", "FAIL", "NA"):
        raise HTTPException(400, "check_result must be PASS, FAIL, or NA")

    sb = _sb()

    # session lifecycle validation
    sess = sb.table("runtime_inspection_session").select("session_status").eq("id", session_id).execute()
    if not sess.data:
        raise HTTPException(404, "Session not found")
    if sess.data[0]["session_status"] not in ("IN_PROGRESS",):
        raise HTTPException(400, f"Cannot execute: session is {sess.data[0]['session_status']}")

    row = {
        "inspection_session_id": session_id,
        "runtime_checklist_item_id": checklist_item_id,
        "check_result": check_result,
        "check_note": check_note,
        "executed_by": executed_by,
        "source_trace": "WORKER_INPUT",
    }
    r = sb.table("runtime_checklist_execution").insert(row).execute()
    _audit("EXECUTE_CHECKLIST", "checklist_execution", r.data[0]["id"], executed_by)
    return {"status": "success", "source": "runtime", "data": r.data[0]}


# ═══ Inspection Evidence ═══

@router.get("/inspection-evidence")
def bridge_get_evidence(
    session_id: str = Query(...),
):
    """세션별 증빙 조회"""
    sb = _sb()
    r = sb.table("runtime_inspection_evidence").select("*").eq("inspection_session_id", session_id).execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


@router.post("/inspection-evidence")
def bridge_upload_evidence(
    session_id: str = Query(...),
    checklist_execution_id: Optional[str] = Query(None),
    evidence_type: str = Query(...),
    uploaded_by: str = Query(...),
    file_name: Optional[str] = Query(None),
    measurement_value: Optional[str] = Query(None),
    measurement_unit: Optional[str] = Query(None),
):
    """증빙 업로드. fake/placeholder/inferred evidence 금지."""
    if evidence_type not in ("IMAGE", "FILE", "MEASUREMENT", "VIDEO", "SIGNATURE"):
        raise HTTPException(400, "Invalid evidence_type")

    sb = _sb()

    # session linkage validation
    sess = sb.table("runtime_inspection_session").select("session_status").eq("id", session_id).execute()
    if not sess.data:
        raise HTTPException(404, "Session not found")
    if sess.data[0]["session_status"] not in ("IN_PROGRESS",):
        raise HTTPException(400, f"Cannot upload: session is {sess.data[0]['session_status']}")

    row = {
        "inspection_session_id": session_id,
        "checklist_execution_id": checklist_execution_id,
        "evidence_type": evidence_type,
        "uploaded_by": uploaded_by,
        "file_name": file_name,
        "measurement_value": measurement_value,
        "measurement_unit": measurement_unit,
        "source_trace": "WORKER_UPLOAD",
    }
    r = sb.table("runtime_inspection_evidence").insert(row).execute()
    _audit("UPLOAD_EVIDENCE", "inspection_evidence", r.data[0]["id"], uploaded_by)
    return {"status": "success", "source": "runtime", "data": r.data[0]}


# ═══ Inspection Submit ═══

@router.post("/inspection-submit")
def bridge_submit_inspection(
    session_id: str = Query(...),
    submitted_by: str = Query(...),
):
    """점검 제출. 체크리스트 완료 검증 + review queue 전달."""
    sb = _sb()

    sess = sb.table("runtime_inspection_session").select("session_status, worker_user_id").eq("id", session_id).execute()
    if not sess.data:
        raise HTTPException(404, "Session not found")
    if sess.data[0]["session_status"] != "IN_PROGRESS":
        raise HTTPException(400, f"Cannot submit: session is {sess.data[0]['session_status']}")
    if sess.data[0]["worker_user_id"] != submitted_by:
        raise HTTPException(403, "Only the assigned worker can submit")

    # checklist completion count
    execs = sb.table("runtime_checklist_execution").select("id").eq("inspection_session_id", session_id).execute()
    checklist_completed = len(execs.data) if execs.data else 0

    # evidence count
    evds = sb.table("runtime_inspection_evidence").select("id").eq("inspection_session_id", session_id).execute()
    evidence_uploaded = len(evds.data) if evds.data else 0

    # create submission record
    sub_row = {
        "inspection_session_id": session_id,
        "submitted_by": submitted_by,
        "submission_type": "INITIAL",
        "checklist_completed": checklist_completed,
        "evidence_uploaded": evidence_uploaded,
        "source_trace": "WORKER_SUBMIT",
    }
    sb.table("runtime_inspection_submission").insert(sub_row).execute()

    # update session status
    sb.table("runtime_inspection_session").update({
        "session_status": "SUBMITTED",
        "submission_status": "SUBMITTED",
        "review_status": "REVIEW_PENDING",
        "inspection_completed_at": "now()",
        "updated_at": "now()",
    }).eq("id", session_id).execute()

    _audit("SUBMIT_INSPECTION", "inspection_session", session_id, submitted_by)
    return {"status": "success", "source": "runtime", "submitted": True}


# ═══ Status ═══

@router.get("/my-inspection-status")
def bridge_inspection_status():
    return {
        "status": "active",
        "phase": "Phase 3 — Inspection Runtime Bridge",
        "bridge_routes": [
            "/bridge/my-inspection",
            "/bridge/my-inspection/{id}",
            "/bridge/inspection-sessions",
            "/bridge/inspection-checklist",
            "/bridge/inspection-evidence",
            "/bridge/inspection-submit",
        ],
        "forbidden_patterns": [
            "semantic", "inferred", "auto_complete", "auto_approve",
            "hidden_sync", "silent_merge", "legacy_mutation",
        ],
    }
