"""
수선중개 API — v1.0.0
prefix: /repair

수수료 기준:
  500만원 미만      → 고정 5만원
  500만원~5천만원   → 3%
  5천만원 초과      → 5%
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timezone
from db.supabase_client import get_supabase

router = APIRouter(prefix="/repair", tags=["수선중개"])


def calc_repair_fee(project_amount: int) -> int:
    if project_amount < 5_000_000:
        return 50_000
    elif project_amount <= 50_000_000:
        return int(project_amount * 0.03)
    else:
        return int(project_amount * 0.05)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ────────────────────────────────────────────────────────
# 1. GET /repair/companies — 수선업체 목록
# ────────────────────────────────────────────────────────
@router.get("/companies")
def list_repair_companies(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="업체명 검색"),
    region: Optional[str] = Query(None, description="서비스 지역"),
):
    supabase = get_supabase()
    query = supabase.table("repair_companies").select("*", count="exact")

    if search:
        query = query.ilike("company_name", f"%{search}%")
    if region:
        query = query.contains("service_regions", [region])

    offset = (page - 1) * size
    res = query.order("created_at", desc=True)\
               .range(offset, offset + size - 1).execute()

    return {"status": "success", "data": {
        "items": res.data or [],
        "total": res.count or 0,
        "page": page,
        "size": size,
    }}


# ────────────────────────────────────────────────────────
# 2. POST /repair/companies — 수선업체 등록
# ────────────────────────────────────────────────────────
@router.post("/companies")
def create_repair_company(body: dict):
    supabase = get_supabase()

    company_name = (body.get("company_name") or "").strip()
    if not company_name:
        raise HTTPException(status_code=400, detail="company_name은 필수입니다.")

    insert_data = {
        "company_name": company_name,
        "representative_name": (body.get("representative_name") or "").strip(),
        "contact_phone": (body.get("contact_phone") or "").strip(),
        "contact_email": (body.get("contact_email") or "").strip(),
        "address": (body.get("address") or "").strip(),
        "service_regions": body.get("service_regions", []),
        "max_project_amount": body.get("max_project_amount"),
        "verified_status": "UNVERIFIED",
        "is_active": True,
        "created_at": _now_iso(),
    }

    res = supabase.table("repair_companies").insert(insert_data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="업체 등록 실패")

    return {"status": "success", "message": "수선업체가 등록됐습니다.", "data": res.data[0]}


# ────────────────────────────────────────────────────────
# 3. PATCH /repair/companies/{id} — 수선업체 수정
# ────────────────────────────────────────────────────────
@router.patch("/companies/{company_id}")
def update_repair_company(company_id: str, body: dict):
    supabase = get_supabase()

    allowed = {
        "company_name", "representative_name", "contact_phone",
        "contact_email", "address", "service_regions",
        "max_project_amount", "verified_status", "is_active",
    }
    update_data = {k: v for k, v in body.items() if k in allowed}
    if not update_data:
        raise HTTPException(status_code=400, detail="수정할 필드가 없습니다.")

    update_data["updated_at"] = _now_iso()
    res = supabase.table("repair_companies").update(update_data)\
        .eq("id", company_id).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="업체를 찾을 수 없습니다.")

    return {"status": "success", "message": "업체 정보가 수정됐습니다.", "data": res.data[0]}


# ────────────────────────────────────────────────────────
# 4. DELETE /repair/companies/{id} — 수선업체 비활성화
# ────────────────────────────────────────────────────────
@router.delete("/companies/{company_id}")
def delete_repair_company(company_id: str):
    supabase = get_supabase()

    res = supabase.table("repair_companies").update({
        "is_active": False,
        "updated_at": _now_iso(),
    }).eq("id", company_id).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="업체를 찾을 수 없습니다.")

    return {"status": "success", "message": "업체가 비활성화됐습니다."}


# ────────────────────────────────────────────────────────
# 5. GET /repair/requests — 수선 의뢰 목록
# ────────────────────────────────────────────────────────
@router.get("/requests")
def list_repair_requests(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status_code: Optional[str] = Query(None),
    factory_id: Optional[str] = Query(None),
):
    supabase = get_supabase()
    query = supabase.table("repair_requests").select(
        "*, factories!left(id, name)", count="exact"
    )

    if status_code:
        query = query.eq("status_code", status_code)
    if factory_id:
        query = query.eq("factory_id", factory_id)

    offset = (page - 1) * size
    res = query.order("created_at", desc=True)\
               .range(offset, offset + size - 1).execute()

    items = []
    for row in (res.data or []):
        f = row.pop("factories", None) or {}
        row["factory_name"] = f.get("name")
        items.append(row)

    return {"status": "success", "data": {
        "items": items,
        "total": res.count or 0,
        "page": page,
        "size": size,
    }}


# ────────────────────────────────────────────────────────
# 6. POST /repair/requests — 수선 의뢰 등록
# ────────────────────────────────────────────────────────
@router.post("/requests")
def create_repair_request(body: dict):
    supabase = get_supabase()

    factory_id = body.get("factory_id")
    request_title = (body.get("request_title") or "").strip()
    project_amount = body.get("project_amount", 0)

    if not request_title:
        raise HTTPException(status_code=400, detail="request_title은 필수입니다.")
    if not project_amount or project_amount <= 0:
        raise HTTPException(status_code=400, detail="project_amount는 0보다 커야 합니다.")

    fee_amount = calc_repair_fee(project_amount)

    insert_data = {
        "factory_id": factory_id,
        "company_id": body.get("company_id"),
        "request_title": request_title,
        "request_content": (body.get("request_content") or "").strip(),
        "project_amount": project_amount,
        "fee_amount": fee_amount,
        "matched_repair_company_id": body.get("matched_repair_company_id"),
        "status_code": "PENDING",
        "created_at": _now_iso(),
    }

    res = supabase.table("repair_requests").insert(insert_data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="의뢰 등록 실패")

    return {"status": "success", "message": "수선 의뢰가 등록됐습니다.", "data": res.data[0]}


# ────────────────────────────────────────────────────────
# 7. PATCH /repair/requests/{id} — 의뢰 상태 변경/매칭
# ────────────────────────────────────────────────────────
@router.patch("/requests/{request_id}")
def update_repair_request(request_id: str, body: dict):
    supabase = get_supabase()

    allowed = {
        "status_code", "matched_repair_company_id",
        "request_title", "request_content", "project_amount",
    }
    update_data = {k: v for k, v in body.items() if k in allowed}
    if not update_data:
        raise HTTPException(status_code=400, detail="수정할 필드가 없습니다.")

    # project_amount 변경 시 수수료 재계산
    if "project_amount" in update_data:
        update_data["fee_amount"] = calc_repair_fee(update_data["project_amount"])

    update_data["updated_at"] = _now_iso()
    res = supabase.table("repair_requests").update(update_data)\
        .eq("id", request_id).execute()

    if not res.data:
        raise HTTPException(status_code=404, detail="의뢰를 찾을 수 없습니다.")

    return {"status": "success", "message": "의뢰가 수정됐습니다.", "data": res.data[0]}
