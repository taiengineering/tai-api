"""하도급업체 관리 CRUD — 건설현장별 하도급업체 + 소속 작업자 연결.

v1.0.0  2026-05-26  신규 생성
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from uuid import UUID
from db.supabase_client import get_supabase

router = APIRouter(prefix="/construction/subcontractors", tags=["하도급관리"])


# ── Schemas ──
class SubcontractorCreate(BaseModel):
    site_id: UUID
    company_id: UUID
    company_name: str
    representative: Optional[str] = None
    business_number: Optional[str] = None
    work_type: Optional[str] = None
    contract_amount: Optional[float] = None
    contract_start: Optional[date] = None
    contract_end: Optional[date] = None
    worker_count: int = 0
    has_safety_manager: bool = False
    safety_manager_name: Optional[str] = None
    safety_manager_phone: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None


class SubcontractorUpdate(BaseModel):
    company_name: Optional[str] = None
    representative: Optional[str] = None
    business_number: Optional[str] = None
    work_type: Optional[str] = None
    contract_amount: Optional[float] = None
    contract_start: Optional[date] = None
    contract_end: Optional[date] = None
    worker_count: Optional[int] = None
    has_safety_manager: Optional[bool] = None
    safety_manager_name: Optional[str] = None
    safety_manager_phone: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    status_code: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


# ── List ──
@router.get("")
async def list_subcontractors(
    site_id: UUID = Query(..., description="건설현장 ID"),
    status_code: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    sb = get_supabase()
    q = sb.table("subcontractors").select("*").eq("site_id", str(site_id))
    if status_code:
        q = q.eq("status_code", status_code)
    q = q.order("created_at", desc=False)
    offset = (page - 1) * size
    q = q.range(offset, offset + size - 1)
    res = q.execute()
    items = res.data or []

    # 각 하도급업체별 실제 소속 작업자 수 조회
    for item in items:
        wq = sb.table("construction_workers").select("id", count="exact").eq(
            "subcontractor_id", item["id"]
        ).eq("is_active", True)
        wres = wq.execute()
        item["actual_worker_count"] = wres.count if wres.count is not None else 0

    return {"status": "success", "data": {"items": items, "page": page, "size": size}}


# ── Detail ──
@router.get("/{subcontractor_id}")
async def get_subcontractor(subcontractor_id: UUID):
    sb = get_supabase()
    res = sb.table("subcontractors").select("*").eq("id", str(subcontractor_id)).execute()
    if not res.data:
        raise HTTPException(404, "하도급업체를 찾을 수 없습니다.")
    item = res.data[0]

    # 소속 작업자 목록
    wres = sb.table("construction_workers").select("*").eq(
        "subcontractor_id", str(subcontractor_id)
    ).eq("is_active", True).execute()
    item["workers"] = wres.data or []
    item["actual_worker_count"] = len(item["workers"])
    return {"status": "success", "data": item}


# ── Create ──
@router.post("")
async def create_subcontractor(body: SubcontractorCreate):
    sb = get_supabase()
    payload = body.model_dump(mode="json")
    payload["site_id"] = str(body.site_id)
    payload["company_id"] = str(body.company_id)
    res = sb.table("subcontractors").insert(payload).execute()
    if not res.data:
        raise HTTPException(500, "하도급업체 생성 실패")
    return {"status": "success", "data": res.data[0]}


# ── Update ──
@router.put("/{subcontractor_id}")
async def update_subcontractor(subcontractor_id: UUID, body: SubcontractorUpdate):
    sb = get_supabase()
    payload = body.model_dump(exclude_none=True, mode="json")
    if not payload:
        raise HTTPException(400, "수정할 항목이 없습니다.")
    payload["updated_at"] = datetime.utcnow().isoformat()
    res = sb.table("subcontractors").update(payload).eq("id", str(subcontractor_id)).execute()
    if not res.data:
        raise HTTPException(404, "하도급업체를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


# ── Delete ──
@router.delete("/{subcontractor_id}")
async def delete_subcontractor(subcontractor_id: UUID):
    sb = get_supabase()
    # soft delete
    res = sb.table("subcontractors").update(
        {"is_active": False, "status_code": "TERMINATED", "updated_at": datetime.utcnow().isoformat()}
    ).eq("id", str(subcontractor_id)).execute()
    if not res.data:
        raise HTTPException(404, "하도급업체를 찾을 수 없습니다.")
    # 소속 작업자 subcontractor_id 해제
    sb.table("construction_workers").update(
        {"subcontractor_id": None}
    ).eq("subcontractor_id", str(subcontractor_id)).execute()
    return {"status": "success", "message": "하도급업체가 해지되었습니다."}
