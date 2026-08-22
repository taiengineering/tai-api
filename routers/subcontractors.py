"""하도급업체 관리 CRUD — 건설현장별 하도급업체 + 소속 작업자 연결.

v1.0.0  2026-05-26  신규 생성

인증·스코프 (2026-08-20):
  company_id 는 하도급업체(공급사)의 회사이므로 테넌트 키가 아니다.
  테넌트 소유는 site_id → construction_sites.company_id 로 확인한다(전 엔드포인트 로그인).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from uuid import UUID
from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import _ensure_own_company

router = APIRouter(prefix="/construction/subcontractors", tags=["하도급관리"])


def _ensure_site_own(sb, site_id, current) -> None:
    """건설현장 소유 확인 — construction_sites.company_id 경유. 비-ALL 타사 404."""
    r = sb.table("construction_sites").select("company_id").eq("id", str(site_id)).limit(1).execute()
    if not r.data:
        raise HTTPException(404, "현장을 찾을 수 없습니다.")
    _ensure_own_company(r.data[0].get("company_id"), current, sb, "현장을 찾을 수 없습니다.")


def _ensure_sub_own(sb, subcontractor_id, current) -> None:
    """하도급업체 → 현장 → 회사 소유 확인."""
    r = sb.table("subcontractors").select("site_id").eq("id", str(subcontractor_id)).limit(1).execute()
    if not r.data:
        raise HTTPException(404, "하도급업체를 찾을 수 없습니다.")
    _ensure_site_own(sb, r.data[0]["site_id"], current)


def _has_active_children(sb, subcontractor_id) -> bool:
    r = (
        sb.table("subcontractors")
        .select("id")
        .eq("parent_subcontractor_id", str(subcontractor_id))
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    return bool(r.data)


def _derive_parent(sb, site_id: str, parent_id: UUID):
    """같은 현장 상위 수급인 조회. 없으면 400."""
    p = (
        sb.table("subcontractors")
        .select("id, site_id, tier, is_active")
        .eq("id", str(parent_id))
        .limit(1)
        .execute()
    )
    if not p.data:
        raise HTTPException(400, "상위 수급인을 찾을 수 없습니다.")
    row = p.data[0]
    if row.get("is_active") is False:
        raise HTTPException(400, "상위 수급인을 찾을 수 없습니다.")
    if str(row["site_id"]) != str(site_id):
        raise HTTPException(400, "상위 수급인은 같은 현장이어야 합니다.")
    return row


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
    parent_subcontractor_id: Optional[UUID] = None


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
    parent_subcontractor_id: Optional[UUID] = None


# ── List ──
@router.get("")
async def list_subcontractors(
    site_id: UUID = Query(..., description="건설현장 ID"),
    status_code: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    current: dict = Depends(get_current_user),
):
    sb = get_supabase()
    _ensure_site_own(sb, site_id, current)
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
async def get_subcontractor(subcontractor_id: UUID, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _ensure_sub_own(sb, subcontractor_id, current)
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
async def create_subcontractor(body: SubcontractorCreate, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _ensure_site_own(sb, body.site_id, current)
    payload = body.model_dump(mode="json", exclude={"parent_subcontractor_id"})
    payload["site_id"] = str(body.site_id)
    payload["company_id"] = str(body.company_id)
    if body.parent_subcontractor_id:
        parent = _derive_parent(sb, str(body.site_id), body.parent_subcontractor_id)
        payload["tier"] = int(parent["tier"] or 1) + 1
        payload["parent_subcontractor_id"] = str(body.parent_subcontractor_id)
    else:
        payload["tier"] = 1
        payload["parent_subcontractor_id"] = None
    res = sb.table("subcontractors").insert(payload).execute()
    if not res.data:
        raise HTTPException(500, "하도급업체 생성 실패")
    return {"status": "success", "data": res.data[0]}


# ── Update ──
@router.put("/{subcontractor_id}")
async def update_subcontractor(subcontractor_id: UUID, body: SubcontractorUpdate, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _ensure_sub_own(sb, subcontractor_id, current)
    payload = body.model_dump(exclude_none=True, mode="json", exclude={"parent_subcontractor_id"})
    if "parent_subcontractor_id" in body.model_fields_set:
        if _has_active_children(sb, subcontractor_id):
            raise HTTPException(400, "하위가 있어 상위를 바꿀 수 없습니다.")
        cur = (
            sb.table("subcontractors")
            .select("id, site_id")
            .eq("id", str(subcontractor_id))
            .limit(1)
            .execute()
        )
        if not cur.data:
            raise HTTPException(404, "하도급업체를 찾을 수 없습니다.")
        site_id = cur.data[0]["site_id"]
        new_parent = body.parent_subcontractor_id
        if new_parent is None:
            payload["parent_subcontractor_id"] = None
            payload["tier"] = 1
        else:
            if str(new_parent) == str(subcontractor_id):
                raise HTTPException(400, "자기 자신을 상위로 지정할 수 없습니다.")
            parent = _derive_parent(sb, site_id, new_parent)
            payload["parent_subcontractor_id"] = str(new_parent)
            payload["tier"] = int(parent["tier"] or 1) + 1
    if not payload:
        raise HTTPException(400, "수정할 항목이 없습니다.")
    payload["updated_at"] = datetime.utcnow().isoformat()
    res = sb.table("subcontractors").update(payload).eq("id", str(subcontractor_id)).execute()
    if not res.data:
        raise HTTPException(404, "하도급업체를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


# ── Delete ──
@router.delete("/{subcontractor_id}")
async def delete_subcontractor(subcontractor_id: UUID, current: dict = Depends(get_current_user)):
    sb = get_supabase()
    _ensure_sub_own(sb, subcontractor_id, current)
    if _has_active_children(sb, subcontractor_id):
        raise HTTPException(400, "하위 수급인을 먼저 정리하세요.")
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
