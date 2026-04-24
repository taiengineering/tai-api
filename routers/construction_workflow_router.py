import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from db.supabase_client import get_supabase
from schemas.construction import (
    CorrectivePatch,
    EntryPatch,
    InspectionCreate,
    InspectionPatch,
    ProcessCreate,
    ProcessPatch,
    PtwPatch,
    SafetyManagerBody,
    WorkCreate,
    WorkPatch,
    WorkerCreate,
    WorkerPatch,
)
from services.construction_helpers import calc_safety_manager
from services.construction_status_svc import (
    build_corrective_update_payload,
    build_entry_update_payload,
    build_ptw_update_payload,
)
from services.construction_svc import (
    create_record,
    get_record_or_none,
    normalize_date_fields,
    prepare_inspection_payload,
    run_list_query,
    send_fcm_inspection_alert,
    soft_delete_record,
    update_record,
)

router = APIRouter(tags=["건설안전"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_uuid(value: str) -> str:
    try:
        uuid.UUID(value)
        return value
    except ValueError:
        raise HTTPException(status_code=400, detail="유효하지 않은 ID 형식입니다.")


def _ptw_number(site_id: str, supabase) -> str:
    year = datetime.now().year
    res = supabase.table("construction_works").select("id", count="exact").eq("site_id", site_id).execute()
    seq = (res.count or 0) + 1
    return f"CS-{year}-{seq:05d}"


@router.get("/sites/{site_id}/processes")
async def list_processes(
    site_id: str,
    status_code: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        data = run_list_query(
            supabase,
            "construction_site_processes",
            {"site_id": site_id, "is_active": True, "status_code": status_code},
            page,
            size,
            ["sort_order", "created_at"],
        )
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/processes")
async def create_process(site_id: str, body: ProcessCreate):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        data["site_id"] = site_id
        data = normalize_date_fields(data, ("planned_start", "planned_end"))
        created = create_record(supabase, "construction_site_processes", data, _now_iso, "등록 실패")
        return {"status": "success", "data": created}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/processes/{process_id}")
async def get_process(process_id: str):
    supabase = get_supabase()
    row = get_record_or_none(supabase, "construction_site_processes", process_id)
    if not row:
        raise HTTPException(status_code=404, detail="공정을 찾을 수 없습니다.")
    return {"status": "success", "data": row}


@router.patch("/processes/{process_id}")
async def update_process(process_id: str, body: ProcessPatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        data = normalize_date_fields(data, ("planned_start", "planned_end", "actual_start", "actual_end"))
        updated = update_record(supabase, "construction_site_processes", process_id, data, _now_iso)
        if not updated:
            raise HTTPException(status_code=404, detail="공정을 찾을 수 없습니다.")
        return {"status": "success", "data": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/processes/{process_id}")
async def delete_process(process_id: str):
    supabase = get_supabase()
    deleted = soft_delete_record(supabase, "construction_site_processes", process_id, _now_iso)
    if not deleted:
        raise HTTPException(status_code=404, detail="공정을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


@router.get("/sites/{site_id}/works")
async def list_works(
    site_id: str,
    status_code: Optional[str] = Query(None),
    ptw_status: Optional[str] = Query(None),
    work_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        data = run_list_query(
            supabase,
            "construction_works",
            {"site_id": site_id, "is_active": True, "status_code": status_code, "ptw_status": ptw_status, "work_date": work_date},
            page,
            size,
            [("work_date", True), ("created_at", True)],
        )
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/works")
async def create_work(site_id: str, body: WorkCreate):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        data["site_id"] = site_id
        data = normalize_date_fields(data, ("work_date",))
        data["ptw_number"] = _ptw_number(site_id, supabase)
        data["ptw_status"] = "DRAFT"
        created = create_record(supabase, "construction_works", data, _now_iso, "등록 실패")
        return {"status": "success", "data": created}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/works/{work_id}")
async def get_work(work_id: str):
    supabase = get_supabase()
    row = get_record_or_none(supabase, "construction_works", work_id)
    if not row:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {"status": "success", "data": row}


@router.patch("/works/{work_id}")
async def update_work(work_id: str, body: WorkPatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        data = normalize_date_fields(data, ("work_date",))
        updated = update_record(supabase, "construction_works", work_id, data, _now_iso)
        if not updated:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
        return {"status": "success", "data": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/works/{work_id}/ptw")
async def update_ptw(work_id: str, body: PtwPatch):
    supabase = get_supabase()
    try:
        data = build_ptw_update_payload(body, _now_iso)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    res = supabase.table("construction_works").update(data).eq("id", work_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.delete("/works/{work_id}")
async def delete_work(work_id: str):
    supabase = get_supabase()
    deleted = soft_delete_record(supabase, "construction_works", work_id, _now_iso)
    if not deleted:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


@router.get("/sites/{site_id}/workers")
async def list_workers(
    site_id: str,
    worker_type: Optional[str] = Query(None),
    entry_status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        data = run_list_query(
            supabase,
            "construction_workers",
            {
                "site_id": site_id,
                "is_active": True,
                "worker_type": worker_type,
                "entry_status": entry_status,
                "worker_name__ilike": f"%{search}%" if search else None,
            },
            page,
            size,
            [("created_at", True)],
        )
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/workers")
async def create_worker(site_id: str, body: WorkerCreate):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        data["site_id"] = site_id
        data = normalize_date_fields(data, ("join_date", "safety_edu_date"))
        created = create_record(supabase, "construction_workers", data, _now_iso, "등록 실패")
        return {"status": "success", "data": created}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workers/{worker_id}")
async def get_worker(worker_id: str):
    supabase = get_supabase()
    row = get_record_or_none(supabase, "construction_workers", worker_id)
    if not row:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
    return {"status": "success", "data": row}


@router.patch("/workers/{worker_id}")
async def update_worker(worker_id: str, body: WorkerPatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        data = normalize_date_fields(data, ("join_date", "leave_date", "health_check_date", "safety_edu_date"))
        updated = update_record(supabase, "construction_workers", worker_id, data, _now_iso)
        if not updated:
            raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
        return {"status": "success", "data": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/workers/{worker_id}/entry")
async def update_entry(worker_id: str, body: EntryPatch):
    supabase = get_supabase()
    try:
        data = build_entry_update_payload(body, _now_iso)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    res = supabase.table("construction_workers").update(data).eq("id", worker_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.delete("/workers/{worker_id}")
async def delete_worker(worker_id: str):
    supabase = get_supabase()
    deleted = soft_delete_record(supabase, "construction_workers", worker_id, _now_iso)
    if not deleted:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


@router.get("/sites/{site_id}/inspections")
async def list_inspections(
    site_id: str,
    inspection_type: Optional[str] = Query(None),
    overall_result: Optional[str] = Query(None),
    corrective_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        data = run_list_query(
            supabase,
            "construction_inspections",
            {
                "site_id": site_id,
                "is_active": True,
                "inspection_type": inspection_type,
                "overall_result": overall_result,
                "corrective_status": corrective_status,
            },
            page,
            size,
            [("inspection_date", True)],
        )
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/inspections")
async def create_inspection(site_id: str, body: InspectionCreate):
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()
    try:
        data = prepare_inspection_payload(body.model_dump(exclude_none=True), _now_iso)
        data["site_id"] = site_id
        res = supabase.table("construction_inspections").insert(data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="등록 실패")
        inspection = res.data[0]
        if data.get("overall_result") in ("FAIL", "ISSUE") and data.get("defect_count", 0) > 0:
            await send_fcm_inspection_alert(supabase, site_id=site_id, inspection_id=inspection["id"], defect_count=data.get("defect_count", 1))
        return {"status": "success", "data": inspection}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inspections/{inspection_id}")
async def get_inspection(inspection_id: str):
    supabase = get_supabase()
    row = get_record_or_none(supabase, "construction_inspections", inspection_id)
    if not row:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다.")
    return {"status": "success", "data": row}


@router.patch("/inspections/{inspection_id}")
async def update_inspection(inspection_id: str, body: InspectionPatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        data = normalize_date_fields(data, ("corrective_deadline",))
        updated = update_record(supabase, "construction_inspections", inspection_id, data, _now_iso)
        if not updated:
            raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다.")
        return {"status": "success", "data": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/inspections/{inspection_id}/corrective")
async def update_corrective(inspection_id: str, body: CorrectivePatch):
    supabase = get_supabase()
    try:
        data = build_corrective_update_payload(body, _now_iso)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    res = supabase.table("construction_inspections").update(data).eq("id", inspection_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.delete("/inspections/{inspection_id}")
async def delete_inspection(inspection_id: str):
    supabase = get_supabase()
    deleted = soft_delete_record(supabase, "construction_inspections", inspection_id, _now_iso)
    if not deleted:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


@router.post("/engine/safety-manager")
async def engine_safety_manager(body: SafetyManagerBody):
    return {"status": "success", "data": calc_safety_manager(body.site_type, body.contract_amount, body.total_workers)}
