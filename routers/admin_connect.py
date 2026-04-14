# routers/admin_connect.py — 연결 서비스 사전등록 API v1.0.0
# v1.0.0 (2026-04-14):
#   POST  /connect/register          — 공개 (인증 불필요)
#   GET   /admin/connect-registrations — 관리자 인증 필요
#   PATCH /admin/connect-registrations/{id} — 관리자 인증 필요
#   GET   /admin/connect-registrations/export — CSV 내보내기
import csv
import io
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from db.database import get_supabase
from routers.auth import get_current_user

router = APIRouter(tags=["연결 등록"])


# ── 모델 ──────────────────────────────────────────────────────────────

class ConnectRegisterCreate(BaseModel):
    service_type:    str           # appointment | repair | consulting | education
    requester_name:  str
    requester_phone: str
    requester_email: Optional[str] = None
    company_name:    Optional[str] = None
    company_size:    Optional[str] = None
    sector_code:     Optional[str] = None   # BUILDING | INDUSTRY | CONSTRUCTION
    region:          Optional[str] = None
    message:         Optional[str] = None


class ConnectRegisterPatch(BaseModel):
    status:       Optional[str] = None  # pending|contacted|matched|closed|cancelled
    admin_memo:   Optional[str] = None
    assigned_to:  Optional[str] = None
    contacted_at: Optional[str] = None
    matched_at:   Optional[str] = None
    closed_at:    Optional[str] = None


SERVICE_TYPES = {"appointment", "repair", "consulting", "education"}
STATUS_TYPES  = {"pending", "contacted", "matched", "closed", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── POST /connect/register — 공개 ────────────────────────────────────

@router.post("/connect/register")
def create_connect_registration(body: ConnectRegisterCreate):
    """연결 서비스 신청 — 인증 불필요, 웹사이트 공개 폼에서 호출."""
    if body.service_type not in SERVICE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"service_type은 {sorted(SERVICE_TYPES)} 중 하나여야 합니다"
        )

    sb = get_supabase()
    data = {
        "service_type":    body.service_type,
        "requester_name":  body.requester_name,
        "requester_phone": body.requester_phone.replace("-", "").replace(" ", ""),
        "requester_email": body.requester_email,
        "company_name":    body.company_name,
        "company_size":    body.company_size,
        "sector_code":     body.sector_code.upper() if body.sector_code else None,
        "region":          body.region,
        "message":         body.message,
        "status":          "pending",
    }
    res = sb.table("connect_registrations").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="등록에 실패했습니다")

    return {
        "status":  "success",
        "message": "신청이 완료되었습니다. 빠른 시일 내 연락드리겠습니다.",
        "id":      res.data[0]["id"],
    }


# ── GET /admin/connect-registrations — 관리자 ─────────────────────────

