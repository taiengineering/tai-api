"""
TBM(작업 전 안전점검회의) 관리 라우터 — v1.1.0

v1.1.0 (2026-04-07 Phase 3):
  - tbm_meetings.construction_site_id 콓럼 추가 (migration)
  - GET /tbm: construction_site_id 필터 지원
  - POST /tbm body: construction_site_id 저장 지원

tbm_meetings, tbm_attendees 테이블 사용

API:
  POST   /tbm                              TBM 생성
  GET    /tbm                              목록 조회
  GET    /tbm/{id}                         상세 조회
  PATCH  /tbm/{id}                         수정
  POST   /tbm/{id}/complete                완료 처리
  POST   /tbm/transcribe                   STT 텍스트 저장
  GET    /tbm/{id}/attendees               참석자 목록
  POST   /tbm/{id}/attendees               참석자 추가
  PATCH  /tbm/{id}/attendees/{aid}/sign    서명 등록
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from db.supabase_client import get_supabase

router = APIRouter(prefix="/tbm", tags=["tbm"])

VERSION = "1.1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Pydantic 모델 ─────────────────────────────────────────────

class TbmCreateBody(BaseModel):
    factory_id:            str
    company_id:            Optional[str] = None
    construction_site_id:  Optional[str] = None   # v1.1.0: 건설현장 연결
    work_date:             str                     # YYYY-MM-DD
    work_location:         Optional[str] = None
    work_description:      Optional[str] = None
    risk_items:            Optional[List[str]] = []  # 위험요인 태그
    safety_items:          Optional[List[str]] = []  # 안전수칙 태그
    conductor_name:        Optional[str] = None
    conductor_id:          Optional[str] = None
    meeting_title:         Optional[str] = None


class TbmUpdateBody(BaseModel):
    work_date:             Optional[str] = None
    work_location:         Optional[str] = None
    work_description:      Optional[str] = None
    risk_items:            Optional[List[str]] = None
    safety_items:          Optional[List[str]] = None
    conductor_name:        Optional[str] = None
    transcript_text:       Optional[str] = None
    meeting_title:         Optional[str] = None
    construction_site_id:  Optional[str] = None


class TranscribeBody(BaseModel):
    tbm_id:          str
    transcript_text: str
    audio_url:       Optional[str] = None


class AttendeeAddBody(BaseModel):
    name:      str
    worker_id: Optional[str] = None
    user_id:   Optional[str] = None
    job_type:  Optional[str] = None


class SignBody(BaseModel):
    signature_url: str


# ── 고정경로 먼저 선언 ──────────────────────────────────────────

# POST /tbm/transcribe — /{id} 앞에 선언
@router.post("/transcribe")
def save_transcript(body: TranscribeBody):
    """STT 변환 결과 저장 (Web Speech API / Whisper 모두 이 API로 수렴)."""
    supabase = get_supabase()
    chk = supabase.table("tbm_meetings").select("id").eq(
        "id", body.tbm_id
    ).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="TBM을 찾을 수 없습니다.")

    update: dict = {
        "transcript_text":   body.transcript_text,
        "transcript_status": "DONE",
        "updated_at":        _now(),
    }
    if body.audio_url:
        update["audio_url"] = body.audio_url

    res = supabase.table("tbm_meetings").update(update).eq(
        "id", body.tbm_id
    ).execute()
    return {
        "status":  "success",
        "message": "STT 텍스트가 저장되었습니다.",
        "data":    res.data[0] if res.data else {},
    }


# ── CRUD ──────────────────────────────────────────────────

@router.post("")
def create_tbm(body: TbmCreateBody):
    """TBM 생성."""
    supabase = get_supabase()
    now = _now()

    company_id = body.company_id
    if not company_id:
        fac = supabase.table("factories").select("company_id").eq(
            "id", body.factory_id
        ).limit(1).execute()
        if fac.data:
            company_id = fac.data[0].get("company_id")

    title = body.meeting_title or f"TBM {body.work_date} {body.work_location or ''}".strip()
    row = {
        "factory_id":           body.factory_id,
        "company_id":           company_id,
        "construction_site_id": body.construction_site_id,  # v1.1.0
        "meeting_title":        title,
        "work_date":            body.work_date,
        "work_location":        body.work_location,
        "work_description":     body.work_description,
        "risk_items":           body.risk_items or [],
        "safety_items":         body.safety_items or [],
        "conductor_id":         body.conductor_id,
        "conductor_name":       body.conductor_name,
        "status_code":          "DRAFT",
        "attendee_count":       0,
        "transcript_status":    "NONE",
        "created_at":           now,
        "updated_at":           now,
    }
    res = supabase.table("tbm_meetings").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="TBM 생성에 실패했습니다.")
    return {"status": "success", "message": "TBM이 생성되었습니다.", "data": res.data[0]}


@router.get("")
def list_tbm(
    factory_id:           Optional[str] = Query(None),
    company_id:           Optional[str] = Query(None),
    construction_site_id: Optional[str] = Query(None),  # v1.1.0
    status_code:          Optional[str] = Query(None),
    date_from:            Optional[str] = Query(None),
    date_to:              Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """TBM 목록 조회."""
    supabase = get_supabase()
    q = supabase.table("tbm_meetings").select(
        "id, factory_id, company_id, construction_site_id, meeting_title, work_date, "
        "work_location, conductor_name, attendee_count, status_code, "
        "transcript_status, audio_url, completed_at, created_at",
        count="exact"
    )
    if factory_id:           q = q.eq("factory_id",           factory_id)
    if company_id:           q = q.eq("company_id",           company_id)
    if construction_site_id: q = q.eq("construction_site_id", construction_site_id)  # v1.1.0
    if status_code:          q = q.eq("status_code",          status_code)
    if date_from:            q = q.gte("work_date",           date_from)
    if date_to:              q = q.lte("work_date",           date_to)

    offset = (page - 1) * size
    res = q.order("work_date", desc=True).range(offset, offset + size - 1).execute()
    total = res.count or 0
    return {
        "status": "success",
        "data": {
            "items":       res.data or [],
            "total":       total,
            "page":        page,
            "size":        size,
            "total_pages": (total + size - 1) // size if total else 0,
        }
    }


@router.get("/{tbm_id}")
def get_tbm(tbm_id: str):
    """TBM 상세 조회 (참석자 포함)."""
    supabase = get_supabase()
    res = supabase.table("tbm_meetings").select("*").eq(
        "id", tbm_id
    ).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="TBM을 찾을 수 없습니다.")

    tbm = res.data[0]
    att = supabase.table("tbm_attendees").select("*").eq(
        "meeting_id", tbm_id
    ).execute()
    tbm["attendees"] = att.data or []
    return {"status": "success", "data": tbm}


@router.patch("/{tbm_id}")
def update_tbm(tbm_id: str, body: TbmUpdateBody):
    """TBM 수정."""
    supabase = get_supabase()
    payload = {k: v for k, v in body.dict().items() if v is not None}
    if not payload:
        raise HTTPException(status_code=422, detail="수정할 내용이 없습니다.")
    payload["updated_at"] = _now()
    res = supabase.table("tbm_meetings").update(payload).eq(
        "id", tbm_id
    ).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="TBM을 찾을 수 없습니다.")
    return {"status": "success", "message": "수정되었습니다.", "data": res.data[0]}


@router.post("/{tbm_id}/complete")
def complete_tbm(tbm_id: str):
    """TBM 완료 처리."""
    supabase = get_supabase()
    now = _now()
    res = supabase.table("tbm_meetings").update({
        "status_code":  "COMPLETED",
        "completed_at": now,
        "updated_at":   now,
    }).eq("id", tbm_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="TBM을 찾을 수 없습니다.")
    return {"status": "success", "message": "완료 처리되었습니다.", "data": res.data[0]}


# ── 참석자 ─────────────────────────────────────────────────

@router.get("/{tbm_id}/attendees")
def list_attendees(tbm_id: str):
    """참석자 목록."""
    supabase = get_supabase()
    res = supabase.table("tbm_attendees").select("*").eq(
        "meeting_id", tbm_id
    ).execute()
    return {"status": "success", "data": {"items": res.data or [], "total": len(res.data or [])}}


@router.post("/{tbm_id}/attendees")
def add_attendee(tbm_id: str, body: AttendeeAddBody):
    """참석자 추가."""
    supabase = get_supabase()
    chk = supabase.table("tbm_meetings").select("id").eq(
        "id", tbm_id
    ).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="TBM을 찾을 수 없습니다.")

    now = _now()
    row = {
        "meeting_id":  tbm_id,
        "name":        body.name,
        "worker_id":   body.worker_id,
        "user_id":     body.user_id,
        "job_type":    body.job_type,
        "attended_at": now,
    }
    res = supabase.table("tbm_attendees").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="참석자 추가 실패.")

    try:
        cnt_res = supabase.table("tbm_attendees").select(
            "id", count="exact"
        ).eq("meeting_id", tbm_id).execute()
        supabase.table("tbm_meetings").update({
            "attendee_count": cnt_res.count or 0,
            "updated_at":     now,
        }).eq("id", tbm_id).execute()
    except Exception:
        pass

    return {"status": "success", "message": "참석자가 추가되었습니다.", "data": res.data[0]}


@router.patch("/{tbm_id}/attendees/{attendee_id}/sign")
def register_sign(tbm_id: str, attendee_id: str, body: SignBody):
    """전자서명 등록."""
    supabase = get_supabase()
    now = _now()
    res = supabase.table("tbm_attendees").update({
        "signature_url": body.signature_url,
        "signed_at":     now,
    }).eq("id", attendee_id).eq("meeting_id", tbm_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="참석자를 찾을 수 없습니다.")
    return {"status": "success", "message": "서명이 등록되었습니다.", "data": res.data[0]}
