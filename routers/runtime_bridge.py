"""TAI Runtime Bridge v1.0.0
Legacy → Runtime 호환 브릿지.
기존 프론트엔드가 Legacy API를 호출하던 경로를 Runtime으로 연결.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from services import persistence_svc, runtime_evaluator_svc
from services import document_engine_svc

router = APIRouter(prefix="/bridge", tags=["런타임 브릿지"])


# ═══ Schedule Bridge (Legacy work_schedules → Runtime schedule_instance) ═══

@router.get("/schedules")
def bridge_list_schedules(facility_id: Optional[str] = Query(None)):
    """Legacy 일정 조회 → Runtime schedule_instance"""
    from db.supabase_client import get_supabase
    sb = get_supabase()
    q = sb.table("runtime_schedule_instance").select("*")
    if facility_id:
        q = q.eq("facility_id", facility_id)
    q = q.order("created_at", desc=True).limit(100)
    r = q.execute()
    return {"status": "success", "source": "runtime", "data": r.data or []}


@router.post("/schedules")
def bridge_create_schedule(
    facility_id: str = Query(...),
    schedule_type: str = Query(...),
    schedule_key: str = Query(...),
    next_due_date: Optional[str] = Query(None),
):
    """Legacy 일정 생성 → Runtime schedule_instance"""
    try:
        result = persistence_svc.create_schedule_instance(
            facility_id, schedule_type, schedule_key, next_due_date
        )
        return {"status": "success", "source": "runtime", "data": result}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ═══ Document Bridge (Legacy documents → Runtime document_data) ═══

@router.get("/documents")
def bridge_list_documents(
    factory_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Legacy 문서 조회 → Runtime document_data"""
    result = document_engine_svc.list_documents(factory_id, None, status, page, page_size)
    return {"status": "success", "source": "runtime", "data": result}


@router.post("/documents")
def bridge_create_document(
    form_schema_id: str = Query(...),
    factory_id: Optional[str] = Query(None),
    created_by: Optional[str] = Query(None),
):
    """Legacy 문서 생성 → Runtime document_data"""
    try:
        result = document_engine_svc.create_document(form_schema_id, factory_id, None, created_by)
        return {"status": "success", "source": "runtime", "data": result}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ═══ Diagnosis Bridge (Legacy diagnosis → Runtime evaluator) ═══

@router.post("/diagnosis/evaluate")
def bridge_evaluate(
    facility_id: str = Query(...),
    industry_code: Optional[str] = Query(None),
    worker_count: Optional[int] = Query(None),
):
    """Legacy 진단 → Runtime evaluator (deterministic only)"""
    try:
        ctx = runtime_evaluator_svc.create_context({
            "facility_id": facility_id,
            "industry_code": industry_code,
            "worker_count": worker_count,
            "created_by": "bridge",
        })
        result = runtime_evaluator_svc.evaluate(ctx["id"])
        return {"status": "success", "source": "runtime", "data": result}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ═══ Health: 브릿지 상태 확인 ═══

@router.get("/status")
def bridge_status():
    """Bridge 상태 확인"""
    return {
        "status": "active",
        "phase": "Phase 1",
        "frozen_legacy": ["schedule_engine", "diagnosis_autofill", "documents_crud"],
        "runtime_active": ["schedule_instance", "document_engine", "diagnosis_engine", "runtime_evaluator"],
        "bridge_routes": ["/bridge/schedules", "/bridge/documents", "/bridge/diagnosis/evaluate"],
    }
