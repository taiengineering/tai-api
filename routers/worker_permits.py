"""
작업자 위험성평가 참여 / 출퇴근 / 작업허가서 API — v1.0.0

작업자 PWA 가 호출하지만 서버에 부재해 404 로 실패하던 마지막 3개 경로를 신설한다.
대응 테이블은 2026-08-10 마이그레이션으로 생성했다.

API:
  POST /risk-assessments/{assessment_id}/participate  위험성평가 참여·서명 (risk.html)
  GET  /risk-assessments/{assessment_id}/participants 참여자 목록 (관리자)
  POST /attendance                                    출퇴근·현장출입 (attendance.html / qr_scan.html)
  GET  /attendance                                    본인 출입 이력
  POST /work-permits                                  작업허가 신청 (work_request.html)
  GET  /work-permits                                  허가 목록

인증은 worker_check.py 관례를 따른다 — Authorization 이 있으면 검증하고 없으면 phone 기반.
현장 작업자가 토큰 만료 상태에서도 법정 의무를 이행할 수 있어야 하기 때문이다.
"""
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from db.supabase_client import get_supabase
from services.time import now_kst, serialize_external_utc

log = logging.getLogger(__name__)
router = APIRouter(tags=["WorkerPermits"])

SIGNATURE_BUCKET = "company-docs"


def _optional_auth(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Authorization이 있으면 검증, 없으면 None 반환. (worker_check.py 와 동일 관례)"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.replace("Bearer ", "")
    supabase = get_supabase()
    try:
        ur = supabase.auth.get_user(token)
        if not ur or not ur.user:
            raise HTTPException(status_code=401, detail={"error": "AUTH_EXPIRED"})
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail={"error": "AUTH_EXPIRED"})
    res = supabase.table("users").select("*").eq("auth_id", str(ur.user.id)).limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")
    return res.data[0]


def _clean_phone(phone: str) -> str:
    return (phone or "").replace("-", "").replace(" ", "")


def _resolve_worker(phone: str):
    """전화번호로 users → worker_registry 순서로 조회. (worker_check.py 와 동일 관례)

    users.phone 은 하이픈 유무가 섞여 있어 양쪽 형식으로 조회한다.
    """
    supabase = get_supabase()
    clean = _clean_phone(phone)
    if not clean:
        return None, ""
    u = supabase.table("users").select("id, name").eq("phone", clean).limit(1).execute()
    if not u.data and len(clean) == 11:
        fmt = f"{clean[:3]}-{clean[3:7]}-{clean[7:]}"
        u = supabase.table("users").select("id, name").eq("phone", fmt).limit(1).execute()
    if u.data:
        return u.data[0]["id"], u.data[0].get("name", "")
    w = supabase.table("worker_registry").select("id, name").eq("phone", clean).limit(1).execute()
    if w.data:
        return w.data[0]["id"], w.data[0].get("name", "")
    return None, ""


def _save_signature(signature_data: str, prefix: str) -> Optional[str]:
    """base64 dataURL 서명을 Storage 에 저장하고 public URL 을 돌려준다.

    실패해도 예외를 올리지 않는다 — 서명 보관 실패가 참여 기록 자체를 막아서는 안 된다.
    """
    if not signature_data:
        return None
    try:
        import base64
        b64 = signature_data.split(",", 1)[-1]
        raw = base64.b64decode(b64)
        path = f"signatures/{prefix}/{uuid.uuid4()}.png"
        supabase = get_supabase()
        supabase.storage.from_(SIGNATURE_BUCKET).upload(
            path=path, file=raw, file_options={"content-type": "image/png"}
        )
        return supabase.storage.from_(SIGNATURE_BUCKET).get_public_url(path)
    except Exception as e:
        log.error(f"[Signature] 저장 실패 prefix={prefix}: {e}")
        return None


# ══════════════════════════════════════════
# 위험성평가 참여 — ra_participation
# ══════════════════════════════════════════

class RaParticipateBody(BaseModel):
    phone: str
    assess_id: Optional[str] = None      # 경로 파라미터와 중복되나 프론트가 함께 보낸다
    worker_id: Optional[str] = None
    agreed_risks: Optional[List[str]] = None
    extra_risks: Optional[List[str]] = None
    signature_data: Optional[str] = None
    participated_at: Optional[str] = None


