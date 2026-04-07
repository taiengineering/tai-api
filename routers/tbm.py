"""
TBM(작업 전 안전점검회의) 관리 라우터 — v1.2.0

v1.2.0 (2026-04-08 FCM 연동):
  - GET  /tbm/{id}/sign-info          서명용 페이지 정보 (인증 불필요)
  - POST /tbm/{id}/sign               base64 서명 업로드 + tbm_attendees 업데이트
  - POST /tbm/{id}/request-sign       참석자 FCM 서명 요청 발송

v1.1.0 (2026-04-07 Phase 3):
  - construction_site_id 지원

tbm_meetings, tbm_attendees 테이블 사용

API:
  POST   /tbm                                TBM 생성
  GET    /tbm                                목록 조회
  POST   /tbm/transcribe                     STT 저장
  GET    /tbm/{id}                           상세 조회
  PATCH  /tbm/{id}                           수정
  POST   /tbm/{id}/complete                  완료 처리
  GET    /tbm/{id}/sign-info                 서명 페이지 정보 ← v1.2.0
  POST   /tbm/{id}/sign                      서명 업로드   ← v1.2.0
  POST   /tbm/{id}/request-sign              FCM 서명 요청 ← v1.2.0
  GET    /tbm/{id}/attendees                 참석자 목록
  POST   /tbm/{id}/attendees                 참석자 추가
  PATCH  /tbm/{id}/attendees/{aid}/sign      서명 URL 등록 (구버전)
"""
import base64
import logging
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase

router = APIRouter(prefix="/tbm", tags=["tbm"])
VERSION = "1.2.0"
log = logging.getLogger(__name__)

STORAGE_BUCKET = "signatures"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Pydantic 모델 ─────────────────────────────────────────────

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


class SignUrlBody(BaseModel):
    """(v1.1.0) 스토리지 URL 직접 저장."""
    signature_url: str


class SignUploadBody(BaseModel):
    """(v1.2.0) base64 서명 업로드."""
    attendee_id:    str
    signature_data: str   # data:image/png;base64,... 또는 순수 base64


class RequestSignBody(BaseModel):
    """(v1.2.0) FCM 서명 요청."""
    attendee_ids: List[str]


# ── 고정경로 먼저 선언 (패리미터 라우트 앞에) ─────────────

@router.post("/transcribe")
def save_transcript(body: TranscribeBody):
    """STT 변환 결과 저장."""
    supabase = get_supabase()
    chk = supabase.table("tbm_meetings").select("id").eq("id", body.tbm_id).limit(1).execute()
    if not chk.data:
        raise HTTPException(status_code=404, detail="TBM을 찾을 수 없습니다.")
    update: dict = {
        "transcript_text":   body.transcript_text,
        "transcript_status": "DONE",
        "updated_at":        _now(),
    }
    if body.audio_url:
        update["audio_url"] = body.audio_url
    res = supabase.table("tbm_meetings").update(update).eq("id", body.tbm_id).execute()
    return {"status": "success", "message": "STT 텍스트가 저장되었습니다.", "data": res.data[0] if res.data else {}}


# ── CRUD ─────────────────────────────────────────────────

@router.post("")
def create_tbm(body: TbmCreateBody):
    supabase = get_supabase()
    now = _now()
    company_id = body.company_id
    if not company_id:
        fac = supabase.table("factories").select("company_id").eq("id", body.factory_id).limit(1).execute()
        if fac.data:
            company_id = fac.data[0].get("company_id")
    title = body.meeting_title or f"TBM {body.work_date} {body.work_location or ''}".strip()
    row = {
        "factory_id": body.factory_id, "company_id": company_id,
        "construction_site_id": body.construction_site_id,
        "meeting_title": title, "work_date": body.work_date,
        "work_location": body.work_location, "work_description": body.work_description,
        "risk_items": body.risk_items or [], "safety_items": body.safety_items or [],
        "conductor_id": body.conductor_id, "conductor_name": body.conductor_name,
        "status_code": "DRAFT", "attendee_count": 0, "transcript_status": "NONE",
        "created_at": now, "updated_at": now,
    }
    res = supabase.table("tbm_meetings").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="TBM 생성 실패")
    return {"status": "success", "message": "TBM이 생성되었습니다.", "data": res.data[0]}


