"""
TBM(작업 전 안전점검회의) 관리 라우터 — v1.2.0

v1.2.0 (2026-04-08):
  [ADD] GET  /tbm/{id}/sign-info  서명의 페이지 정보 (JWT 불필요)
  [ADD] POST /tbm/{id}/sign       전자서명 (base64 → Storage 업로드)
  [ADD] POST /tbm/{id}/request-sign  참석자 FCM 서명요청 발송

v1.1.0 (2026-04-07 Phase 3):
  - construction_site_id 콓럼 추가, 필터 지원

tbm_meetings, tbm_attendees 테이블 사용

API:
  POST   /tbm                              TBM 생성
  GET    /tbm                              목록 조회
  POST   /tbm/transcribe                   STT 텍스트 저장
  GET    /tbm/{id}/sign-info               서명 페이지 정보 (JWT 불필요)← v1.2.0
  POST   /tbm/{id}/sign                    전자서명 저장          ← v1.2.0
  POST   /tbm/{id}/request-sign            FCM 서명요청 발송     ← v1.2.0
  GET    /tbm/{id}                         상세 조회
  PATCH  /tbm/{id}                         수정
  POST   /tbm/{id}/complete                완료 처리
  GET    /tbm/{id}/attendees               참석자 목록
  POST   /tbm/{id}/attendees               참석자 추가
  PATCH  /tbm/{id}/attendees/{aid}/sign    서명 등록 (구버전 호환용)
"""
import base64
import logging
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)

router = APIRouter(prefix="/tbm", tags=["tbm"])

VERSION = "1.2.0"

STORAGE_BUCKET = "signatures"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Pydantic 모델 ────────────────────────────────────────

class TbmCreateBody(BaseModel):
    factory_id:            str
    company_id:            Optional[str] = None
    construction_site_id:  Optional[str] = None
    work_date:             str
    work_location:         Optional[str] = None
    work_description:      Optional[str] = None
    risk_items:            Optional[List[str]] = []
    safety_items:          Optional[List[str]] = []
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
    """v1.1.0 호환 레거시 서명 body."""
    signature_url: str


class MobileSignBody(BaseModel):
    """v1.2.0: base64 PNG 서명 데이터 업로드."""
    attendee_id:    str
    signature_data: str    # data:image/png;base64,... 또는 순수 base64


class RequestSignBody(BaseModel):
    """v1.2.0: FCM 서명요청 발송."""
    attendee_ids: List[str]


# ── 고정경로 먼저 선언 (/{id} 보다 앞에) ──────────────

@router.post("/transcribe")
def save_transcript(body: TranscribeBody):
    """STT 변환 결과 저장."""
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
    return {"status": "success", "message": "STT 텍스트가 저장되었습니다.",
            "data": res.data[0] if res.data else {}}


# ── v1.2.0: 서명 관련 엔드포인트 ─────────────────────────
# 주의: /{tbm_id}/sign-info, /{tbm_id}/sign, /{tbm_id}/request-sign 은
#         /{tbm_id}/attendees 보다 먼저 선언해야 라우트 충돌 없음
#         (FastAPI는 조건부 URL에서 별도 세그먼트라 충돌 안 남)

@router.get("/{tbm_id}/sign-info")
def get_sign_info(
    tbm_id:     str,
    attendee_id: str = Query(..., description="참석자 UUID"),
):
    """
    v1.2.0: 서명 페이지 기본 정보 조회 (JWT 불필요 — 비공개 링크 방식).
    TBM 정보 + 해당 참석자 정보 반환.
    """
    supabase = get_supabase()

    tbm_res = supabase.table("tbm_meetings").select(
        "id, meeting_title, work_date, work_location, work_description, "
        "conductor_name, status_code"
    ).eq("id", tbm_id).limit(1).execute()
    if not tbm_res.data:
        raise HTTPException(status_code=404, detail="TBM을 찾을 수 없습니다.")

    att_res = supabase.table("tbm_attendees").select(
        "id, name, job_type, sign_status, signature_url, signed_at_final"
    ).eq("id", attendee_id).eq("meeting_id", tbm_id).limit(1).execute()
    if not att_res.data:
        raise HTTPException(status_code=404, detail="참석자를 찾을 수 없습니다.")

    return {
        "status": "success",
        "data": {
            "tbm":      tbm_res.data[0],
            "attendee": att_res.data[0],
        },
    }


