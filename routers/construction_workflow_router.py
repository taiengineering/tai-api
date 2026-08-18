import re
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


def _alias_inspection_row(row: dict) -> dict:
    """화면 계약 호환(LEDGER §62 표시분): DB 컬럼명에 화면이 읽는 별칭을 병기(원본 유지).
    목록은 item.inspection_datetime 을, 상세는 defect_details·corrective_due 를 읽어
    값이 있어도 '-'/created_at 으로 떨어지던 것을 해소한다.
    ※ inspector_name(이름) 은 inspector_id(uuid)에서 채울 수 없어 여기서 다루지 않는다(결정 대기)."""
    if not isinstance(row, dict):
        return row
    if row.get("inspection_datetime") is None and row.get("inspection_date") is not None:
        row["inspection_datetime"] = row.get("inspection_date")
    if row.get("defect_details") is None and row.get("defect_items") is not None:
        row["defect_details"] = row.get("defect_items")
    if row.get("corrective_due") is None and row.get("corrective_deadline") is not None:
        row["corrective_due"] = row.get("corrective_deadline")
    return row


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


def _iso_date(v) -> Optional[str]:
    """date 객체면 ISO 문자열로, 그 외(str/None)는 그대로."""
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


@router.post("/sites/{site_id}/workers")
async def create_worker(site_id: str, body: WorkerCreate):
    """건설 작업자 등록 — 통합 명부(worker_registry) + 현장배치(construction_workers) 동시 생성.

    LEDGER §19: 종전에는 construction_workers 에만 직접 써서 화면 8필드가 버려지고, org
    (부서·팀·그룹)·리더 체계에서 이탈했다. 실측상 org 배정·리더는 worker_registry.id 를
    기준점으로 하고(worker_group·groups.lead_worker_id·teams.lead_worker_id FK),
    construction_workers 는 worker_registry_id 로 명부와 연결된다(기존 데이터 전원 연결·
    worker_registry.factory_id=NULL·company 스코프). 그 선례대로:
      1) worker_registry 명부 생성(factory_id=NULL, company 스코프) — org·리더 편입 가능
      2) construction_workers 현장배치 생성(worker_registry_id 연결 + 건설 특화: 고용형태·
         안전교육·출입상태)
    실패 시 명부 고아를 남기지 않도록 보상 삭제한다.
    """
    site_id = _validate_uuid(site_id)
    supabase = get_supabase()

    name = (body.worker_name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="이름은 필수입니다.")

    # site → company_id (worker_registry 는 factory_id 없이 company 스코프로 담는다)
    site = supabase.table("construction_sites").select("company_id").eq("id", site_id).single().execute()
    if not site.data:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")
    company_id = site.data.get("company_id")

    phone = re.sub(r"[^0-9]", "", body.phone or "") or None
    job_label = (body.job_type or "").strip() or None
    contractor = (body.company_name or "").strip() or None
    memo = (body.memo or "").strip() or None
    hire = _iso_date(body.hire_date)
    now = _now_iso()

    # 1) 통합 명부(worker_registry) — factory_id=NULL, company 스코프 (실측 선례)
    reg_payload = {
        "company_id":      company_id,
        "factory_id":      None,
        "name":            name,
        "phone":           phone,
        "job_type_code":   job_label,
        "job_type_name":   job_label,
        "contractor_name": contractor,
        "start_date":      hire,
        "memo":            memo,
        "is_active":       True,
        "status_code":     "ACTIVE",
        "created_at":      now,
        "updated_at":      now,
    }
    reg_payload = {k: v for k, v in reg_payload.items() if v is not None}
    try:
        reg = supabase.table("worker_registry").insert(reg_payload).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"작업자 명부 등록 실패: {e}")
    if not reg.data:
        raise HTTPException(status_code=500, detail="작업자 명부 등록 실패")
    worker_registry_id = reg.data[0]["id"]

    # 2) 현장배치(construction_workers) — 명부 연결 + 건설 특화(고용형태·안전교육·출입)
    edu_hours = int(body.safety_training_hours) if body.safety_training_hours is not None else None
    cw_payload = {
        "site_id":            site_id,
        "worker_registry_id": worker_registry_id,
        "worker_name":        name,
        "worker_phone":       phone,
        "worker_type":        body.worker_type,
        "join_date":          hire,
        "safety_edu_date":    _iso_date(body.safety_training_date),
        "safety_edu_hours":   edu_hours,
        "entry_status":       body.entry_status,
        "notes":              memo,
        "is_active":          True,
        "created_at":         now,
        "updated_at":         now,
    }
    cw_payload = {k: v for k, v in cw_payload.items() if v is not None}
    try:
        res = supabase.table("construction_workers").insert(cw_payload).execute()
        if not res.data:
            raise Exception("현장 배치 저장 결과가 비어 있습니다.")
    except Exception as e:
        # 보상: 명부 고아 방지
        try:
            supabase.table("worker_registry").delete().eq("id", worker_registry_id).execute()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"현장 배치 등록 실패: {e}")

    return {"status": "success", "data": res.data[0]}


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
        data["items"] = [_alias_inspection_row(r) for r in data.get("items", [])]
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
        return {"status": "success", "data": _alias_inspection_row(inspection)}
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
    return {"status": "success", "data": _alias_inspection_row(row)}


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
        return {"status": "success", "data": _alias_inspection_row(updated)}
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
    return {"status": "success", "data": _alias_inspection_row(res.data[0])}


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
