"""작업자 사진 업로드 / 배정업무 / 교육이수 API — v1.2.0

v1.2.0 (Goal G-mswtdmi1-420f8c):
  [RE-ADD] GET /work-assignments/{id}/items 소유자 검증(ⓐ) 재도입.
    v1.1.1 에서 임시 철회했던 이유(작업자 토큰 발급 불안정)가 해소됨:
    verify-otp 로그인·토큰 정상 동작을 운영 로그(auth 200/get_user 200)로 확인했고,
    미확인 이메일 계정은 생성경로에서 email_confirm=True 로 발급되며(작업자), 잔여
    미확인(웹가입) 계정은 로그인 자가치유(auth.py 별건)로 확인 처리된다.
    → 토큰 users.id 와 work_assignments.assigned_user_id 대조, 다르면 403 (A-8).
v1.1.1: 소유자 검증 임시 철회(위에서 재도입).
v1.1.0: 소유자 검증 최초 추가.
v1.0.0: 작업자 PWA 가 호출하지만 서버에 부재해 404 로 실패하던 경로를 신설.

API:
  POST /uploads/inspection-photo    현장 사진 업로드 (_utils.js TAI.uploadPhoto)
  GET  /work-assignments            배정업무 조회 (index.html 미이행 배너)
  GET  /work-assignments/{id}/items 배정 점검 항목 (inspect.html) — 소유자 검증
  POST /education/worker-complete   교육 이수 확인 (education.html)
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel

from db.supabase_client import get_supabase
from services import inspection_sets_svc as _iss

log = logging.getLogger(__name__)
router = APIRouter(tags=["WorkerAssets"])

PHOTO_BUCKET = "company-docs"


def _optional_auth(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Authorization이 있으면 검증, 없으면 None. (worker_check.py 와 동일 관례)"""
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


@router.post("/uploads/inspection-photo")
async def upload_inspection_photo(
    file: UploadFile = File(...),
    context: str = Form(...),
    inspection_id: Optional[str] = Form(None),
    factory_id: Optional[str] = Form(None),
    site_id: Optional[str] = Form(None),
    current_user: Optional[dict] = Depends(_optional_auth),
):
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
        supabase.storage.from_(PHOTO_BUCKET).upload(path=storage_path, file=contents, file_options={"content-type": mime})
    except Exception as e:
        log.error(f"[UploadPhoto] Storage 실패 path={storage_path}: {e}")
        raise HTTPException(status_code=500, detail="사진 업로드에 실패했습니다")
    public_url = supabase.storage.from_(PHOTO_BUCKET).get_public_url(storage_path)
    row = {
        "table_name": context, "file_category": "inspection_photo", "file_url": public_url,
        "file_name": file_name, "file_size": len(contents), "file_ext": ext, "mime_type": mime,
        "is_photo": True, "uploaded_by": current_user["id"] if current_user else None,
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
        log.error(f"[UploadPhoto] attachments 저장 실패 url={public_url}: {e}")
    log.info(f"[UploadPhoto] 저장 context={context} size={len(contents)}")
    return {"status": "success", "url": public_url, "data": {"url": public_url, "file_name": file_name, "size": len(contents)}}


@router.get("/work-assignments")
def list_work_assignments(
    assigned_user_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="CSV 다중값 허용"),
    overdue_only: bool = Query(False),
    limit: int = Query(50, le=200),
):
    """index.html 미이행 배너용. /work-assignments?assigned_user_id=<uuid>&status=PENDING,OVERDUE&overdue_only=true"""
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
        q = q.is_("resolved_at", "null")
    res = q.order("scheduled_date", desc=False).limit(limit).execute()
    items = res.data or []
    if overdue_only:
        today = datetime.now(timezone.utc).date().isoformat()
        items = [a for a in items if (a.get("overdue_level") or 0) > 0 or ((a.get("due_date") or a.get("scheduled_date") or "") < today and (a.get("status_code") or "").upper() not in ("DONE", "COMPLETED", "RESOLVED"))]
    return {"status": "success", "data": {"items": items, "total": len(items)}}


@router.get("/work-assignments/{assignment_id}/items")
def get_work_assignment_items(
    assignment_id: str,
    current_user: Optional[dict] = Depends(_optional_auth),
):
    """배정 점검 항목 조회. ⓐ 본인 배정만(A-8): 토큰 users.id vs assigned_user_id, 다르면 403.

    verify-otp 가 worker_id=users.id 로 발급하므로 앱이 조회하는 assigned_user_id 와 같은 공간이다.
    토큰 없으면 401(앱이 로그인 유도). 토큰 정상 동작은 운영 로그로 확인됨(v1.2.0).
    """
    if not current_user:
        raise HTTPException(status_code=401, detail={"error": "AUTH_REQUIRED"})
    supabase = get_supabase()
    wa = supabase.table("work_assignments").select("assigned_user_id").eq("id", assignment_id).limit(1).execute()
    if not wa.data:
        raise HTTPException(status_code=404, detail="배정된 점검을 찾을 수 없습니다")
    if wa.data[0].get("assigned_user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="본인에게 배정된 점검만 조회할 수 있습니다")
    try:
        return _iss.get_items_for_assignment(assignment_id)
    except _iss.InspectionSetsSvcError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


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
    """작업자 교육 이수 확인 (산안법 제29조)."""
    supabase = get_supabase()
    clean = _clean_phone(body.phone)
    user_id = body.worker_id
    if not user_id and current_user:
        user_id = current_user["id"]
    if not user_id:
        user_id, _ = _resolve_worker(clean)
    completed_date = (body.completed_at or datetime.now(timezone.utc).isoformat())[:10]
    signature_note = None
    if body.signature_data:
        try:
            import base64
            b64 = body.signature_data.split(",", 1)[-1]
            raw = base64.b64decode(b64)
            sig_path = f"signatures/education/{uuid.uuid4()}.png"
            supabase.storage.from_(PHOTO_BUCKET).upload(path=sig_path, file=raw, file_options={"content-type": "image/png"})
            signature_note = supabase.storage.from_(PHOTO_BUCKET).get_public_url(sig_path)
        except Exception as e:
            log.error(f"[EduComplete] 서명 저장 실패 phone={clean}: {e}")
    row = {"user_id": user_id, "education_code": body.edu_id, "completed_at": completed_date, "status_code": "COMPLETED"}
    if signature_note:
        row["memo"] = f"작업자 확인 서명: {signature_note}"
    res = supabase.table("education_history").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="이수 기록 저장에 실패했습니다")
    log.info(f"[EduComplete] 저장 phone={clean} edu={body.edu_id}")
    return {"status": "success", "message": "교육 이수가 확인됐습니다.", "data": {"id": res.data[0]["id"], "education_code": body.edu_id, "completed_at": completed_date}}