@router.post("/risk-assessments/{assessment_id}/participate")
def participate_risk_assessment(
    assessment_id: str,
    body: RaParticipateBody,
    current_user: Optional[dict] = Depends(_optional_auth),
):
    """위험성평가 참여·서명 (산안법 제36조).

    같은 평가에 같은 작업자가 다시 서명하면 기존 행을 갱신한다.
    (assessment_id, phone) 유니크 인덱스가 중복 행을 막는다.
    """
    supabase = get_supabase()
    clean = _clean_phone(body.phone)

    exist = supabase.table("risk_assessments").select("id").eq("id", assessment_id).limit(1).execute()
    if not exist.data:
        raise HTTPException(status_code=404, detail="위험성평가를 찾을 수 없습니다")

    worker_id = body.worker_id or (current_user["id"] if current_user else None)
    worker_name = ""
    if not worker_id:
        worker_id, worker_name = _resolve_worker(clean)
    elif current_user:
        worker_name = current_user.get("name", "")

    signature_url = _save_signature(body.signature_data, "ra")

    row = {
        "assessment_id": assessment_id,
        "worker_id": worker_id,
        "phone": clean,
        "worker_name": worker_name or None,
        "agreed_json": body.agreed_risks or [],
        "extra_json": body.extra_risks or [],
        "signature_url": signature_url,
        "review_status": "PENDING",
    }
    if body.participated_at:
        row["participated_at"] = body.participated_at

    prev = supabase.table("ra_participation").select("id") \
        .eq("assessment_id", assessment_id).eq("phone", clean).limit(1).execute()

    if prev.data:
        # 재서명 — 기존 행 갱신. 검토 상태는 다시 PENDING 으로 되돌린다.
        row["updated_at"] = serialize_external_utc(now_kst())
        res = supabase.table("ra_participation").update(row).eq("id", prev.data[0]["id"]).execute()
        saved_id = prev.data[0]["id"]
    else:
        res = supabase.table("ra_participation").insert(row).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="참여 기록 저장에 실패했습니다")
        saved_id = res.data[0]["id"]

    log.info(f"[RaParticipate] 저장 assessment={assessment_id} phone={clean} "
             f"extra={len(body.extra_risks or [])}")

    return {
        "status": "success",
        "message": "위험성평가 참여가 기록됐습니다.",
        "data": {"id": saved_id, "assessment_id": assessment_id},
    }


@router.get("/risk-assessments/{assessment_id}/participants")
def list_ra_participants(
    assessment_id: str,
    review_status: Optional[str] = Query(None, description="PENDING|ADOPTED|REJECTED"),
):
    """참여자 목록. 관리자가 작업자 발굴 위험요인(extra_json)을 검토할 때 쓴다."""
    supabase = get_supabase()
    q = supabase.table("ra_participation").select("*").eq("assessment_id", assessment_id)
    if review_status:
        q = q.eq("review_status", review_status)
    res = q.order("participated_at", desc=True).execute()
    items = res.data or []
    return {"status": "success", "data": {"items": items, "total": len(items)}}


# ══════════════════════════════════════════
# 출퇴근 / 현장 출입 — worker_attendance
# ══════════════════════════════════════════

class AttendanceBody(BaseModel):
    phone: str
    entry_type: str                       # IN | OUT
    method: Optional[str] = "GPS"         # GPS | QR | MANUAL
    worker_id: Optional[str] = None
    worker_name: Optional[str] = None
    company_id: Optional[str] = None
    factory_id: Optional[str] = None
    site_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_text: Optional[str] = None
    qr_code: Optional[str] = None
    recorded_at: Optional[str] = None


@router.post("/attendance")
def create_attendance(
    body: AttendanceBody,
    current_user: Optional[dict] = Depends(_optional_auth),
):
    """출퇴근·현장 출입 기록. attendance.html(GPS)과 qr_scan.html(QR) 양쪽이 쓴다."""
    supabase = get_supabase()
    clean = _clean_phone(body.phone)

    entry_type = (body.entry_type or "").upper()
    if entry_type not in ("IN", "OUT"):
        raise HTTPException(status_code=400, detail="entry_type 은 IN 또는 OUT 이어야 합니다")

    method = (body.method or "GPS").upper()
    if method not in ("GPS", "QR", "MANUAL"):
        method = "GPS"

    worker_id = body.worker_id or (current_user["id"] if current_user else None)
    worker_name = body.worker_name or ""
    if not worker_id:
        worker_id, resolved_name = _resolve_worker(clean)
        worker_name = worker_name or resolved_name

    row = {
        "worker_id": worker_id,
        "phone": clean,
        "worker_name": worker_name or None,
        "company_id": body.company_id,
        "factory_id": body.factory_id,
        "site_id": body.site_id,
        "entry_type": entry_type,
        "method": method,
        "latitude": body.latitude,
        "longitude": body.longitude,
        "location_text": body.location_text,
        "qr_code": body.qr_code,
    }
    if body.recorded_at:
        row["recorded_at"] = body.recorded_at

    res = supabase.table("worker_attendance").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="출입 기록 저장에 실패했습니다")

    log.info(f"[Attendance] {entry_type} phone={clean} method={method}")

    return {
        "status": "success",
        "message": "출근 기록됐습니다." if entry_type == "IN" else "퇴근 기록됐습니다.",
        "data": {"id": res.data[0]["id"], "entry_type": entry_type, "method": method},
    }