@router.get("/admin/connect-registrations")
def list_connect_registrations(
    service_type: Optional[str] = None,
    status:       Optional[str] = None,
    sector_code:  Optional[str] = None,
    region:       Optional[str] = None,
    q:            Optional[str] = None,    # 이름/전화 검색
    page:         int = Query(1, ge=1),
    page_size:    int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """연결 신청 목록 조회 — 관리자 인증 필요."""
    sb = get_supabase()
    query = sb.table("connect_registrations").select("*")

    if service_type:
        query = query.eq("service_type", service_type)
    if status:
        query = query.eq("status", status)
    if sector_code:
        query = query.eq("sector_code", sector_code.upper())
    if region:
        query = query.ilike("region", f"%{region}%")
    if q:
        # 이름 또는 전화번호 검색
        query = query.or_(f"requester_name.ilike.%{q}%,requester_phone.ilike.%{q}%")

    offset = (page - 1) * page_size
    res = query.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()

    # 전체 건수
    count_q = sb.table("connect_registrations").select("id", count="exact")
    if service_type: count_q = count_q.eq("service_type", service_type)
    if status:       count_q = count_q.eq("status", status)
    if sector_code:  count_q = count_q.eq("sector_code", sector_code.upper())
    total = count_q.execute().count or 0

    return {
        "status":    "success",
        "data":      res.data or [],
        "total":     total,
        "page":      page,
        "page_size": page_size,
        "pages":     -(-total // page_size),  # ceil
    }


# ── PATCH /admin/connect-registrations/{id} ──────────────────────────

@router.patch("/admin/connect-registrations/{reg_id}")
def update_connect_registration(
    reg_id: str,
    body: ConnectRegisterPatch,
    current_user: dict = Depends(get_current_user),
):
    """연결 신청 상태 업데이트 — 관리자 인증 필요."""
    sb = get_supabase()
    old = sb.table("connect_registrations").select("*").eq("id", reg_id).single().execute()
    if not old.data:
        raise HTTPException(status_code=404, detail="신청 정보를 찾을 수 없습니다")

    if body.status and body.status not in STATUS_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"status는 {sorted(STATUS_TYPES)} 중 하나여야 합니다"
        )

    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="변경할 항목이 없습니다")

    now = _now()
    # 상태 전환 시 타임스탬프 자동 기록
    if body.status == "contacted" and not old.data.get("contacted_at"):
        update_data["contacted_at"] = now
    elif body.status == "matched" and not old.data.get("matched_at"):
        update_data["matched_at"] = now
    elif body.status in ("closed", "cancelled") and not old.data.get("closed_at"):
        update_data["closed_at"] = now
    update_data["updated_at"] = now

    res = sb.table("connect_registrations").update(update_data).eq("id", reg_id).execute()
    return {"status": "success", "data": res.data[0] if res.data else None}


# ── GET /admin/connect-registrations/export — CSV ────────────────────

@router.get("/admin/connect-registrations/export")
def export_connect_registrations(
    service_type: Optional[str] = None,
    status:       Optional[str] = None,
    sector_code:  Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """연결 신청 CSV 내보내기 — 관리자 인증 필요."""
    sb = get_supabase()
    query = sb.table("connect_registrations").select("*")
    if service_type: query = query.eq("service_type", service_type)
    if status:       query = query.eq("status", status)
    if sector_code:  query = query.eq("sector_code", sector_code.upper())
    rows = query.order("created_at", desc=True).execute().data or []

    HEADERS = [
        "id", "service_type", "requester_name", "requester_phone", "requester_email",
        "company_name", "company_size", "sector_code", "region", "message",
        "status", "admin_memo", "contacted_at", "matched_at", "closed_at", "created_at",
    ]
    SERVICE_LABEL = {
        "appointment": "선임 연결",
        "repair":      "수선 연결",
        "consulting":  "컨설팅",
        "education":   "교육",
    }
    STATUS_LABEL = {
        "pending":   "대기",
        "contacted": "연락완료",
        "matched":   "매칭완료",
        "closed":    "종결",
        "cancelled": "취소",
    }

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=HEADERS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        row["service_type"] = SERVICE_LABEL.get(row.get("service_type", ""), row.get("service_type", ""))
        row["status"]       = STATUS_LABEL.get(row.get("status", ""), row.get("status", ""))
        writer.writerow(row)

    output.seek(0)
    filename = f"connect_registrations_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── GET /admin/connect-registrations/stats ───────────────────────────

@router.get("/admin/connect-registrations/stats")
def connect_registration_stats(
    current_user: dict = Depends(get_current_user),
):
    """서비스 유형·상태별 건수 통계."""
    sb = get_supabase()
    rows = sb.table("connect_registrations").select("service_type, status").execute().data or []

    stats: dict = {}
    for row in rows:
        svc = row["service_type"]
        st  = row["status"]
        if svc not in stats:
            stats[svc] = {"total": 0, "pending": 0, "contacted": 0,
                          "matched": 0, "closed": 0, "cancelled": 0}
        stats[svc]["total"] += 1
        stats[svc][st] = stats[svc].get(st, 0) + 1

    return {"status": "success", "data": stats}
