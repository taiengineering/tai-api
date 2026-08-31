"""
선임연결 관리 라우터 — v1.1.0
v1.1.0:
  - /stats: matched_count, contracted_count, fee_total 추가
  - /requests: 신규 엔드포인트 (matching_requests 기반)
  - /list: contact_phone, contact_email, service_regions alias 추가
  - /agencies: representative_name, address, contact_phone, contact_email,
               service_regions, max_factory_count, current_factory_count alias 추가
  - POST /personnel: contact_phone/email/service_regions body alias 처리
  - POST /personnel/agencies: representative_name, address, contact_phone 처리
  - POST /personnel/create: /personnel 와 동일한 엔드포인트 추가
  - verify: VERIFIED 상태 추가 (APPROVED와 동일 처리)
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone
from db.supabase_client import get_supabase
from services.time import now_kst, serialize_external_utc

router = APIRouter(prefix="/personnel", tags=["선임연결"])

VERSION = "1.1.0"

PATCH_PERSONNEL_ALLOWED = {
    "name", "phone", "contact_phone", "tai_grade", "region_sido", "service_regions",
    "region_range_km", "monthly_fee_min", "monthly_fee_max", "max_slots",
    "verified_status", "is_active", "current_slots",
}

PATCH_AGENCY_ALLOWED = {
    "agency_name", "phone", "contact_phone", "email", "contact_email",
    "region_sido", "service_regions", "max_clients", "max_factory_count",
    "current_clients", "current_factory_count", "specialties",
    "verified_status", "is_active",
}


def _now_iso() -> str:
    return serialize_external_utc(now_kst())


def _map_personnel(row: dict) -> dict:
    """safety_personnel 행 → 프론트 기대 필드명으로 변환"""
    row = dict(row)
    row["contact_phone"]   = row.get("phone", "")
    row["contact_email"]   = row.get("email", "")
    row["service_regions"] = [row["region_sido"]] if row.get("region_sido") else []
    return row


def _map_agency(row: dict) -> dict:
    """safety_agencies 행 → 프론트 기대 필드명으로 변환"""
    row = dict(row)
    row["contact_phone"]        = row.get("phone", "")
    row["contact_email"]        = row.get("email", "")
    row["representative_name"]  = row.get("representative_name", "")
    row["address"]              = row.get("address", "")
    row["service_regions"]      = row.get("region_sido") or []
    row["max_factory_count"]    = row.get("max_clients", 0)
    row["current_factory_count"] = row.get("current_clients", 0)
    return row


# ─────────────────────────────────────────────────────
# 1. GET /personnel/stats  전체 통계
# ─────────────────────────────────────────────────────
@router.get("/stats")
async def get_personnel_stats():
    supabase = get_supabase()
    try:
        p_res = supabase.table("safety_personnel").select(
            "id, employment_type, verified_status, is_active, match_count, monthly_fee_min"
        ).execute()
        personnel = p_res.data or []

        a_res = supabase.table("safety_agencies").select(
            "id, verified_status, is_active"
        ).execute()
        agencies = a_res.data or []

        # matching_requests 기반 contracted/matched 집계
        mr_res = supabase.table("matching_requests").select(
            "id, status"
        ).eq("request_type", "PERSONNEL").execute()
        mr_rows = mr_res.data or []

        matched_count    = sum(1 for r in mr_rows if r.get("status") in ("MATCHED", "CONTRACTED", "ACTIVE"))
        contracted_count = sum(1 for r in mr_rows if r.get("status") in ("CONTRACTED", "ACTIVE"))
        fee_total        = sum(
            int(r.get("monthly_fee_min") or 0) * 12
            for r in personnel if r.get("is_active")
        )

        approved_count = sum(
            1 for r in personnel + agencies if r.get("verified_status") in ("APPROVED", "VERIFIED")
        )
        pending_count  = sum(
            1 for r in personnel + agencies if r.get("verified_status") == "PENDING"
        )
        fulltime_count = sum(1 for r in personnel if r.get("employment_type") == "FULLTIME")
        parttime_count = sum(1 for r in personnel if r.get("employment_type") == "PARTTIME")

        return {
            "status": "success",
            "data": {
                "personnel_total":    len(personnel),
                "agencies_total":     len(agencies),
                "matched_count":      matched_count,
                "contracted_count":   contracted_count,
                "fee_total":          fee_total,
                "approved_count":     approved_count,
                "pending_count":      pending_count,
                "fulltime_count":     fulltime_count,
                "parttime_count":     parttime_count,
                "active_personnel":   sum(1 for r in personnel if r.get("is_active")),
                "active_agencies":    sum(1 for r in agencies  if r.get("is_active")),
                "version":            VERSION,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 2. GET /personnel/requests  선임연결 요청 목록 (신규)
# ─────────────────────────────────────────────────────
@router.get("/requests")
async def list_personnel_requests(
    status: Optional[str] = Query(None, description="요청 상태 필터"),
    factory_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """선임연결 요청 목록 (matching_requests where request_type=PERSONNEL)"""
    supabase = get_supabase()
    try:
        query = supabase.table("matching_requests").select(
            "id, created_at, factory_id, company_id, request_detail, status, requested_by",
            count="exact"
        ).eq("request_type", "PERSONNEL")

        if status:
            query = query.eq("status", status)
        if factory_id:
            query = query.eq("factory_id", factory_id)

        offset = (page - 1) * page_size
        res = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()

        items = []
        for row in (res.data or []):
            detail = row.get("request_detail") or {}
            items.append({
                "id":                   row.get("id"),
                "created_at":           row.get("created_at"),
                "factory_id":           row.get("factory_id"),
                "factory_name":         detail.get("factory_name", ""),
                "employment_type":      detail.get("employment_type", ""),
                "matched_manager_name": detail.get("matched_manager_name", ""),
                "status_code":          row.get("status", ""),
                "fee_amount":           detail.get("fee_amount", 0),
                "request_detail":       detail,
            })

        total = res.count or 0
        return {"status": "success", "data": {
            "items": items, "total": total, "page": page, "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 3. GET /personnel/fee-calc  수수료 계산
# ─────────────────────────────────────────────────────
@router.get("/fee-calc")
async def calc_fee(
    employment_type: str = Query(...),
    annual_salary: Optional[int] = Query(None),
    monthly_fee: Optional[int] = Query(None),
):
    try:
        if employment_type == "FULLTIME":
            if annual_salary is None:
                raise HTTPException(status_code=400, detail="FULLTIME은 annual_salary가 필요합니다.")
            fee = annual_salary * 0.15
        elif employment_type == "PARTTIME":
            if monthly_fee is None:
                raise HTTPException(status_code=400, detail="PARTTIME은 monthly_fee가 필요합니다.")
            fee = monthly_fee * 12 * 0.10
        else:
            raise HTTPException(status_code=400, detail="employment_type은 FULLTIME 또는 PARTTIME이어야 합니다.")
        fee_int = int(fee)
        return {"status": "success", "data": {
            "employment_type": employment_type,
            "fee_amount":      fee_int,
            "fee_total":       fee_int,
            "fee_label":       f"{fee_int // 10000:,}만원",
        }}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 4. GET /personnel/agencies  대행업체 목록
# ─────────────────────────────────────────────────────
@router.get("/agencies")
async def list_agencies(
    region_sido: Optional[str] = Query(None),
    verified_status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        query = supabase.table("safety_agencies").select("*", count="exact").eq("is_active", True)
        if verified_status:
            query = query.eq("verified_status", verified_status)
        if search:
            query = query.or_(f"agency_name.ilike.%{search}%,email.ilike.%{search}%")
        if region_sido:
            query = query.contains("region_sido", [region_sido])
        offset = (page - 1) * page_size
        res = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()
        total = res.count or 0
        return {"status": "success", "data": {
            "items": [_map_agency(r) for r in (res.data or [])],
            "total": total, "page": page, "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 5. POST /personnel/agencies  대행업체 등록
# ─────────────────────────────────────────────────────
@router.post("/agencies")
async def create_agency(body: dict):
    supabase = get_supabase()
    try:
        if not body.get("agency_name", "").strip():
            raise HTTPException(status_code=400, detail="agency_name은 필수입니다.")
        now = _now_iso()
        # alias 처리: contact_phone → phone, contact_email → email 등
        phone   = body.get("contact_phone") or body.get("phone")
        email   = body.get("contact_email") or body.get("email")
        regions = body.get("service_regions") or body.get("region_sido", [])
        max_cli = body.get("max_factory_count") or body.get("max_clients", 0)
        insert_data = {
            "agency_name":     body.get("agency_name"),
            "phone":           phone,
            "email":           email,
            "business_no":     body.get("business_no"),
            "license_no":      body.get("license_no"),
            "region_sido":     regions,
            "max_clients":     max_cli,
            "current_clients": 0,
            "specialties":     body.get("specialties", []),
            "verified_status": "PENDING",
            "match_count":     0,
            "is_active":       True,
            "created_at":      now,
            "updated_at":      now,
        }
        res = supabase.table("safety_agencies").insert(insert_data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="대행업체 등록 실패")
        return {"status": "success", "message": "대행업체가 등록됐습니다.", "data": _map_agency(res.data[0])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 6. PATCH /personnel/agencies/{agency_id}  대행업체 수정
# ─────────────────────────────────────────────────────
@router.patch("/agencies/{agency_id}")
async def update_agency(agency_id: str, body: dict):
    supabase = get_supabase()
    try:
        update_data = {}
        # alias 처리
        if "contact_phone" in body: update_data["phone"]   = body["contact_phone"]
        if "contact_email" in body: update_data["email"]   = body["contact_email"]
        if "service_regions" in body: update_data["region_sido"] = body["service_regions"]
        if "max_factory_count" in body: update_data["max_clients"] = body["max_factory_count"]
        if "current_factory_count" in body: update_data["current_clients"] = body["current_factory_count"]
        for k, v in body.items():
            if k in PATCH_AGENCY_ALLOWED and k not in update_data:
                update_data[k] = v
        if not update_data:
            raise HTTPException(status_code=400, detail="수정할 필드가 없습니다.")
        update_data["updated_at"] = _now_iso()
        res = supabase.table("safety_agencies").update(update_data).eq("id", agency_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="대행업체를 찾을 수 없습니다.")
        return {"status": "success", "message": "수정됐습니다.", "data": _map_agency(res.data[0])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 7. GET /personnel  개인기술자 목록
# ─────────────────────────────────────────────────────
@router.get("")
async def list_personnel(
    employment_type: Optional[str] = Query(None),
    tai_grade: Optional[str] = Query(None),
    region_sido: Optional[str] = Query(None),
    verified_status: Optional[str] = Query(None),
    qualification_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        query = supabase.table("safety_personnel").select("*", count="exact").eq("is_active", True)
        if employment_type:    query = query.eq("employment_type", employment_type)
        if tai_grade:          query = query.eq("tai_grade", tai_grade)
        if region_sido:        query = query.eq("region_sido", region_sido)
        if verified_status:    query = query.eq("verified_status", verified_status)
        if qualification_type: query = query.eq("qualification_type", qualification_type)
        if search:             query = query.or_(f"name.ilike.%{search}%,email.ilike.%{search}%")
        offset = (page - 1) * page_size
        res = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()
        total = res.count or 0
        return {"status": "success", "data": {
            "items": [_map_personnel(r) for r in (res.data or [])],
            "total": total, "page": page, "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 8. POST /personnel  개인기술자 등록
# ─────────────────────────────────────────────────────
@router.post("")
async def create_personnel(body: dict):
    supabase = get_supabase()
    try:
        if not body.get("name", "").strip():
            raise HTTPException(status_code=400, detail="name은 필수입니다.")
        emp_type = body.get("employment_type")
        if emp_type not in ("FULLTIME", "PARTTIME", "RESIDENT", "NON_RESIDENT", None):
            raise HTTPException(status_code=400, detail="employment_type 값이 올바르지 않습니다.")
        # alias 처리
        phone   = body.get("contact_phone") or body.get("phone")
        email   = body.get("contact_email") or body.get("email")
        regions = body.get("service_regions")
        region_sido = regions[0] if isinstance(regions, list) and regions else body.get("region_sido")
        now = _now_iso()
        insert_data = {
            "name":               body.get("name"),
            "phone":              phone,
            "email":              email,
            "employment_type":    emp_type,
            "qualification_type": body.get("qualification_type"),
            "qualification_grade": body.get("qualification_grade"),
            "qualification_no":   body.get("qualification_no"),
            "qualification_verified": False,
            "career_years":       body.get("career_years", 0),
            "tai_grade":          body.get("tai_grade"),
            "region_sido":        region_sido,
            "region_range_km":    body.get("region_range_km", 50),
            "industry_specialties": body.get("industry_specialties", []),
            "current_slots":      0,
            "max_slots":          body.get("max_slots", 1),
            "monthly_fee_min":    body.get("monthly_fee_min"),
            "monthly_fee_max":    body.get("monthly_fee_max"),
            "verified_status":    "PENDING",
            "match_count":        0,
            "is_active":          True,
            "created_at":         now,
            "updated_at":         now,
        }
        insert_data = {k: v for k, v in insert_data.items() if v is not None}
        res = supabase.table("safety_personnel").insert(insert_data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="등록 실패")
        return {"status": "success", "message": "개인기술자가 등록됐습니다.", "data": _map_personnel(res.data[0])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 8-b. POST /personnel/create  alias
# ─────────────────────────────────────────────────────
@router.post("/create")
async def create_personnel_alias(body: dict):
    """POST /personnel 과 동일 — /create alias"""
    return await create_personnel(body)


# ─────────────────────────────────────────────────────
# 9. GET /personnel/{personnel_id}  개인기술자 상세
# ─────────────────────────────────────────────────────
@router.get("/{personnel_id}")
async def get_personnel(personnel_id: str):
    supabase = get_supabase()
    try:
        res = supabase.table("safety_personnel").select("*").eq(
            "id", personnel_id
        ).limit(1).execute()
        rows = res.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="기술자를 찾을 수 없습니다.")
        return {"status": "success", "data": _map_personnel(rows[0])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 10. PATCH /personnel/{personnel_id}  개인기술자 수정
# ─────────────────────────────────────────────────────
@router.patch("/{personnel_id}")
async def update_personnel(personnel_id: str, body: dict):
    supabase = get_supabase()
    try:
        update_data = {}
        if "contact_phone" in body: update_data["phone"] = body["contact_phone"]
        if "contact_email" in body: update_data["email"] = body["contact_email"]
        if "service_regions" in body:
            regions = body["service_regions"]
            update_data["region_sido"] = regions[0] if isinstance(regions, list) and regions else regions
        for k, v in body.items():
            if k in PATCH_PERSONNEL_ALLOWED and k not in update_data:
                update_data[k] = v
        if not update_data:
            raise HTTPException(status_code=400, detail="수정할 필드가 없습니다.")
        update_data["updated_at"] = _now_iso()
        res = supabase.table("safety_personnel").update(update_data).eq("id", personnel_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="기술자를 찾을 수 없습니다.")
        return {"status": "success", "message": "수정됐습니다.", "data": _map_personnel(res.data[0])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# 11. POST /personnel/{personnel_id}/verify  검증 상태 변경
# ─────────────────────────────────────────────────────
@router.post("/{personnel_id}/verify")
async def verify_personnel(personnel_id: str, body: dict):
    """
    검증 상태 변경. VERIFIED → APPROVED 동일 처리.
    body: { verified_status: 'VERIFIED'|'APPROVED'|'REJECTED'|'PENDING', note: '...' }
    """
    supabase = get_supabase()
    try:
        verified_status = body.get("verified_status")
        valid = ("APPROVED", "VERIFIED", "REJECTED", "PENDING", "SUSPENDED")
        if verified_status not in valid:
            raise HTTPException(status_code=400, detail=f"verified_status는 {valid} 중 하나여야 합니다.")
        # VERIFIED → APPROVED 로 정규화 (DB 컬럼 값)
        db_status = "APPROVED" if verified_status == "VERIFIED" else verified_status
        now = _now_iso()
        p_res = supabase.table("safety_personnel").update({
            "verified_status": db_status,
            "updated_at":      now,
        }).eq("id", personnel_id).execute()
        if not p_res.data:
            raise HTTPException(status_code=404, detail="기술자를 찾을 수 없습니다.")
        try:
            supabase.table("verification_logs").insert({
                "target_type":       "PERSONNEL",
                "target_id":         personnel_id,
                "verification_step": "STATUS_CHANGE",
                "status":            db_status,
                "note":              body.get("note", ""),
                "created_at":        now,
            }).execute()
        except Exception:
            pass  # 로그 실패는 무시
        return {"status": "success",
                "message": f"검증 상태가 {verified_status}로 변경됐습니다.",
                "data": {"personnel_id": personnel_id, "verified_status": db_status, "updated_at": now}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
