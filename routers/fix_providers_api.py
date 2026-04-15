# routers/fix_providers_api.py — TAI Fix 업체 등록/조회 API
# v1.1.0 (2026-04-15): fix_provider_overview 뷰 컬럼명 provider_id 반영, FK JOIN 컬럼명 수정
# v1.0.0: 신규
#   POST /connect/providers        — 업체 등록 (공개, 트랜잭션)
#   GET  /connect/providers        — 업체 목록 (fix_provider_overview 뷰)
#   GET  /connect/providers/{id}   — 업체 상세 (JOIN)
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from db.database import get_supabase

router = APIRouter(prefix="/connect/providers", tags=["TAI Fix 업체"])


# ── Pydantic 모델 ───────────────────────────────────────────────

class QualificationIn(BaseModel):
    qualification_id: int
    headcount: int = 1
    license_number: Optional[str] = None
    issued_date: Optional[str] = None
    expiry_date: Optional[str] = None


class ServiceIn(BaseModel):
    subcategory_id: int
    price_min: Optional[int] = None
    price_max: Optional[int] = None
    price_unit: Optional[str] = None
    price_note: Optional[str] = None


class ProviderCreate(BaseModel):
    company_name: str
    business_number: Optional[str] = None
    representative: Optional[str] = None
    phone: str
    email: str
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    established_year: Optional[int] = None
    employee_count: Optional[int] = None
    service_regions: Optional[List[str]] = None
    description: Optional[str] = None
    qualifications: Optional[List[QualificationIn]] = []
    services: Optional[List[ServiceIn]] = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── POST /connect/providers — 업체 등록 (공개, 트랜잭션) ────────

@router.post("", status_code=201)
def create_provider(body: ProviderCreate):
    """
    TAI Fix 업체 등록.
    - fix_providers INSERT
    - fix_provider_qualifications 반복 INSERT
    - fix_provider_services 반복 INSERT
    하나라도 실패하면 전체 롤백.
    인증 없이 호출 가능 (공개 API).
    """
    if not body.company_name.strip():
        raise HTTPException(status_code=400, detail="company_name은 필수입니다")
    if not body.phone.strip():
        raise HTTPException(status_code=400, detail="phone은 필수입니다")
    if not body.email.strip():
        raise HTTPException(status_code=400, detail="email은 필수입니다")

    sb = get_supabase()

    # ① 업체 기본 정보 INSERT
    provider_data = {
        "company_name":     body.company_name.strip(),
        "business_number":  body.business_number,
        "representative":   body.representative,
        "phone":            body.phone.strip(),
        "email":            body.email.strip(),
        "address":          body.address,
        "latitude":         body.latitude,
        "longitude":        body.longitude,
        "established_year": body.established_year,
        "employee_count":   body.employee_count,
        "service_regions":  body.service_regions or [],
        "description":      body.description,
        "status":           "PENDING",
        "created_at":       _now(),
        "updated_at":       _now(),
    }

    try:
        prov_res = sb.table("fix_providers").insert(provider_data).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"업체 등록 실패: {e}")

    if not prov_res.data:
        raise HTTPException(status_code=500, detail="업체 등록 실패 (빈 응답)")

    provider_id = prov_res.data[0]["id"]

    # ② 자격/면허 INSERT
    if body.qualifications:
        qual_rows = [
            {
                "provider_id":      provider_id,
                "qualification_id": q.qualification_id,
                "headcount":        q.headcount,
                "license_number":   q.license_number,
                "issued_date":      q.issued_date,
                "expiry_date":      q.expiry_date,
                "verified":         False,
            }
            for q in body.qualifications
        ]
        try:
            sb.table("fix_provider_qualifications").insert(qual_rows).execute()
        except Exception as e:
            sb.table("fix_providers").delete().eq("id", provider_id).execute()
            raise HTTPException(status_code=500, detail=f"자격 등록 실패 (롤백): {e}")

    # ③ 서비스 영역 INSERT
    if body.services:
        svc_rows = [
            {
                "provider_id":    provider_id,
                "subcategory_id": s.subcategory_id,
                "price_min":      s.price_min,
                "price_max":      s.price_max,
                "price_unit":     s.price_unit,
                "price_note":     s.price_note,
                "is_active":      True,
            }
            for s in body.services
        ]
        try:
            sb.table("fix_provider_services").insert(svc_rows).execute()
        except Exception as e:
            sb.table("fix_provider_qualifications").delete().eq("provider_id", provider_id).execute()
            sb.table("fix_providers").delete().eq("id", provider_id).execute()
            raise HTTPException(status_code=500, detail=f"서비스 등록 실패 (롤백): {e}")

    return {
        "status":  "success",
        "message": "업체 등록이 완료되었습니다. 검토 후 승인됩니다.",
        "id":      provider_id,
    }


# ── GET /connect/providers — 업체 목록 ─────────────────────────

@router.get("")
def list_providers(
    status:    Optional[str] = None,
    region:    Optional[str] = None,
    page:      int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    TAI Fix 업체 목록.
    fix_provider_overview 뷰 사용 (provider_id, company_name, status, …).
    status: PENDING | APPROVED | REJECTED | SUSPENDED
    region: 지역명 부분 매칭 (예: 서울)
    """
    sb = get_supabase()
    q = sb.table("fix_provider_overview").select("*")

    if status:
        q = q.eq("status", status.upper())
    if region:
        q = q.ilike("service_regions", f"%{region}%")

    offset = (page - 1) * page_size
    res = q.order("provider_id", desc=True).range(offset, offset + page_size - 1).execute()

    return {
        "status": "success",
        "data":   res.data or [],
        "page":   page,
    }


# ── GET /connect/providers/{id} — 업체 상세 ────────────────────

@router.get("/{provider_id}")
def get_provider(provider_id: str):
    """
    TAI Fix 업체 상세 조회.
    fix_providers + qualifications + services JOIN.
    """
    sb = get_supabase()

    prov = sb.table("fix_providers").select("*").eq("id", provider_id).limit(1).execute()
    if not prov.data:
        raise HTTPException(status_code=404, detail="업체를 찾을 수 없습니다")

    quals = sb.table("fix_provider_qualifications").select(
        "id, qualification_id, headcount, license_number, issued_date, expiry_date, verified,"
        "fix_qualification_master(name, qualification_type, grade)"
    ).eq("provider_id", provider_id).execute()

    svcs = sb.table("fix_provider_services").select(
        "id, subcategory_id, price_min, price_max, price_unit, price_note, is_active,"
        "fix_subcategory(name, service_grade, category_id)"
    ).eq("provider_id", provider_id).eq("is_active", True).execute()

    return {
        "status": "success",
        "data": {
            **prov.data[0],
            "qualifications": quals.data or [],
            "services":       svcs.data or [],
        },
    }
