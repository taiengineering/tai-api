# routers/connect_registration.py — 연결 서비스 사전등록 API
# v1.0.0 (2026-04-14): 신규
#   POST /connect/register   — 공개 (인증 불필요)
#   GET  /connect/register   — 관리자 인증 필요
#   PATCH /connect/register/{id} — 관리자 인증 필요
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from db.database import get_supabase
from routers.auth import get_current_user

router = APIRouter(prefix="/connect", tags=["연결 사전등록"])


# ── Pydantic 모델 ──────────────────────────────────────────────

class PreRegistrationCreate(BaseModel):
    service_type: str          # appointment | repair | consulting | education
    requester_name: str
    requester_phone: str
    requester_email: Optional[str] = None
    company_name: Optional[str] = None
    company_size: Optional[str] = None
    sector_code: Optional[str] = None    # BUILDING | INDUSTRY | CONSTRUCTION
    region: Optional[str] = None
    message: Optional[str] = None


class PreRegistrationPatch(BaseModel):
    status: Optional[str] = None         # pending | contacted | matched | closed
    admin_memo: Optional[str] = None
    contacted_at: Optional[str] = None
    matched_at: Optional[str] = None


SERVICE_TYPES = {"appointment", "repair", "consulting", "education"}


# ── POST /connect/register — 공개 ────────────────────────────

@router.post("/register")
def create_pre_registration(body: PreRegistrationCreate):
    """사전등록 신청 — 인증 불필요, 누구나 접근 가능."""
    if body.service_type not in SERVICE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"service_type은 {SERVICE_TYPES} 중 하나여야 합니다"
        )

    sb = get_supabase()
    data = {
        "service_type":    body.service_type,
        "requester_name":  body.requester_name,
        "requester_phone": body.requester_phone,
        "requester_email": body.requester_email,
        "company_name":    body.company_name,
        "company_size":    body.company_size,
        "sector_code":     body.sector_code,
        "region":          body.region,
        "message":         body.message,
        "status":          "pending",
    }
    res = sb.table("connect_pre_registration").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="등록에 실패했습니다")

    return {
        "status": "success",
        "message": "사전등록이 완료되었습니다. 빠른 시일 내에 연락드리겠습니다.",
        "id": res.data[0]["id"],
    }


# ── GET /connect/register — 관리자 ───────────────────────────

@router.get("/register")
def list_pre_registrations(
    service_type: str = None,
    status: str = None,
    sector_code: str = None,
    page: int = 1,
    page_size: int = 50,
    authorization: str = Header(None),
):
    """사전등록 목록 조회 — 관리자 인증 필요."""
    import os
    from routers.auth import verify_token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    token = authorization.split(" ", 1)[1]
    verify_token(token)  # 유효하지 않으면 예외 발생

    sb = get_supabase()
    q = sb.table("connect_pre_registration").select("*")
    if service_type:
        q = q.eq("service_type", service_type)
    if status:
        q = q.eq("status", status)
    if sector_code:
        q = q.eq("sector_code", sector_code.upper())

    offset = (page - 1) * page_size
    res = q.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()
    return {"status": "success", "data": res.data or [], "page": page}


# ── PATCH /connect/register/{id} — 관리자 ────────────────────

@router.patch("/register/{reg_id}")
def update_pre_registration(
    reg_id: str,
    body: PreRegistrationPatch,
    authorization: str = Header(None),
):
    """사전등록 상태 업데이트 — 관리자 인증 필요."""
    from routers.auth import verify_token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    token = authorization.split(" ", 1)[1]
    verify_token(token)

    sb = get_supabase()
    old = sb.table("connect_pre_registration").select("*").eq("id", reg_id).single().execute()
    if not old.data:
        raise HTTPException(status_code=404, detail="등록 정보를 찾을 수 없습니다")

    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="변경할 항목이 없습니다")

    # 상태 전환 시 타임스탬프 자동 기록
    now = datetime.now().isoformat()
    if body.status == "contacted" and not old.data.get("contacted_at"):
        update_data["contacted_at"] = now
    if body.status == "matched" and not old.data.get("matched_at"):
        update_data["matched_at"] = now
    update_data["updated_at"] = now

    res = sb.table("connect_pre_registration").update(update_data).eq("id", reg_id).execute()
    return {"status": "success", "data": res.data[0] if res.data else None}


# ── GET /connect/register/stats — 관리자 통계 ────────────────

@router.get("/register/stats")
def pre_registration_stats(authorization: str = Header(None)):
    """서비스 유형별 등록 현황 통계."""
    from routers.auth import verify_token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    token = authorization.split(" ", 1)[1]
    verify_token(token)

    sb = get_supabase()
    res = sb.table("connect_pre_registration").select(
        "service_type, status"
    ).execute()

    rows = res.data or []
    stats: dict = {}
    for row in rows:
        svc = row["service_type"]
        st = row["status"]
        if svc not in stats:
            stats[svc] = {"total": 0, "pending": 0, "contacted": 0, "matched": 0, "closed": 0}
        stats[svc]["total"] += 1
        stats[svc][st] = stats[svc].get(st, 0) + 1

    return {"status": "success", "data": stats}
