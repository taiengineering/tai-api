"""
수선중개 관리 라우터 — v1.0.0
prefix: /repair

대상 테이블:
  - repair_companies   : 수선업체
  - matching_requests  : 매칭 요청 (request_type='REPAIR')

엔드포인트:
  GET  /repair/companies              수선업체 목록
  POST /repair/companies              수선업체 등록
  GET  /repair/companies/{id}         수선업체 상세
  PATCH /repair/companies/{id}        수선업체 수정
  POST /repair/companies/{id}/verify  검증 상태 변경
  GET  /repair/requests               수선 요청 목록
  POST /repair/requests               수선 요청 등록
  PATCH /repair/requests/{id}         수선 요청 상태 수정
  GET  /repair/stats                  전체 통계
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone
from db.supabase_client import get_supabase

router = APIRouter(prefix="/repair", tags=["수선중개"])

VERSION = "1.0.0"

PATCH_COMPANY_ALLOWED = {
    "company_name", "phone", "email", "business_no",
    "license_types", "license_verified", "equipment_types",
    "company_scale", "capital_amount", "region_sido", "region_range_km",
    "min_project_amount", "max_project_amount",
    "verified_status", "is_active",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────
# GET /repair/stats  전체 통계
# ─────────────────────────────────────────────────────
@router.get("/stats")
async def get_repair_stats():
    supabase = get_supabase()
    try:
        c_res = supabase.table("repair_companies").select(
            "id, verified_status, is_active"
        ).execute()
        companies = c_res.data or []

        r_res = supabase.table("matching_requests").select(
            "id, status"
        ).eq("request_type", "REPAIR").execute()
        requests = r_res.data or []

        return {"status": "success", "data": {
            "companies_total":    len(companies),
            "active_companies":   sum(1 for c in companies if c.get("is_active")),
            "verified_companies": sum(1 for c in companies if c.get("verified_status") in ("APPROVED", "VERIFIED")),
            "pending_companies":  sum(1 for c in companies if c.get("verified_status") == "PENDING"),
            "requests_total":     len(requests),
            "matched_count":      sum(1 for r in requests if r.get("status") in ("MATCHED", "CONTRACTED", "ACTIVE")),
            "contracted_count":   sum(1 for r in requests if r.get("status") in ("CONTRACTED", "ACTIVE")),
            "pending_requests":   sum(1 for r in requests if r.get("status") == "PENDING"),
            "version": VERSION,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# GET /repair/companies  수선업체 목록
# ─────────────────────────────────────────────────────
@router.get("/companies")
async def list_repair_companies(
    region_sido:     Optional[str]  = Query(None, description="지역 시도"),
    verified_status: Optional[str]  = Query(None, description="검증 상태"),
    equipment_type:  Optional[str]  = Query(None, description="설비 종류 필터"),
    search:          Optional[str]  = Query(None, description="업체명/이메일 검색"),
    page:            int = Query(1, ge=1),
    page_size:       int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        query = supabase.table("repair_companies").select("*", count="exact").eq("is_active", True)
        if verified_status:
            query = query.eq("verified_status", verified_status)
        if region_sido:
            query = query.eq("region_sido", region_sido)
        if search:
            query = query.or_(f"company_name.ilike.%{search}%,email.ilike.%{search}%")
        if equipment_type:
            query = query.contains("equipment_types", [equipment_type])
        offset = (page - 1) * page_size
        res = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()
        total = res.count or 0
        return {"status": "success", "data": {
            "items": res.data or [], "total": total, "page": page, "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# POST /repair/companies  수선업체 등록
# ─────────────────────────────────────────────────────
@router.post("/companies")
async def create_repair_company(body: dict):
    supabase = get_supabase()
    try:
        if not body.get("company_name", "").strip():
            raise HTTPException(status_code=400, detail="company_name은 필수입니다.")
        now = _now_iso()
        insert_data = {
            "company_name":      body.get("company_name"),
            "phone":             body.get("phone"),
            "email":             body.get("email"),
            "business_no":       body.get("business_no"),
            "license_types":     body.get("license_types", []),
            "license_verified":  False,
            "equipment_types":   body.get("equipment_types", []),
            "company_scale":     body.get("company_scale"),
            "capital_amount":    body.get("capital_amount"),
            "region_sido":       body.get("region_sido"),
            "region_range_km":   body.get("region_range_km", 50),
            "min_project_amount": body.get("min_project_amount"),
            "max_project_amount": body.get("max_project_amount"),
            "verified_status":   "PENDING",
            "match_count":       0,
            "is_active":         True,
            "created_at":        now,
            "updated_at":        now,
        }
        insert_data = {k: v for k, v in insert_data.items() if v is not None}
        res = supabase.table("repair_companies").insert(insert_data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="수선업체 등록 실패")
        return {"status": "success", "message": "수선업체가 등록됐습니다.", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# GET /repair/companies/{company_id}  수선업체 상세
# ─────────────────────────────────────────────────────
@router.get("/companies/{company_id}")
async def get_repair_company(company_id: str):
    supabase = get_supabase()
    try:
        res = supabase.table("repair_companies").select("*").eq("id", company_id).limit(1).execute()
        rows = res.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="수선업체를 찾을 수 없습니다.")
        return {"status": "success", "data": rows[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# PATCH /repair/companies/{company_id}  수선업체 수정
# ─────────────────────────────────────────────────────
@router.patch("/companies/{company_id}")
async def update_repair_company(company_id: str, body: dict):
    supabase = get_supabase()
    try:
        update_data = {k: v for k, v in body.items() if k in PATCH_COMPANY_ALLOWED}
        if not update_data:
            raise HTTPException(status_code=400, detail="수정할 필드가 없습니다.")
        update_data["updated_at"] = _now_iso()
        res = supabase.table("repair_companies").update(update_data).eq("id", company_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="수선업체를 찾을 수 없습니다.")
        return {"status": "success", "message": "수정됐습니다.", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# POST /repair/companies/{company_id}/verify  검증 상태 변경
# ─────────────────────────────────────────────────────
@router.post("/companies/{company_id}/verify")
async def verify_repair_company(company_id: str, body: dict):
    supabase = get_supabase()
    try:
        verified_status = body.get("verified_status")
        valid = ("APPROVED", "VERIFIED", "REJECTED", "PENDING", "SUSPENDED")
        if verified_status not in valid:
            raise HTTPException(status_code=400, detail=f"verified_status는 {valid} 중 하나여야 합니다.")
        db_status = "APPROVED" if verified_status == "VERIFIED" else verified_status
        now = _now_iso()
        res = supabase.table("repair_companies").update({
            "verified_status": db_status,
            "updated_at":      now,
        }).eq("id", company_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="수선업체를 찾을 수 없습니다.")
        return {"status": "success",
                "message": f"검증 상태가 {verified_status}로 변경됐습니다.",
                "data": {"company_id": company_id, "verified_status": db_status, "updated_at": now}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# GET /repair/requests  수선 요청 목록
# ─────────────────────────────────────────────────────
@router.get("/requests")
async def list_repair_requests(
    status:     Optional[str] = Query(None),
    factory_id: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
    page:       int = Query(1, ge=1),
    page_size:  int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    try:
        query = supabase.table("matching_requests").select(
            "id, created_at, factory_id, company_id, request_detail, status, requested_by",
            count="exact"
        ).eq("request_type", "REPAIR")
        if status:     query = query.eq("status", status)
        if factory_id: query = query.eq("factory_id", factory_id)
        if company_id: query = query.eq("company_id", company_id)
        offset = (page - 1) * page_size
        res = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()
        items = []
        for row in (res.data or []):
            detail = row.get("request_detail") or {}
            items.append({
                "id":             row.get("id"),
                "created_at":     row.get("created_at"),
                "factory_id":     row.get("factory_id"),
                "company_id":     row.get("company_id"),
                "factory_name":   detail.get("factory_name", ""),
                "equipment_type": detail.get("equipment_type", ""),
                "repair_type":    detail.get("repair_type", ""),
                "status_code":    row.get("status", ""),
                "fee_amount":     detail.get("fee_amount", 0),
                "request_detail": detail,
            })
        total = res.count or 0
        return {"status": "success", "data": {
            "items": items, "total": total, "page": page, "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if total else 0,
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# POST /repair/requests  수선 요청 등록
# ─────────────────────────────────────────────────────
@router.post("/requests")
async def create_repair_request(body: dict):
    supabase = get_supabase()
    try:
        factory_id = body.get("factory_id")
        if not factory_id:
            raise HTTPException(status_code=400, detail="factory_id는 필수입니다.")
        now = _now_iso()
        # request_detail에 추가 정보 담기
        detail = {
            "factory_name":   body.get("factory_name", ""),
            "equipment_type": body.get("equipment_type", ""),
            "repair_type":    body.get("repair_type", ""),
            "description":    body.get("description", ""),
            "fee_amount":     body.get("fee_amount", 0),
            "urgency":        body.get("urgency", "NORMAL"),
        }
        insert_data = {
            "request_type":   "REPAIR",
            "factory_id":     factory_id,
            "company_id":     body.get("company_id"),
            "request_detail": detail,
            "status":         "PENDING",
            "requested_by":   body.get("requested_by"),
            "created_at":     now,
            "updated_at":     now,
        }
        insert_data = {k: v for k, v in insert_data.items() if v is not None}
        res = supabase.table("matching_requests").insert(insert_data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="수선 요청 등록 실패")
        return {"status": "success", "message": "수선 요청이 등록됐습니다.", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────
# PATCH /repair/requests/{request_id}  수선 요청 상태 수정
# ─────────────────────────────────────────────────────
@router.patch("/requests/{request_id}")
async def update_repair_request(request_id: str, body: dict):
    supabase = get_supabase()
    try:
        allowed_status = ("PENDING", "MATCHED", "CONTRACTED", "ACTIVE", "COMPLETED", "CANCELLED")
        new_status = body.get("status")
        if new_status and new_status not in allowed_status:
            raise HTTPException(status_code=400, detail=f"status는 {allowed_status} 중 하나여야 합니다.")
        update_data: dict = {"updated_at": _now_iso()}
        if new_status:
            update_data["status"] = new_status
        if "company_id" in body:
            update_data["company_id"] = body["company_id"]
        if "request_detail" in body:
            update_data["request_detail"] = body["request_detail"]
        res = supabase.table("matching_requests").update(update_data).eq(
            "id", request_id
        ).eq("request_type", "REPAIR").execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="수선 요청을 찾을 수 없습니다.")
        return {"status": "success", "message": "수선 요청이 수정됐습니다.", "data": res.data[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
