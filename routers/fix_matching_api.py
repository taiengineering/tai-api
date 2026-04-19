# routers/fix_matching_api.py — TAI Fix 서비스 요청 접수 API
# v1.0.0 (2026-04-15): 신규
#   POST /matching/requests  — 서비스 요청 접수 (공개, 인증 불필요)
#   GET  /matching/requests  — 관리자용 요청 목록
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from db.database import get_supabase

router = APIRouter(prefix="/matching/requests", tags=["TAI Fix 서비스요청"])


class ServiceRequestCreate(BaseModel):
    company_name: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    facility_type: Optional[str] = None   # building/factory/construction/apartment/other
    category_code: Optional[str] = None   # ELEC/FIRE/MECH/ARCH/ENV/SAFE/CLEAN/IT
    description: Optional[str] = None
    urgency: Optional[str] = None         # urgent/normal/flexible
    budget: Optional[str] = None          # unknown/under100/100to500/500to1000/over1000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("", status_code=201)
def create_service_request(body: ServiceRequestCreate):
    """
    TAI Fix 서비스 요청 접수.
    fix_service_requests 테이블에 저장.
    인증 없이 호출 가능 (공개 API).
    """
    if not body.company_name or not body.company_name.strip():
        raise HTTPException(status_code=400, detail="company_name은 필수입니다")

    sb = get_supabase()

    row = {
        "company_name":  body.company_name.strip(),
        "address":       body.address,
        "latitude":      body.latitude,
        "longitude":     body.longitude,
        "contact_name":  body.contact_name,
        "contact_phone": body.contact_phone,
        "contact_email": body.contact_email,
        "facility_type": body.facility_type,
        "category_code": body.category_code,
        "description":   body.description,
        "urgency":       body.urgency,
        "budget":        body.budget,
        "status":        "pending",
        "created_at":    _now(),
        "updated_at":    _now(),
    }

    try:
        res = sb.table("fix_service_requests").insert(row).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서비스 요청 접수 실패: {e}")

    if not res.data:
        raise HTTPException(status_code=500, detail="서비스 요청 접수 실패 (빈 응답)")

    request_id = res.data[0]["id"]

    return {
        "status":     "success",
        "message":    "서비스 요청이 접수되었습니다. TAI가 적합한 업체를 매칭합니다.",
        "request_id": request_id,
    }


@router.get("", include_in_schema=False)
def list_service_requests(
    status:    Optional[str] = None,
    category:  Optional[str] = None,
    page:      int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """관리자용 서비스 요청 목록."""
    sb = get_supabase()
    q = sb.table("fix_service_requests").select("*")

    if status:
        q = q.eq("status", status)
    if category:
        q = q.eq("category_code", category.upper())

    offset = (page - 1) * page_size
    res = q.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()

    return {
        "status": "success",
        "data":   res.data or [],
        "page":   page,
    }
