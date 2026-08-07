"""
작업자 사진 업로드 / 배정업무 / 교육이수 API — v1.0.0

작업자 PWA 가 호출하지만 서버에 부재해 404 로 실패하던 경로를 신설한다.
테이블은 모두 이미 존재하므로 DDL 변경은 없다.

API:
  POST /uploads/inspection-photo   현장 사진 업로드 (_utils.js TAI.uploadPhoto)
  GET  /work-assignments           배정업무 조회 (index.html 미이행 배너)
  POST /education/worker-complete  교육 이수 확인 (education.html)

사진 업로드가 기존 /documents/upload 를 쓰지 못하는 이유:
  documents 계약은 company_id 를 Form 필수로 요구하는데 작업자 앱은 이를 보내지 않는다.
  또한 documents 는 회사 문서관리 테이블이고, 현장 사진은 is_photo·gps_*·taken_at·
  exif_json 을 갖춘 attachments 가 용도에 맞다.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel

from db.supabase_client import get_supabase

log = logging.getLogger(__name__)
router = APIRouter(tags=["WorkerAssets"])

PHOTO_BUCKET = "company-docs"


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
    """전화번호로 users → worker_registry 순서로 조회. (worker_check.py 와 동일 관례)"""
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


# ══════════════════════════════════════════
# 현장 사진 업로드 — attachments
# ══════════════════════════════════════════

@router.post("/uploads/inspection-photo")
async def upload_inspection_photo(
    file: UploadFile = File(...),
    context: str = Form(...),
    inspection_id: Optional[str] = Form(None),
    factory_id: Optional[str] = Form(None),
    site_id: Optional[str] = Form(None),
    current_user: Optional[dict] = Depends(_optional_auth),
):
    """현장 사진 업로드.

    프론트(_utils.js TAI.uploadPhoto)는 file·context 와 선택적 id 들을 FormData 로 보내고
    응답의 url 을 photo_urls 에 담아 신고·점검 제출에 함께 전송한다.
    따라서 응답에 url 을 반드시 포함해야 한다.
    """
    supabase = get_supabase()

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="빈 파일입니다")

    file_name = file.filename or "photo.jpg"
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "jpg"
    mime = file.content_type or "image/jpeg"

    now = datetime.now(timezone.utc)
    storage_path = f"worker-photos/{context}/{now.strftime('%Y-%m')}/{uuid.uuid4()}.{ext}"

    try:
        supabase.storage.from_(PHOTO_BUCKET).upload(
            path=storage_path,
            file=contents,
            file_options={"content-type": mime},
        )
    except Exception as e:
        log.error(f"[UploadPhoto] Storage 업로드 실패 path={storage_path}: {e}")
        raise HTTPException(status_code=500, detail="사진 업로드에 실패했습니다")

    public_url = supabase.storage.from_(PHOTO_BUCKET).get_public_url(storage_path)

    # attachments 는 현장 사진용 컬럼(is_photo·gps_*·taken_at·exif_json)을 갖춘 테이블이다.
    # record_id 는 uuid 컬럼이라 inspection_id 가 uuid 가 아니면 넣지 않는다.
    row = {
        "table_name": context,
        "file_category": "inspection_photo",
        "file_url": public_url,
        "file_name": file_name,
        "file_size": len(contents),
        "file_ext": ext,
        "mime_type": mime,
        "is_photo": True,
        "uploaded_by": current_user["id"] if current_user else None,
    }
    if inspection_id:
        try:
            uuid.UUID(str(inspection_id))
            row["record_id"] = inspection_id
        except (ValueError, AttributeError, TypeError):
            row["description"] = f"inspection_id={inspection_id}"

    try:
        supabase.table("attachments").insert(row).execute()
    except Exception as e:
        # 메타 저장이 실패해도 파일은 이미 올라갔고 URL 은 유효하다.
        # 프론트가 URL 을 받아 신고에 첨부할 수 있도록 업로드 자체는 성공으로 처리한다.
        log.error(f"[UploadPhoto] attachments 저장 실패 url={public_url}: {e}")

    log.info(f"[UploadPhoto] 저장 context={context} size={len(contents)}")

    return {
        "status": "success",
        "url": public_url,
        "data": {"url": public_url, "file_name": file_name, "size": len(contents)},
    }


# ══════════════════════════════════════════
# 배정업무 조회 — work_assignments
# ══════════════════════════════════════════

@router.get("/work-assignments")
def list_work_assignments(
    assigned_user_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="CSV 다중값 허용 (예: PENDING,OVERDUE)"),
    overdue_only: bool = Query(False),
    limit: int = Query(50, le=200),
):
    """작업자에게 배정된 업무 조회. index.html 의 미이행 배너가 사용한다.

    프론트 호출 형태:
      /work-assignments?assigned_user_id=<uuid>&status=PENDING,OVERDUE&overdue_only=true
    """
    supabase = get_supabase()

    q = supabase.table("work_assignments").select("*")
    if assigned_user_id:
        q = q.eq("assigned_user_id", assigned_user_id)
    if status:
        codes = [s.strip() for s in status.split(",") if s.strip()]
        if len(codes) == 1:
            q = q.eq("status_code", codes[0])
        elif codes:
            q = q.in_("status_code", codes)
    if overdue_only:
        # resolved_at 이 없고 기한이 지난 건. overdue_level 은 배치가 올리는 값이라
        # 아직 반영 전일 수 있어 due_date 기준도 함께 본다.
        q = q.is_("resolved_at", "null")

    res = q.order("scheduled_date", desc=False).limit(limit).execute()
    items = res.data or []

    if overdue_only:
        today = datetime.now(timezone.utc).date().isoformat()
        items = [
            a for a in items
            if (a.get("overdue_level") or 0) > 0
            or ((a.get("due_date") or a.get("scheduled_date") or "") < today
                and (a.get("status_code") or "").upper() not in ("DONE", "COMPLETED", "RESOLVED"))
        ]

    return {"status": "success", "data": {"items": items, "total": len(items)}}


# ══════════════════════════════════════════
# 교육 이수 확인 — education_history
# ══════════════════════════════════════════

class WorkerEduCompleteBody(BaseModel):
    phone: str
    edu_id: str
    worker_id: Optional[str] = None
    signature_data: Optional[str] = None
    completed_at: Optional[str] = None


@router.post("/education/worker-complete")
def worker_complete_education(
    body: WorkerEduCompleteBody,
    current_user: Optional[dict] = Depends(_optional_auth),
):
    """작업자 교육 이수 확인 (산안법 제29조).

    기존 POST /education-history 를 쓰지 못하는 이유:
      completed_hours 가 필수이고 education_master.min_hours 미만이면 400 으로 거부한다.
      작업자 앱은 이수 시간을 입력받지 않으며, 법정 기준시간 검증은 관리자 등록 경로의
      규칙이지 작업자 확인 서명의 조건이 아니다.

    서명 보관:
      education_history 에는 서명 컬럼이 없다. Storage 에 저장하고 memo 에 경로를 남긴다.
      정식 보관이 필요하면 education_files 연계 또는 컬럼 추가 마이그레이션이 선행되어야 한다.
    """
    supabase = get_supabase()
    clean = _clean_phone(body.phone)

    user_id = body.worker_id
    if not user_id and current_user:
        user_id = current_user["id"]
    if not user_id:
        user_id, _ = _resolve_worker(clean)

    # completed_at 은 date 타입이라 ISO 타임스탬프에서 날짜만 취한다.
    completed_date = (body.completed_at or datetime.now(timezone.utc).isoformat())[:10]

    signature_note = None
    if body.signature_data:
        try:
            import base64
            b64 = body.signature_data.split(",", 1)[-1]
            raw = base64.b64decode(b64)
            sig_path = f"signatures/education/{uuid.uuid4()}.png"
            supabase.storage.from_(PHOTO_BUCKET).upload(
                path=sig_path,
                file=raw,
                file_options={"content-type": "image/png"},
            )
            signature_note = supabase.storage.from_(PHOTO_BUCKET).get_public_url(sig_path)
        except Exception as e:
            # 서명 보관에 실패해도 이수 기록 자체는 남긴다.
            log.error(f"[EduComplete] 서명 저장 실패 phone={clean}: {e}")

    row = {
        "user_id": user_id,
        "education_code": body.edu_id,
        "completed_at": completed_date,
        "status_code": "COMPLETED",
    }
    if signature_note:
        row["memo"] = f"작업자 확인 서명: {signature_note}"

    res = supabase.table("education_history").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="이수 기록 저장에 실패했습니다")

    log.info(f"[EduComplete] 저장 phone={clean} edu={body.edu_id}")

    return {
        "status": "success",
        "message": "교육 이수가 확인됐습니다.",
        "data": {
            "id": res.data[0]["id"],
            "education_code": body.edu_id,
            "completed_at": completed_date,
        },
    }
