"""
안전보건 회의 관리 라우터 — v1.2.1

safety_committee_meetings 테이블 사용
참석자는 전용 테이블 safety_committee_attendees 사용 (v1.1.0~)

v1.2.1 (2026-08-18, 로그 관측):
  [FIX] GET /{meeting_id} 에 uuid 가드. 정의되지 않은 고정경로(/summary 등)가 catch-all 에
        잡혀 .eq("id","summary") → Postgres 22P02(500)로 깨지던 것 방지. 비-uuid → 깨끗한 404.
        (work_schedules v1.2.2 와 동일 패턴.) 회의 요약이 필요하면 GET /schedule 이 준수현황을 제공.
v1.2.0 (2026-08-17, LEDGER ④):
  [FIX] GET /safety-meetings 에 date_from·date_to(회의일 meeting_date 범위) 추가.
        화면(useSafetyMeetingList)이 보내던 기간 필터가 서버에 선언되지 않아 무시되던 것 해소.

API:
  POST   /safety-meetings                     회의록 생성
  GET    /safety-meetings                     목록 조회 (date_from·date_to 기간 필터 ← v1.2.0)
  GET    /safety-meetings/schedule            개최 주기 준수 현황 (고정경로)
  GET    /safety-meetings/{id}                상세 조회 (attendees 포함)
  PATCH  /safety-meetings/{id}                수정
  POST   /safety-meetings/{id}/files          파일 첨부 (URL 저장)
  POST   /safety-meetings/{id}/complete       완료 처리

meeting_type:
  SAFETY_COMMITTEE    산업안전보건위원회 (제24조) — 100인 이상, 분기 1회
  CONTRACTOR_COUNCIL  도급 안전보건협의체 (제64조) — 도급현장, 월 1회
  LABOR_COUNCIL       노사협의회
  OTHER               기타 안전회의
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, date, timedelta
from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services.company_scope import require_company_id, scoped_list_company, _ensure_own_company

router = APIRouter(prefix="/safety-meetings", tags=["safety_meetings"])

VERSION = "1.2.1"

RETENTION_YEARS = 3   # 회의록 법정 보존기한

MEETING_CYCLE = {
    "SAFETY_COMMITTEE":   "QUARTERLY",   # 분기 1회
    "CONTRACTOR_COUNCIL": "MONTHLY",     # 월 1회
    "LABOR_COUNCIL":      "QUARTERLY",   # 분기 1회
    "OTHER":              None,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _retention_expires(meeting_date_str: str, years: int = RETENTION_YEARS) -> str:
    try:
        d = date.fromisoformat(meeting_date_str)
        return date(d.year + years, d.month, d.day).isoformat()
    except Exception:
        return ""


# ── 참석자 전용 테이블(safety_committee_attendees) 헬퍼 ─────────

def _load_attendees(supabase, meeting_id: str) -> list:
    """회의 참석자 목록을 전용 테이블에서 조회."""
    res = supabase.table("safety_committee_attendees").select(
        "id, worker_id, name, role, phone, organization, sign_status, attended_at"
    ).eq("meeting_id", meeting_id).order("created_at").execute()
    return res.data or []


def _replace_attendees(supabase, meeting_id: str, attendees: list) -> int:
    """참석자 전용 테이블을 전달된 목록으로 교체하고 인원수를 반환."""
    supabase.table("safety_committee_attendees").delete().eq(
        "meeting_id", meeting_id
    ).execute()
    rows = []
    for a in (attendees or []):
        if not isinstance(a, dict):
            continue
        rows.append({
            "meeting_id":   meeting_id,
            "worker_id":    a.get("worker_id"),
            "name":         a.get("name") or a.get("worker_name") or "",
            "role":         a.get("role"),
            "phone":        a.get("phone"),
            "organization": a.get("organization"),
            "sign_status":  a.get("sign_status") or "PENDING",
            "attended_at":  a.get("attended_at"),
        })
    if rows:
        supabase.table("safety_committee_attendees").insert(rows).execute()
    return len(rows)


# ── Pydantic 모델 ─────────────────────────────────────────────

class MeetingCreateBody(BaseModel):
    company_id:       str
    factory_id:       Optional[str] = None
    meeting_type:     str                          # SAFETY_COMMITTEE | CONTRACTOR_COUNCIL | LABOR_COUNCIL | OTHER
    meeting_title:    str
    meeting_date:     str                          # YYYY-MM-DD
    meeting_place:    Optional[str] = None
    duration_min:     Optional[int] = None
    chair_name:       Optional[str] = None
    attendee_count:   Optional[int] = None
    attendees_json:   Optional[list] = []          # 참석자 목록 → 전용 테이블로 저장
    agenda_items:     Optional[list] = []
    discussion_text:  Optional[str] = None
    resolution_text:  Optional[str] = None
    created_by:       Optional[str] = None


class MeetingUpdateBody(BaseModel):
    meeting_type:    Optional[str]  = None
    meeting_title:   Optional[str]  = None
    meeting_date:    Optional[str]  = None
    meeting_place:   Optional[str]  = None
    duration_min:    Optional[int]  = None
    chair_name:      Optional[str]  = None
    attendee_count:  Optional[int]  = None
    attendees_json:  Optional[list] = None         # 참석자 목록 → 전용 테이블로 저장
    agenda_items:    Optional[list] = None
    discussion_text: Optional[str]  = None
    resolution_text: Optional[str]  = None
    files_json:      Optional[list] = None
    status_code:     Optional[str]  = None


class FileAttachBody(BaseModel):
    file_url:  str
    file_name: str
    file_type: Optional[str] = None


# ── 고정경로 먼저 선언 ────────────────────────────────────────

@router.get("/schedule")
def get_meeting_schedule(
    company_id: str = Query(..., description="회사 ID"),
    year:       int = Query(None, description="연도 (기본: 올해)"),
    current: dict = Depends(get_current_user),
):
    """
    안전보건 회의 개최 주기 준수 현황.
    - SAFETY_COMMITTEE: 분기별 개최 여부 (1~4분기)
    - CONTRACTOR_COUNCIL: 월별 개최 여부 (1~12월)
    """
    supabase = get_supabase()
    target_year = year or date.today().year
    scoped_cid, deny_all = scoped_list_company(current, supabase, company_id)
    if deny_all or not scoped_cid:
        return {
            "status": "success",
            "data": {
                "company_id": None,
                "year": target_year,
                "safety_committee": [],
                "contractor_council": [],
                "summary": {
                    "committee_compliant": 0,
                    "committee_overdue": 0,
                    "council_compliant": 0,
                    "council_overdue": 0,
                },
            },
        }
    company_id = scoped_cid

    res = supabase.table("safety_committee_meetings").select(
        "id, meeting_type, meeting_date, status_code"
    ).eq("company_id", company_id).gte(
        "meeting_date", f"{target_year}-01-01"
    ).lte(
        "meeting_date", f"{target_year}-12-31"
    ).execute()

    rows = res.data or []

    # 분기별 집계 (SAFETY_COMMITTEE)
    quarters: dict = {1: [], 2: [], 3: [], 4: []}
    months:   dict = {m: [] for m in range(1, 13)}

    for r in rows:
        try:
            md = date.fromisoformat(r["meeting_date"])
        except Exception:
            continue
        q = (md.month - 1) // 3 + 1
        mt = r["meeting_type"]
        if mt == "SAFETY_COMMITTEE":
            quarters[q].append(r)
        elif mt == "CONTRACTOR_COUNCIL":
            months[md.month].append(r)

    today = date.today()
    current_quarter = (today.month - 1) // 3 + 1
    current_month   = today.month

    committee_status = []
    for q, items in quarters.items():
        passed = q < current_quarter or (q == current_quarter and today.month > q * 3)
        committee_status.append({
            "quarter":    q,
            "label":      f"{q}분기",
            "count":      len(items),
            "compliant":  len(items) > 0,
            "overdue":    passed and len(items) == 0,
        })

    council_status = []
    for m, items in months.items():
        passed = m < current_month
        council_status.append({
            "month":     m,
            "label":     f"{m}월",
            "count":     len(items),
            "compliant": len(items) > 0,
            "overdue":   passed and len(items) == 0,
        })

    return {
        "status": "success",
        "data": {
            "company_id":           company_id,
            "year":                 target_year,
            "safety_committee":     committee_status,
            "contractor_council":   council_status,
            "summary": {
                "committee_compliant":  sum(1 for s in committee_status if s["compliant"]),
                "committee_overdue":    sum(1 for s in committee_status if s["overdue"]),
                "council_compliant":    sum(1 for s in council_status   if s["compliant"]),
                "council_overdue":      sum(1 for s in council_status   if s["overdue"]),
            }
        }
    }


# ── CRUD ─────────────────────────────────────────────────────

@router.post("")
def create_meeting(body: MeetingCreateBody, current: dict = Depends(get_current_user)):
    """안전보건 회의록 생성."""
    supabase = get_supabase()
    body.company_id = require_company_id(current, supabase)   # 무회사 403, 클라 company_id 무시
    now = _now()
    row = {
        "company_id":      body.company_id,
        "factory_id":      body.factory_id,
        "meeting_type":    body.meeting_type,
        "meeting_title":   body.meeting_title,
        "meeting_date":    body.meeting_date,
        "meeting_place":   body.meeting_place,
        "duration_min":    body.duration_min,
        "chair_name":      body.chair_name,
        "attendee_count":  body.attendee_count or 0,
        "attendees_json":  [],
        "agenda_items":    body.agenda_items   or [],
        "discussion_text": body.discussion_text,
        "resolution_text": body.resolution_text,
        "files_json":      [],
        "status_code":     "DRAFT",
        "retention_years": RETENTION_YEARS,
        "created_by":      body.created_by,
        "created_at":      now,
        "updated_at":      now,
    }
    res = supabase.table("safety_committee_meetings").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="회의록 생성에 실패했습니다.")

    record = res.data[0]
    # 참석자는 전용 테이블(safety_committee_attendees)에 저장
    if body.attendees_json:
        cnt = _replace_attendees(supabase, record["id"], body.attendees_json)
        supabase.table("safety_committee_meetings").update(
            {"attendee_count": cnt}
        ).eq("id", record["id"]).execute()
        record["attendee_count"] = cnt
    record["attendees"] = _load_attendees(supabase, record["id"])
    record["retention_expires"] = _retention_expires(body.meeting_date)
    return {"status": "success", "message": "회의록이 생성됐습니다.", "data": record}


@router.get("")
def list_meetings(
    company_id:   Optional[str] = Query(None),
    factory_id:   Optional[str] = Query(None),
    meeting_type: Optional[str] = Query(None),
    status_code:  Optional[str] = Query(None),
    year:         Optional[int] = Query(None),
    date_from:    Optional[str] = Query(None, description="회의일 시작 (YYYY-MM-DD)"),
    date_to:      Optional[str] = Query(None, description="회의일 종료 (YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current: dict = Depends(get_current_user),
):
    """안전보건 회의 목록 조회. v1.2.0: date_from·date_to(meeting_date 범위) 필터 추가."""
    supabase = get_supabase()
    scoped_cid, deny_all = scoped_list_company(current, supabase, company_id)
    if deny_all or not scoped_cid:
        return {"status": "success", "data": {"items": [], "total": 0, "page": page, "size": size, "total_pages": 0}}
    company_id = scoped_cid
    q = supabase.table("safety_committee_meetings").select(
        "id, company_id, factory_id, meeting_type, meeting_title, meeting_date, "
        "meeting_place, chair_name, attendee_count, files_json, status_code, "
        "retention_years, completed_at, created_at",
        count="exact"
    )
    if company_id:   q = q.eq("company_id",   company_id)
    if factory_id:   q = q.eq("factory_id",   factory_id)
    if meeting_type: q = q.eq("meeting_type", meeting_type)
    if status_code:  q = q.eq("status_code",  status_code)
    if year:
        q = q.gte("meeting_date", f"{year}-01-01").lte("meeting_date", f"{year}-12-31")
    # v1.2.0 (LEDGER ④): 화면이 보내던 기간 필터를 실제 적용
    if date_from:    q = q.gte("meeting_date", date_from)
    if date_to:      q = q.lte("meeting_date", date_to)

    offset = (page - 1) * size
    res = q.order("meeting_date", desc=True).range(offset, offset + size - 1).execute()
    total = res.count or 0

    items = []
    for row in (res.data or []):
        row["retention_expires"] = _retention_expires(
            row.get("meeting_date", ""), row.get("retention_years", RETENTION_YEARS)
        )
        row["file_count"] = len(row.get("files_json") or [])
        items.append(row)

    return {
        "status": "success",
        "data": {
            "items":       items,
            "total":       total,
            "page":        page,
            "size":        size,
            "total_pages": (total + size - 1) // size if total else 0,
        }
    }


@router.get("/{meeting_id}")
def get_meeting(meeting_id: str, current: dict = Depends(get_current_user)):
    """안전보건 회의 상세 조회 (참석자는 전용 테이블에서 로드)."""
    # 정의되지 않은 고정경로(/summary 등)가 catch-all 에 잡혀 22P02 나던 것 방지 (v1.2.1)
    if not _is_uuid(meeting_id):
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    supabase = get_supabase()
    res = supabase.table("safety_committee_meetings").select("*").eq(
        "id", meeting_id
    ).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    record = res.data[0]
    _ensure_own_company(record.get("company_id"), current, supabase, "회의록을 찾을 수 없습니다.")
    record["attendees"] = _load_attendees(supabase, meeting_id)
    record["retention_expires"] = _retention_expires(
        record.get("meeting_date", ""), record.get("retention_years", RETENTION_YEARS)
    )
    return {"status": "success", "data": record}


@router.patch("/{meeting_id}")
def update_meeting(meeting_id: str, body: MeetingUpdateBody, current: dict = Depends(get_current_user)):
    """안전보건 회의 수정 (참석자는 전용 테이블에 교체 저장)."""
    if not _is_uuid(meeting_id):
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    supabase = get_supabase()
    _own = supabase.table("safety_committee_meetings").select("company_id").eq("id", meeting_id).limit(1).execute()
    if not _own.data:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    _ensure_own_company(_own.data[0].get("company_id"), current, supabase, "회의록을 찾을 수 없습니다.")
    payload = {k: v for k, v in body.dict().items() if v is not None}
    # 참석자는 전용 테이블로 분리 저장 (json 컬럼 대신)
    attendees = payload.pop("attendees_json", None)
    if not payload and attendees is None:
        raise HTTPException(status_code=422, detail="수정할 내용이 없습니다.")

    record = None
    if payload:
        payload["updated_at"] = _now()
        res = supabase.table("safety_committee_meetings").update(payload).eq(
            "id", meeting_id
        ).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
        record = res.data[0]

    if attendees is not None:
        cnt = _replace_attendees(supabase, meeting_id, attendees)
        supabase.table("safety_committee_meetings").update(
            {"attendee_count": cnt, "updated_at": _now()}
        ).eq("id", meeting_id).execute()

    if record is None:
        chk = supabase.table("safety_committee_meetings").select("*").eq(
            "id", meeting_id
        ).limit(1).execute()
        if not chk.data:
            raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
        record = chk.data[0]

    record["attendees"] = _load_attendees(supabase, meeting_id)
    return {"status": "success", "message": "수정됐습니다.", "data": record}


@router.post("/{meeting_id}/files")
def attach_file(meeting_id: str, body: FileAttachBody, current: dict = Depends(get_current_user)):
    """파일 URL 첨부 (프론트에서 Supabase Storage 업로드 후 URL 전달)."""
    supabase = get_supabase()
    _own = supabase.table("safety_committee_meetings").select("company_id").eq("id", meeting_id).limit(1).execute()
    if not _own.data:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    _ensure_own_company(_own.data[0].get("company_id"), current, supabase, "회의록을 찾을 수 없습니다.")
    # 현재 files_json 조회
    chk = supabase.table("safety_committee_meetings").select(
        "id, files_json"
    ).eq("id", meeting_id).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")

    files = list(chk.data[0].get("files_json") or [])
    files.append({
        "url":       body.file_url,
        "name":      body.file_name,
        "type":      body.file_type,
        "added_at":  _now(),
    })
    res = supabase.table("safety_committee_meetings").update({
        "files_json": files,
        "updated_at": _now(),
    }).eq("id", meeting_id).execute()
    return {"status": "success", "message": "파일이 첨부됐습니다.", "data": {"files": files}}


@router.delete("/{meeting_id}")
def delete_meeting(meeting_id: str, current: dict = Depends(get_current_user)):
    """안전보건 회의 삭제 (참석자는 FK ON DELETE CASCADE로 함께 삭제)."""
    supabase = get_supabase()
    _own = supabase.table("safety_committee_meetings").select("company_id").eq("id", meeting_id).limit(1).execute()
    if not _own.data:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    _ensure_own_company(_own.data[0].get("company_id"), current, supabase, "회의록을 찾을 수 없습니다.")
    res = supabase.table("safety_committee_meetings").delete().eq(
        "id", meeting_id
    ).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    return {"status": "success", "message": "삭제됐습니다."}


@router.post("/{meeting_id}/complete")
def complete_meeting(meeting_id: str, current: dict = Depends(get_current_user)):
    """회의록 완료 처리."""
    supabase = get_supabase()
    _own = supabase.table("safety_committee_meetings").select("company_id").eq("id", meeting_id).limit(1).execute()
    if not _own.data:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    _ensure_own_company(_own.data[0].get("company_id"), current, supabase, "회의록을 찾을 수 없습니다.")
    now = _now()
    res = supabase.table("safety_committee_meetings").update({
        "status_code":  "COMPLETED",
        "completed_at": now,
        "updated_at":   now,
    }).eq("id", meeting_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    return {"status": "success", "message": "완료 처리됐습니다.", "data": res.data[0]}