@router.post("/{tbm_id}/sign")
def submit_sign(tbm_id: str, body: MobileSignBody):
    """
    v1.2.0: 전자서명 저장 (JWT 불필요).

    1. base64 데코딩 (data URI 포함 가능)
    2. Supabase Storage 'signatures' 버킷에 업로드
       경로: tbm/{tbm_id}/{attendee_id}.png
    3. tbm_attendees UPDATE
    4. 서명완료수 업데이트
    """
    supabase = get_supabase()
    now = _now()

    # 1. base64 데코딩
    raw = body.signature_data
    if raw.startswith("data:"):
        raw = raw.split(",", 1)[-1]
    try:
        img_bytes = base64.b64decode(raw)
    except Exception:
        raise HTTPException(status_code=422, detail="서명 이미지 base64 파싱 실패")

    # 2. Storage 업로드
    storage_path = f"tbm/{tbm_id}/{body.attendee_id}.png"
    try:
        storage_res = supabase.storage.from_(STORAGE_BUCKET).upload(
            path=storage_path,
            file=img_bytes,
            file_options={"content-type": "image/png", "upsert": "true"},
        )
        # 업로드 성공 시 public URL 추출
        pub_url = supabase.storage.from_(STORAGE_BUCKET).get_public_url(storage_path)
    except Exception as e:
        log.error(f"[TBM SIGN] Storage 업로드 실패: {e}")
        raise HTTPException(status_code=500, detail=f"Storage 업로드 실패: {e}")

    # 3. tbm_attendees UPDATE
    att_res = supabase.table("tbm_attendees").update({
        "signature_url":  pub_url,
        "sign_status":    "SIGNED",
        "signed_at_final": now,
        "signed_at":      now,
    }).eq("id", body.attendee_id).eq("meeting_id", tbm_id).execute()
    if not att_res.data:
        raise HTTPException(status_code=404, detail="참석자를 찾을 수 없습니다.")

    # 4. 서명완료 수 업데이트
    try:
        signed_cnt = supabase.table("tbm_attendees").select(
            "id", count="exact"
        ).eq("meeting_id", tbm_id).eq("sign_status", "SIGNED").execute()
        supabase.table("tbm_meetings").update({
            "updated_at": now,
        }).eq("id", tbm_id).execute()
    except Exception:
        pass

    return {"status": "success", "ok": True, "signature_url": pub_url}


@router.post("/{tbm_id}/request-sign")
def request_sign(tbm_id: str, body: RequestSignBody):
    """
    v1.2.0: 선택된 참석자에게 FCM 서명요청 푸시 발송.

    1. attendee_ids 순회
    2. worker_id → worker_registry.push_token 조회
    3. FCM 발송
    4. tbm_attendees.push_sent_at 업데이트
    """
    supabase = get_supabase()
    now = _now()

    # TBM 정보 조회 (알림 내용용)
    tbm_res = supabase.table("tbm_meetings").select(
        "id, work_date, work_location"
    ).eq("id", tbm_id).limit(1).execute()
    if not tbm_res.data:
        raise HTTPException(status_code=404, detail="TBM을 찾을 수 없습니다.")
    tbm = tbm_res.data[0]
    work_date     = tbm.get("work_date", "")[:10]
    work_location = tbm.get("work_location", "")

    try:
        from utils.fcm_utils import send_push
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"FCM 유틸리티 로드 실패: {e}")

    sent = 0
    failed = 0

    for attendee_id in body.attendee_ids:
        # 참석자 + worker_id 조회
        att_res = supabase.table("tbm_attendees").select(
            "id, name, worker_id"
        ).eq("id", attendee_id).eq("meeting_id", tbm_id).limit(1).execute()
        if not att_res.data:
            failed += 1
            continue

        att = att_res.data[0]
        worker_id = att.get("worker_id")
        if not worker_id:
            failed += 1
            continue

        # push_token 조회
        wr_res = supabase.table("worker_registry").select("push_token") \
            .eq("id", worker_id).limit(1).execute()
        if not wr_res.data or not wr_res.data[0].get("push_token"):
            failed += 1
            continue

        push_token = wr_res.data[0]["push_token"]
        try:
            send_push(
                fcm_token=push_token,
                title="[TAI Safe] TBM 서명 요청",
                body=f"{work_date} {work_location} TBM 서명 요청이 왔습니다.",
                data={
                    "type":        "tbm_sign",
                    "tbm_id":      tbm_id,
                    "attendee_id": attendee_id,
                },
            )
            # push_sent_at 업데이트
            supabase.table("tbm_attendees").update({
                "push_sent_at": now,
            }).eq("id", attendee_id).execute()
            sent += 1
        except Exception as e:
            log.error(f"[TBM] FCM 실패 attendee_id={attendee_id}: {e}")
            failed += 1

    return {
        "status": "success",
        "data":   {"sent": sent, "failed": failed},
    }