@router.get("/attendance")
def list_attendance(
    phone: str = Query(..., description="작업자 전화번호"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(100, le=500),
):
    """본인 출입 이력. 달력·월별 집계 화면이 쓴다."""
    supabase = get_supabase()
    clean = _clean_phone(phone)

    q = supabase.table("worker_attendance").select("*").eq("phone", clean)
    if date_from:
        q = q.gte("recorded_at", f"{date_from}T00:00:00")
    if date_to:
        q = q.lte("recorded_at", f"{date_to}T23:59:59")
    res = q.order("recorded_at", desc=True).limit(limit).execute()
    items = res.data or []
    return {"status": "success", "data": {"items": items, "total": len(items)}}


# ══════════════════════════════════════════
# 작업허가서 — work_permits
# ══════════════════════════════════════════

class WorkPermitBody(BaseModel):
    phone: str
    work_type: str                        # height|fire|confined|electric|crane|other
    description: str
    requester_id: Optional[str] = None
    requester_name: Optional[str] = None
    company_id: Optional[str] = None
    factory_id: Optional[str] = None
    site_id: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    workers: Optional[List[str]] = None
    safety_checks: Optional[List[str]] = None
    requested_at: Optional[str] = None


VALID_WORK_TYPES = ("height", "fire", "confined", "electric", "crane", "other")


@router.post("/work-permits")
def create_work_permit(
    body: WorkPermitBody,
    current_user: Optional[dict] = Depends(_optional_auth),
):
    """작업허가 신청 (Permit-to-Work).

    프론트는 응답의 permit_number 를 화면에 표시하므로 반드시 반환해야 한다.
    """
    supabase = get_supabase()
    clean = _clean_phone(body.phone)

    work_type = (body.work_type or "").lower()
    if work_type not in VALID_WORK_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"work_type 은 {', '.join(VALID_WORK_TYPES)} 중 하나여야 합니다",
        )

    requester_id = body.requester_id or (current_user["id"] if current_user else None)
    requester_name = body.requester_name or ""
    if not requester_id:
        requester_id, resolved_name = _resolve_worker(clean)
        requester_name = requester_name or resolved_name

    today = now_kst().strftime("%Y%m%d")
    permit_number = f"WRQ-{today}-{random.randint(100000, 999999)}"

    row = {
        "permit_number": permit_number,
        "company_id": body.company_id,
        "factory_id": body.factory_id,
        "site_id": body.site_id,
        "requester_id": requester_id,
        "requester_phone": clean,
        "requester_name": requester_name or None,
        "work_type": work_type,
        "description": body.description,
        "start_time": body.start_time,
        "end_time": body.end_time,
        "workers_json": body.workers or [],
        "safety_checks_json": body.safety_checks or [],
        "status": "REQUESTED",
    }

    res = supabase.table("work_permits").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="작업허가 신청 저장에 실패했습니다")

    log.info(f"[WorkPermit] 신청 {permit_number} phone={clean} type={work_type}")

    return {
        "status": "success",
        "message": "작업허가 신청이 접수됐습니다.",
        "permit_number": permit_number,
        "data": {
            "id": res.data[0]["id"],
            "permit_number": permit_number,
            "status": "REQUESTED",
        },
    }


@router.get("/work-permits")
def list_work_permits(
    phone: Optional[str] = Query(None, description="신청자 전화번호"),
    factory_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="CSV 다중값 허용"),
    limit: int = Query(50, le=200),
):
    """작업허가 목록. 작업자는 본인 신청 이력을, 관리자는 승인 대기 건을 조회한다."""
    supabase = get_supabase()

    q = supabase.table("work_permits").select("*")
    if phone:
        q = q.eq("requester_phone", _clean_phone(phone))
    if factory_id:
        q = q.eq("factory_id", factory_id)
    if site_id:
        q = q.eq("site_id", site_id)
    if status:
        codes = [s.strip().upper() for s in status.split(",") if s.strip()]
        if len(codes) == 1:
            q = q.eq("status", codes[0])
        elif codes:
            q = q.in_("status", codes)

    res = q.order("created_at", desc=True).limit(limit).execute()
    items = res.data or []
    return {"status": "success", "data": {"items": items, "total": len(items)}}