@router.get("")
def list_tbm(
    factory_id: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
    construction_site_id: Optional[str] = Query(None),
    status_code: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
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
    if factory_id:           q = q.eq("factory_id", factory_id)
    if company_id:           q = q.eq("company_id", company_id)
    if construction_site_id: q = q.eq("construction_site_id", construction_site_id)
    if status_code:          q = q.eq("status_code", status_code)
    if date_from:            q = q.gte("work_date", date_from)
    if date_to:              q = q.lte("work_date", date_to)
    offset = (page - 1) * size
    res = q.order("work_date", desc=True).range(offset, offset + size - 1).execute()
    total = res.count or 0
    return {"status": "success", "data": {
        "items": res.data or [], "total": total, "page": page, "size": size,
        "total_pages": (total + size - 1) // size if total else 0,
    }}


# ── /{tbm_id} 하위 고정경로 먼저 (/{tbm_id} 파라미터보다 앞에) ──
# 주의: FastAPI는 같은 prefix 내에서 고정 세그먼트를 파라미터 라우트와 자동 연결.
# /{tbm_id}/sign-info, /{tbm_id}/sign, /{tbm_id}/request-sign 은
# /{tbm_id} 보다 구체적이므로 충돌 없음.

@router.get("/{tbm_id}/sign-info")
def get_sign_info(
    tbm_id: str,
    attendee_id: Optional[str] = Query(None),
):
    """
    v1.2.0: 서명 페이지 정보 조회 (인증 불필요, 비공개 링크 방식).
    tbm_meetings + tbm_attendees 데이터 반환.
    """
    supabase = get_supabase()
    tbm_res = supabase.table("tbm_meetings").select(
        "id, meeting_title, work_date, work_location, work_description, status_code, conductor_name"
    ).eq("id", tbm_id).limit(1).execute()
    if not tbm_res.data:
        raise HTTPException(status_code=404, detail="TBM을 찾을 수 없습니다.")

    attendee = None
    if attendee_id:
        att_res = supabase.table("tbm_attendees").select(
            "id, name, job_type, sign_status, signed_at_final, signature_url, push_sent_at"
        ).eq("id", attendee_id).eq("meeting_id", tbm_id).limit(1).execute()
        if att_res.data:
            attendee = att_res.data[0]

    return {
        "status": "success",
        "data": {
            "tbm":      tbm_res.data[0],
            "attendee": attendee,
        },
    }


@router.post("/{tbm_id}/sign")
def sign_tbm(
    tbm_id: str,
    body: SignUploadBody,
):
    """
    v1.2.0: base64 서명 이미지 업로드 후 tbm_attendees 업데이트.

    로직:
    1. base64 디코딩 (데이터 URI 헤더 제거)
    2. Supabase Storage 'signatures' 버킷에 업로드
       경로: tbm/{tbm_id}/{attendee_id}.png
    3. tbm_attendees UPDATE: signature_url, sign_status='SIGNED', signed_at_final
    """
    supabase = get_supabase()
    now = _now()

    # attendee 존재 확인
    att_res = supabase.table("tbm_attendees").select("id") \
        .eq("id", body.attendee_id).eq("meeting_id", tbm_id).limit(1).execute()
    if not att_res.data:
        raise HTTPException(status_code=404, detail="참석자를 찾을 수 없습니다.")

    # base64 디코딩
    sig_data = body.signature_data
    if "," in sig_data:
        sig_data = sig_data.split(",", 1)[1]  # data:image/png;base64, 헤더 제거
    try:
        img_bytes = base64.b64decode(sig_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"base64 디코딩 실패: {e}")

    # Supabase Storage 업로드
    storage_path = f"tbm/{tbm_id}/{body.attendee_id}.png"
    try:
        supabase.storage.from_(STORAGE_BUCKET).upload(
            path=storage_path,
            file=img_bytes,
            file_options={"content-type": "image/png", "upsert": "true"},
        )
    except Exception as e:
        log.error(f"[TBM SIGN] Storage 업로드 실패: {e}")
        raise HTTPException(status_code=500, detail=f"서명 이미지 업로드 실패: {e}")

    # 공개 URL 생성
    try:
        url_res = supabase.storage.from_(STORAGE_BUCKET).get_public_url(storage_path)
        signature_url = url_res if isinstance(url_res, str) else url_res.get("publicUrl", "")
    except Exception:
        signature_url = storage_path  # fallback

    # tbm_attendees 업데이트
    supabase.table("tbm_attendees").update({
        "signature_url":  signature_url,
        "sign_status":    "SIGNED",
        "signed_at_final": now,
        "signed_at":      now,
    }).eq("id", body.attendee_id).execute()

    # tbm_meetings 서명 완료 수 업데이트 (선택적)
    try:
        signed_cnt = supabase.table("tbm_attendees").select("id", count="exact") \
            .eq("meeting_id", tbm_id).eq("sign_status", "SIGNED").execute()
        supabase.table("tbm_meetings").update({
            "updated_at": now,
        }).eq("id", tbm_id).execute()
    except Exception:
        pass

    return {"ok": True, "signature_url": signature_url}


@router.post("/{tbm_id}/request-sign")
def request_sign(
    tbm_id: str,
    body: RequestSignBody,
):
    """
    v1.2.0: 참석자에게 FCM 서명 요청 알림 발송.

    로직:
    1. tbm_meetings 조회 (work_date, work_location)
    2. attendee_ids 순회
    3. attendee.worker_id → worker_registry.push_token 조회
    4. FCM 발송
    5. tbm_attendees.push_sent_at 업데이트
    """
    supabase = get_supabase()
    now = _now()

    # TBM 정보 조회
    tbm_res = supabase.table("tbm_meetings").select(
        "work_date, work_location"
    ).eq("id", tbm_id).limit(1).execute()
    if not tbm_res.data:
        raise HTTPException(status_code=404, detail="TBM을 찾을 수 없습니다.")
    tbm = tbm_res.data[0]
    push_body = f"{tbm.get('work_date', '')} {tbm.get('work_location', '')} TBM 서명 요청이 왔습니다.".strip()

    # FCM 유틸리티 import (야서 임포트해야 FIREBASE_CREDENTIALS 로드 실패 대비)
    try:
        from utils.fcm_utils import send_push_safe
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    sent = 0
    failed = 0

    for attendee_id in body.attendee_ids:
        # attendee 조회
        att_res = supabase.table("tbm_attendees").select(
            "id, worker_id"
        ).eq("id", attendee_id).eq("meeting_id", tbm_id).limit(1).execute()
        if not att_res.data:
            failed += 1
            continue
        att = att_res.data[0]
        worker_id = att.get("worker_id")

        # push_token 조회
        push_token = None
        if worker_id:
            wr = supabase.table("worker_registry").select("push_token") \
                .eq("id", worker_id).limit(1).execute()
            if wr.data:
                push_token = wr.data[0].get("push_token")

        if not push_token:
            log.warning(f"[TBM] push_token 없음 attendee_id={attendee_id}")
            failed += 1
            continue

        result = send_push_safe(
            fcm_token=push_token,
            title="[TAI Safe] TBM 서명 요청",
            body=push_body,
            data={
                "type":        "tbm_sign",
                "tbm_id":      tbm_id,
                "attendee_id": attendee_id,
            },
        )

        if result["ok"]:
            sent += 1
            # push_sent_at 업데이트
            try:
                supabase.table("tbm_attendees").update({
                    "push_sent_at":     now,
                    "sign_requested_at": now,
                }).eq("id", attendee_id).execute()
            except Exception:
                pass
        else:
            failed += 1

    return {
        "status": "success",
        "data":   {"sent": sent, "failed": failed},
    }


# ── /{tbm_id} 이하 일반 엔드포인트 ─────────────────────

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
        "meeting_id": tbm_id, "name": body.name,
        "worker_id": body.worker_id, "user_id": body.user_id,
        "job_type": body.job_type, "attended_at": now,
    }
    res = supabase.table("tbm_attendees").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="참석자 추가 실패.")
    try:
        cnt_res = supabase.table("tbm_attendees").select("id", count="exact").eq("meeting_id", tbm_id).execute()
        supabase.table("tbm_meetings").update({"attendee_count": cnt_res.count or 0, "updated_at": now}).eq("id", tbm_id).execute()
    except Exception:
        pass
    return {"status": "success", "message": "참석자가 추가되었습니다.", "data": res.data[0]}


@router.patch("/{tbm_id}/attendees/{attendee_id}/sign")
def register_sign(tbm_id: str, attendee_id: str, body: SignUrlBody):
    """(v1.1.0) 서명 URL 직접 등록 (구버전 호환 유지)."""
    supabase = get_supabase()
    now = _now()
    res = supabase.table("tbm_attendees").update({
        "signature_url": body.signature_url,
        "signed_at":     now,
        "sign_status":   "SIGNED",
    }).eq("id", attendee_id).eq("meeting_id", tbm_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="참석자를 찾을 수 없습니다.")
    return {"status": "success", "message": "서명이 등록되었습니다.", "data": res.data[0]}