# ── CRUD ──────────────────────────────────────────────────

@router.post("")
def create_tbm(body: TbmCreateBody):
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
        "construction_site_id": body.construction_site_id,
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
    construction_site_id: Optional[str] = Query(None),
    status_code:          Optional[str] = Query(None),
    date_from:            Optional[str] = Query(None),
    date_to:              Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    supabase = get_supabase()
    q = supabase.table("tbm_meetings").select(
        "id, factory_id, company_id, construction_site_id, meeting_title, work_date, "
        "work_location, conductor_name, attendee_count, status_code, "
        "transcript_status, audio_url, completed_at, created_at",
        count="exact"
    )
    if factory_id:           q = q.eq("factory_id",           factory_id)
    if company_id:           q = q.eq("company_id",           company_id)
    if construction_site_id: q = q.eq("construction_site_id", construction_site_id)
    if status_code:          q = q.eq("status_code",          status_code)
    if date_from:            q = q.gte("work_date",           date_from)
    if date_to:              q = q.lte("work_date",           date_to)
    offset = (page - 1) * size
    res = q.order("work_date", desc=True).range(offset, offset + size - 1).execute()
    total = res.count or 0
    return {"status": "success", "data": {
        "items": res.data or [], "total": total,
        "page": page, "size": size,
        "total_pages": (total + size - 1) // size if total else 0,
    }}


@router.get("/{tbm_id}")
def get_tbm(tbm_id: str):
    supabase = get_supabase()
    res = supabase.table("tbm_meetings").select("*").eq("id", tbm_id).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="TBM을 찾을 수 없습니다.")
    tbm = res.data[0]
    att = supabase.table("tbm_attendees").select("*").eq("meeting_id", tbm_id).execute()
    tbm["attendees"] = att.data or []
    return {"status": "success", "data": tbm}


@router.patch("/{tbm_id}")
def update_tbm(tbm_id: str, body: TbmUpdateBody):
    supabase = get_supabase()
    payload = {k: v for k, v in body.dict().items() if v is not None}
    if not payload:
        raise HTTPException(status_code=422, detail="수정할 내용이 없습니다.")
    payload["updated_at"] = _now()
    res = supabase.table("tbm_meetings").update(payload).eq("id", tbm_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="TBM을 찾을 수 없습니다.")
    return {"status": "success", "message": "수정되었습니다.", "data": res.data[0]}


@router.post("/{tbm_id}/complete")
def complete_tbm(tbm_id: str):
    supabase = get_supabase()
    now = _now()
    res = supabase.table("tbm_meetings").update({
        "status_code": "COMPLETED", "completed_at": now, "updated_at": now,
    }).eq("id", tbm_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="TBM을 찾을 수 없습니다.")
    return {"status": "success", "message": "완료 처리되었습니다.", "data": res.data[0]}


@router.get("/{tbm_id}/attendees")
def list_attendees(tbm_id: str):
    supabase = get_supabase()
    res = supabase.table("tbm_attendees").select("*").eq("meeting_id", tbm_id).execute()
    return {"status": "success", "data": {"items": res.data or [], "total": len(res.data or [])}}


@router.post("/{tbm_id}/attendees")
def add_attendee(tbm_id: str, body: AttendeeAddBody):
    supabase = get_supabase()
    chk = supabase.table("tbm_meetings").select("id").eq("id", tbm_id).limit(1).execute()
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
            "attendee_count": cnt_res.count or 0, "updated_at": now,
        }).eq("id", tbm_id).execute()
    except Exception:
        pass
    return {"status": "success", "message": "참석자가 추가되었습니다.", "data": res.data[0]}


@router.patch("/{tbm_id}/attendees/{attendee_id}/sign")
def register_sign(tbm_id: str, attendee_id: str, body: SignBody):
    """v1.1.0 레거시 서명 URL 등록 (호환 유지)."""
    supabase = get_supabase()
    now = _now()
    res = supabase.table("tbm_attendees").update({
        "signature_url": body.signature_url,
        "sign_status":   "SIGNED",
        "signed_at":     now,
    }).eq("id", attendee_id).eq("meeting_id", tbm_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="참석자를 찾을 수 없습니다.")
    return {"status": "success", "message": "서명이 등록되었습니다.", "data": res.data[0]}
