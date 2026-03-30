"""
건설안전 관리 라우터 — v1.0.0
=====================================
v1.0.0: 신규 생성
  - 건설현장 CRUD + 통계
  - 현장 공정(KCSC 연동) CRUD
  - 위험작업/PTW CRUD
  - 작업자 배치/출입 관리
  - 안전점검/시정조치
  - 안전관리자 선임 의무 자동 판정 엔진 (산안법 시행령 제16조)
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Any, Dict, List
from datetime import datetime, date, timezone

from db.supabase_client import get_supabase

router = APIRouter(tags=["건설안전"])

VERSION = "1.0.0"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ptw_number(site_id: str, supabase) -> str:
    """CS-{YYYY}-{5자리 순번} 자동채번"""
    year = datetime.now().year
    res = supabase.table("construction_works") \
        .select("id", count="exact") \
        .eq("site_id", site_id) \
        .execute()
    seq = (res.count or 0) + 1
    return f"CS-{year}-{seq:05d}"


# ──────────────────────────────────────────────
# 안전관리자 선임 의무 판정 엔진
# ──────────────────────────────────────────────

def calc_safety_manager(site_type: str, contract_amount: float, total_workers: int) -> Dict[str, Any]:
    """
    산안법 시행령 제16조 기준
    - 건축(BUILDING): 도급금액 >= 150억 → 선임 의무
    - 토목(CIVIL):    도급금액 >= 120억 → 선임 의무
    - 상시 근로자(하도급 포함) >= 50명 → 선임 의무 (도급금액 무관)
    """
    required = False
    count = 0
    reasons = []

    if site_type == "BUILDING" and contract_amount >= 150:
        required = True
        count = max(1, int(contract_amount // 150))
        reasons.append(f"건축 도급금액 {contract_amount}억 ≥ 150억 (시행령 제16조①1호가목)")
    elif site_type == "CIVIL" and contract_amount >= 120:
        required = True
        count = max(1, int(contract_amount // 120))
        reasons.append(f"토목 도급금액 {contract_amount}억 ≥ 120억 (시행령 제16조①1호나목)")

    if total_workers >= 50:
        required = True
        count = max(count, 1)
        reasons.append(f"상시 근로자(하도급 포함) {total_workers}명 ≥ 50명 (시행령 제16조③)")

    return {
        "required": required,
        "count": count,
        "reasons": reasons,
        "site_type": site_type,
        "contract_amount": contract_amount,
        "total_workers": total_workers,
    }


# ══════════════════════════════════════════════
# Pydantic 모델
# ══════════════════════════════════════════════

class SiteCreate(BaseModel):
    company_id: str
    site_name: str
    site_code: Optional[str] = None
    site_type: str = "BUILDING"
    contract_amount: Optional[float] = None
    total_workers: Optional[int] = 0
    direct_workers: Optional[int] = 0
    subcon_workers: Optional[int] = 0
    site_address: Optional[str] = None
    site_address_detail: Optional[str] = None
    site_sido: Optional[str] = None
    site_sigungu: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    manager_id: Optional[str] = None
    status_code: Optional[str] = "PLANNED"
    notes: Optional[str] = None


class SitePatch(BaseModel):
    site_name: Optional[str] = None
    site_type: Optional[str] = None
    contract_amount: Optional[float] = None
    total_workers: Optional[int] = None
    direct_workers: Optional[int] = None
    subcon_workers: Optional[int] = None
    site_address: Optional[str] = None
    site_address_detail: Optional[str] = None
    site_sido: Optional[str] = None
    site_sigungu: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    manager_id: Optional[str] = None
    status_code: Optional[str] = None
    notes: Optional[str] = None


class ProcessCreate(BaseModel):
    process_master_id: Optional[str] = None
    process_name: str
    construction_type: Optional[str] = None
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    worker_count: Optional[int] = 0
    is_high_risk: Optional[bool] = False
    sort_order: Optional[int] = 0
    notes: Optional[str] = None


class ProcessPatch(BaseModel):
    process_name: Optional[str] = None
    planned_start: Optional[date] = None
    planned_end: Optional[date] = None
    actual_start: Optional[date] = None
    actual_end: Optional[date] = None
    progress_rate: Optional[int] = None
    worker_count: Optional[int] = None
    is_high_risk: Optional[bool] = None
    status_code: Optional[str] = None
    sort_order: Optional[int] = None
    notes: Optional[str] = None


class WorkCreate(BaseModel):
    process_id: Optional[str] = None
    work_master_id: Optional[str] = None
    work_name: str
    work_date: date
    work_time_start: Optional[str] = None
    work_time_end: Optional[str] = None
    work_location: Optional[str] = None
    assigned_manager_id: Optional[str] = None
    subcontractor_id: Optional[str] = None
    special_work_type: Optional[str] = None
    hazard_codes: Optional[str] = None
    ppe_required: Optional[str] = None
    worker_count: Optional[int] = 0
    notes: Optional[str] = None


class WorkPatch(BaseModel):
    work_name: Optional[str] = None
    work_date: Optional[date] = None
    work_time_start: Optional[str] = None
    work_time_end: Optional[str] = None
    work_location: Optional[str] = None
    assigned_manager_id: Optional[str] = None
    subcontractor_id: Optional[str] = None
    special_work_type: Optional[str] = None
    hazard_codes: Optional[str] = None
    ppe_required: Optional[str] = None
    worker_count: Optional[int] = None
    status_code: Optional[str] = None
    notes: Optional[str] = None


class PtwPatch(BaseModel):
    ptw_status: str  # APPROVED / REJECTED / CLOSED
    ptw_approved_by: Optional[str] = None


class WorkerCreate(BaseModel):
    user_id: Optional[str] = None
    worker_name: Optional[str] = None
    worker_phone: Optional[str] = None
    worker_type: Optional[str] = "SUBCON"
    subcontractor_id: Optional[str] = None
    role_code: Optional[str] = None
    join_date: Optional[date] = None
    certification_codes: Optional[str] = None
    safety_edu_date: Optional[date] = None
    safety_edu_hours: Optional[int] = 0
    notes: Optional[str] = None


class WorkerPatch(BaseModel):
    worker_name: Optional[str] = None
    worker_phone: Optional[str] = None
    worker_type: Optional[str] = None
    subcontractor_id: Optional[str] = None
    role_code: Optional[str] = None
    join_date: Optional[date] = None
    leave_date: Optional[date] = None
    certification_codes: Optional[str] = None
    health_check_date: Optional[date] = None
    health_check_result: Optional[str] = None
    safety_edu_date: Optional[date] = None
    safety_edu_hours: Optional[int] = None
    notes: Optional[str] = None


class EntryPatch(BaseModel):
    entry_status: str  # IN / OUT / OFFSITE


class InspectionCreate(BaseModel):
    work_id: Optional[str] = None
    process_id: Optional[str] = None
    inspection_date: Optional[datetime] = None
    inspector_id: Optional[str] = None
    inspection_type: Optional[str] = "BEFORE_WORK"
    checklist_items: Optional[Any] = None
    overall_result: Optional[str] = None
    defect_count: Optional[int] = 0
    defect_items: Optional[Any] = None
    corrective_action: Optional[str] = None
    corrective_deadline: Optional[date] = None
    photo_urls: Optional[List[str]] = None
    notes: Optional[str] = None


class InspectionPatch(BaseModel):
    inspection_type: Optional[str] = None
    checklist_items: Optional[Any] = None
    overall_result: Optional[str] = None
    defect_count: Optional[int] = None
    defect_items: Optional[Any] = None
    corrective_action: Optional[str] = None
    corrective_deadline: Optional[date] = None
    photo_urls: Optional[List[str]] = None
    notes: Optional[str] = None


class CorrectivePatch(BaseModel):
    corrective_status: str  # IN_PROGRESS / DONE
    corrective_action: Optional[str] = None


class SafetyManagerBody(BaseModel):
    site_type: str
    contract_amount: float
    total_workers: int


# ══════════════════════════════════════════════
# ① 건설현장 (Sites)
# ══════════════════════════════════════════════

@router.get("/sites")
async def list_sites(
    company_id: Optional[str] = Query(None),
    status_code: Optional[str] = Query(None),
    site_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        offset = (page - 1) * size
        q = supabase.table("construction_sites").select("*", count="exact").eq("is_active", True)
        if company_id:   q = q.eq("company_id", company_id)
        if status_code:  q = q.eq("status_code", status_code)
        if site_type:    q = q.eq("site_type", site_type)
        if search:       q = q.ilike("site_name", f"%{search}%")
        q = q.order("created_at", desc=True).range(offset, offset + size - 1)
        res = q.execute()
        return {"status": "success", "data": {
            "items": res.data or [], "total": res.count or 0, "page": page, "size": size,
            "total_pages": ((res.count or 0) + size - 1) // size if res.count else 0,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites")
async def create_site(body: SiteCreate):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        for key in ("start_date", "end_date"):
            if key in data and isinstance(data[key], date):
                data[key] = data[key].isoformat()
        # 안전관리자 선임 의무 자동 판정
        if body.contract_amount is not None:
            sm = calc_safety_manager(
                body.site_type,
                float(body.contract_amount),
                body.total_workers or 0,
            )
            data["safety_manager_required"] = sm["required"]
            data["safety_manager_count"] = sm["count"]
        data["created_at"] = _now_iso()
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_sites").insert(data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="등록 실패")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sites/{site_id}")
async def get_site(site_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_sites").select("*").eq("id", site_id).eq("is_active", True).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.patch("/sites/{site_id}")
async def update_site(site_id: str, body: SitePatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        for key in ("start_date", "end_date"):
            if key in data and isinstance(data[key], date):
                data[key] = data[key].isoformat()
        # 안전관리자 재판정 (금액/인원 변경 시)
        if "contract_amount" in data or "total_workers" in data or "site_type" in data:
            site_res = supabase.table("construction_sites").select("site_type,contract_amount,total_workers").eq("id", site_id).limit(1).execute()
            if site_res.data:
                cur = site_res.data[0]
                sm = calc_safety_manager(
                    data.get("site_type", cur.get("site_type", "BUILDING")),
                    float(data.get("contract_amount", cur.get("contract_amount") or 0)),
                    int(data.get("total_workers", cur.get("total_workers") or 0)),
                )
                data["safety_manager_required"] = sm["required"]
                data["safety_manager_count"] = sm["count"]
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_sites").update(data).eq("id", site_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sites/{site_id}")
async def delete_site(site_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_sites").update({"is_active": False, "updated_at": _now_iso()}).eq("id", site_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


@router.get("/sites/{site_id}/stats")
async def get_site_stats(site_id: str):
    supabase = get_supabase()
    try:
        site_res = supabase.table("construction_sites").select("*").eq("id", site_id).limit(1).execute()
        if not site_res.data:
            raise HTTPException(status_code=404, detail="현장을 찾을 수 없습니다.")
        site = site_res.data[0]

        proc_res = supabase.table("construction_site_processes").select("id,status_code", count="exact").eq("site_id", site_id).eq("is_active", True).execute()
        work_res = supabase.table("construction_works").select("id,status_code,ptw_status", count="exact").eq("site_id", site_id).eq("is_active", True).execute()
        worker_res = supabase.table("construction_workers").select("id,worker_type,entry_status", count="exact").eq("site_id", site_id).eq("is_active", True).execute()
        insp_res = supabase.table("construction_inspections").select("id,overall_result", count="exact").eq("site_id", site_id).eq("is_active", True).execute()

        procs = proc_res.data or []
        works = work_res.data or []
        workers = worker_res.data or []
        insps = insp_res.data or []

        return {"status": "success", "data": {
            "site_id": site_id,
            "site_name": site.get("site_name"),
            "safety_manager_required": site.get("safety_manager_required"),
            "safety_manager_count": site.get("safety_manager_count"),
            "processes": {
                "total": len(procs),
                "in_progress": sum(1 for p in procs if p.get("status_code") == "IN_PROGRESS"),
                "done": sum(1 for p in procs if p.get("status_code") == "DONE"),
            },
            "works": {
                "total": len(works),
                "scheduled": sum(1 for w in works if w.get("status_code") == "SCHEDULED"),
                "in_progress": sum(1 for w in works if w.get("status_code") == "IN_PROGRESS"),
                "ptw_pending": sum(1 for w in works if w.get("ptw_status") == "DRAFT"),
                "ptw_approved": sum(1 for w in works if w.get("ptw_status") == "APPROVED"),
            },
            "workers": {
                "total": len(workers),
                "direct": sum(1 for w in workers if w.get("worker_type") == "DIRECT"),
                "subcon": sum(1 for w in workers if w.get("worker_type") == "SUBCON"),
                "on_site": sum(1 for w in workers if w.get("entry_status") == "IN"),
            },
            "inspections": {
                "total": len(insps),
                "pass": sum(1 for i in insps if i.get("overall_result") == "PASS"),
                "fail": sum(1 for i in insps if i.get("overall_result") == "FAIL"),
            },
        }}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════
# ② 공정 (Processes)
# ══════════════════════════════════════════════

@router.get("/sites/{site_id}/processes")
async def list_processes(
    site_id: str,
    status_code: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        offset = (page - 1) * size
        q = supabase.table("construction_site_processes").select("*", count="exact") \
            .eq("site_id", site_id).eq("is_active", True)
        if status_code:
            q = q.eq("status_code", status_code)
        q = q.order("sort_order").order("created_at").range(offset, offset + size - 1)
        res = q.execute()
        return {"status": "success", "data": {
            "items": res.data or [], "total": res.count or 0, "page": page, "size": size,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/processes")
async def create_process(site_id: str, body: ProcessCreate):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        data["site_id"] = site_id
        for key in ("planned_start", "planned_end"):
            if key in data and isinstance(data[key], date):
                data[key] = data[key].isoformat()
        data["created_at"] = _now_iso()
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_site_processes").insert(data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="등록 실패")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/processes/{process_id}")
async def get_process(process_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_site_processes").select("*").eq("id", process_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="공정을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.patch("/processes/{process_id}")
async def update_process(process_id: str, body: ProcessPatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        for key in ("planned_start", "planned_end", "actual_start", "actual_end"):
            if key in data and isinstance(data[key], date):
                data[key] = data[key].isoformat()
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_site_processes").update(data).eq("id", process_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="공정을 찾을 수 없습니다.")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/processes/{process_id}")
async def delete_process(process_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_site_processes").update({"is_active": False, "updated_at": _now_iso()}).eq("id", process_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="공정을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


# ══════════════════════════════════════════════
# ③ KCSC 마스터
# ══════════════════════════════════════════════

@router.get("/kcsc/processes")
async def list_kcsc_processes(
    search: Optional[str] = Query(None),
    construction_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    supabase = get_supabase()
    try:
        offset = (page - 1) * size
        q = supabase.table("kcsc_process_master").select("*", count="exact")
        if search:
            q = q.ilike("process_name", f"%{search}%")
        if construction_type:
            q = q.eq("construction_type", construction_type)
        q = q.order("process_code").range(offset, offset + size - 1)
        res = q.execute()
        return {"status": "success", "data": {
            "items": res.data or [], "total": res.count or 0, "page": page, "size": size,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kcsc/works/{process_id}")
async def list_kcsc_works(process_id: str):
    supabase = get_supabase()
    try:
        res = supabase.table("kcsc_work_master").select("*") \
            .eq("process_id", process_id).order("work_code").execute()
        return {"status": "success", "data": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════════
# ④ 위험작업 / PTW (Works)
# ══════════════════════════════════════════════

@router.get("/sites/{site_id}/works")
async def list_works(
    site_id: str,
    status_code: Optional[str] = Query(None),
    ptw_status: Optional[str] = Query(None),
    work_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        offset = (page - 1) * size
        q = supabase.table("construction_works").select("*", count="exact") \
            .eq("site_id", site_id).eq("is_active", True)
        if status_code:  q = q.eq("status_code", status_code)
        if ptw_status:   q = q.eq("ptw_status", ptw_status)
        if work_date:    q = q.eq("work_date", work_date)
        q = q.order("work_date", desc=True).order("created_at", desc=True).range(offset, offset + size - 1)
        res = q.execute()
        return {"status": "success", "data": {
            "items": res.data or [], "total": res.count or 0, "page": page, "size": size,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/works")
async def create_work(site_id: str, body: WorkCreate):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        data["site_id"] = site_id
        if "work_date" in data and isinstance(data["work_date"], date):
            data["work_date"] = data["work_date"].isoformat()
        data["ptw_number"] = _ptw_number(site_id, supabase)
        data["ptw_status"] = "DRAFT"
        data["created_at"] = _now_iso()
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_works").insert(data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="등록 실패")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/works/{work_id}")
async def get_work(work_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_works").select("*").eq("id", work_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.patch("/works/{work_id}")
async def update_work(work_id: str, body: WorkPatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        if "work_date" in data and isinstance(data["work_date"], date):
            data["work_date"] = data["work_date"].isoformat()
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_works").update(data).eq("id", work_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/works/{work_id}/ptw")
async def update_ptw(work_id: str, body: PtwPatch):
    supabase = get_supabase()
    allowed = {"APPROVED", "REJECTED", "CLOSED"}
    if body.ptw_status not in allowed:
        raise HTTPException(status_code=400, detail=f"ptw_status는 {allowed} 중 하나여야 합니다.")
    data: Dict[str, Any] = {"ptw_status": body.ptw_status, "updated_at": _now_iso()}
    if body.ptw_status == "APPROVED":
        data["ptw_approved_by"] = body.ptw_approved_by
        data["ptw_approved_at"] = _now_iso()
    res = supabase.table("construction_works").update(data).eq("id", work_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.delete("/works/{work_id}")
async def delete_work(work_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_works").update({"is_active": False, "updated_at": _now_iso()}).eq("id", work_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


# ══════════════════════════════════════════════
# ⑤ 작업자 (Workers)
# ══════════════════════════════════════════════

@router.get("/sites/{site_id}/workers")
async def list_workers(
    site_id: str,
    worker_type: Optional[str] = Query(None),
    entry_status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        offset = (page - 1) * size
        q = supabase.table("construction_workers").select("*", count="exact") \
            .eq("site_id", site_id).eq("is_active", True)
        if worker_type:   q = q.eq("worker_type", worker_type)
        if entry_status:  q = q.eq("entry_status", entry_status)
        if search:        q = q.ilike("worker_name", f"%{search}%")
        q = q.order("created_at", desc=True).range(offset, offset + size - 1)
        res = q.execute()
        return {"status": "success", "data": {
            "items": res.data or [], "total": res.count or 0, "page": page, "size": size,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/workers")
async def create_worker(site_id: str, body: WorkerCreate):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        data["site_id"] = site_id
        for key in ("join_date", "safety_edu_date"):
            if key in data and isinstance(data[key], date):
                data[key] = data[key].isoformat()
        data["created_at"] = _now_iso()
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_workers").insert(data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="등록 실패")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workers/{worker_id}")
async def get_worker(worker_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_workers").select("*").eq("id", worker_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.patch("/workers/{worker_id}")
async def update_worker(worker_id: str, body: WorkerPatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        for key in ("join_date", "leave_date", "health_check_date", "safety_edu_date"):
            if key in data and isinstance(data[key], date):
                data[key] = data[key].isoformat()
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_workers").update(data).eq("id", worker_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/workers/{worker_id}/entry")
async def update_entry(worker_id: str, body: EntryPatch):
    supabase = get_supabase()
    allowed = {"IN", "OUT", "OFFSITE"}
    if body.entry_status not in allowed:
        raise HTTPException(status_code=400, detail=f"entry_status는 {allowed} 중 하나여야 합니다.")
    data: Dict[str, Any] = {"entry_status": body.entry_status, "updated_at": _now_iso()}
    if body.entry_status == "IN":
        data["last_entry_at"] = _now_iso()
    res = supabase.table("construction_workers").update(data).eq("id", worker_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.delete("/workers/{worker_id}")
async def delete_worker(worker_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_workers").update({"is_active": False, "updated_at": _now_iso()}).eq("id", worker_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="작업자를 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


# ══════════════════════════════════════════════
# ⑥ 안전점검 (Inspections)
# ══════════════════════════════════════════════

@router.get("/sites/{site_id}/inspections")
async def list_inspections(
    site_id: str,
    inspection_type: Optional[str] = Query(None),
    overall_result: Optional[str] = Query(None),
    corrective_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        offset = (page - 1) * size
        q = supabase.table("construction_inspections").select("*", count="exact") \
            .eq("site_id", site_id).eq("is_active", True)
        if inspection_type:   q = q.eq("inspection_type", inspection_type)
        if overall_result:    q = q.eq("overall_result", overall_result)
        if corrective_status: q = q.eq("corrective_status", corrective_status)
        q = q.order("inspection_date", desc=True).range(offset, offset + size - 1)
        res = q.execute()
        return {"status": "success", "data": {
            "items": res.data or [], "total": res.count or 0, "page": page, "size": size,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sites/{site_id}/inspections")
async def create_inspection(site_id: str, body: InspectionCreate):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        data["site_id"] = site_id
        if "inspection_date" in data and isinstance(data["inspection_date"], datetime):
            data["inspection_date"] = data["inspection_date"].isoformat()
        if "corrective_deadline" in data and isinstance(data["corrective_deadline"], date):
            data["corrective_deadline"] = data["corrective_deadline"].isoformat()
        data["created_at"] = _now_iso()
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_inspections").insert(data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="등록 실패")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inspections/{inspection_id}")
async def get_inspection(inspection_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_inspections").select("*").eq("id", inspection_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.patch("/inspections/{inspection_id}")
async def update_inspection(inspection_id: str, body: InspectionPatch):
    supabase = get_supabase()
    try:
        data = body.model_dump(exclude_none=True)
        if not data:
            raise HTTPException(status_code=400, detail="수정할 항목이 없습니다.")
        if "corrective_deadline" in data and isinstance(data["corrective_deadline"], date):
            data["corrective_deadline"] = data["corrective_deadline"].isoformat()
        data["updated_at"] = _now_iso()
        res = supabase.table("construction_inspections").update(data).eq("id", inspection_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다.")
        return {"status": "success", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/inspections/{inspection_id}/corrective")
async def update_corrective(inspection_id: str, body: CorrectivePatch):
    supabase = get_supabase()
    allowed = {"IN_PROGRESS", "DONE"}
    if body.corrective_status not in allowed:
        raise HTTPException(status_code=400, detail=f"corrective_status는 {allowed} 중 하나여야 합니다.")
    data: Dict[str, Any] = {"corrective_status": body.corrective_status, "updated_at": _now_iso()}
    if body.corrective_action:
        data["corrective_action"] = body.corrective_action
    res = supabase.table("construction_inspections").update(data).eq("id", inspection_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@router.delete("/inspections/{inspection_id}")
async def delete_inspection(inspection_id: str):
    supabase = get_supabase()
    res = supabase.table("construction_inspections").update({"is_active": False, "updated_at": _now_iso()}).eq("id", inspection_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


# ══════════════════════════════════════════════
# ⑦ 안전관리자 선임 의무 판정 엔진
# ══════════════════════════════════════════════

@router.post("/engine/safety-manager")
async def engine_safety_manager(body: SafetyManagerBody):
    """
    산안법 시행령 제16조 기준 안전관리자 선임 의무 자동 판정
    - BUILDING: 도급금액 >= 150억
    - CIVIL: 도급금액 >= 120억
    - 하도급 포함 상시 근로자 >= 50명
    """
    result = calc_safety_manager(body.site_type, body.contract_amount, body.total_workers)
    return {"status": "success", "data": result}
