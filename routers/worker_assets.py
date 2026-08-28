"""작업자 사진 업로드 / 배정업무 / 교육이수 API — v1.3.0

v1.3.0 (Goal G-mtce7l8v-ab95bd, §81 WorkerAssets Authorization Boundary):
  POST /uploads/inspection-photo · GET /work-assignments · POST /education/worker-complete
  인증 강제(get_current_user). 사진 소유권/magic/stable-ref/signed preview.
  배정 목록은 토큰 users.id 로 고정. 교육은 active master → canonical code,
  동일 일자 dedup(CREATED/REPLAY). UNIQUE(user_id, education_code) 금지.
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
import base64
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from services import inspection_sets_svc as _iss
from services.status_vocab import is_wa_done
from services.upload_service import MAX_SIZE, MIME_TO_EXT, validate_image_file

log = logging.getLogger(__name__)
router = APIRouter(tags=["WorkerAssets"])

PHOTO_BUCKET = "company-docs"
PHOTO_CONTEXTS = frozenset({"inspect", "construction_inspect", "report"})
SIGNED_URL_EXPIRES = 3600
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_EXT_TO_MIME = {ext: mime for mime, ext in MIME_TO_EXT.items()}


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


def _stable_ref(storage_path: str) -> str:
    return f"{PHOTO_BUCKET}/{storage_path}"


def _signed_preview_url(storage, storage_path: str) -> str:
    signed = storage.from_(PHOTO_BUCKET).create_signed_url(storage_path, SIGNED_URL_EXPIRES)
    if isinstance(signed, dict):
        return signed.get("signedURL") or signed.get("signedUrl") or signed.get("signed_url") or ""
    return str(signed or "")


def _parse_uuid(value: str) -> Optional[str]:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None


def _assert_inspection_photo_owner(supabase, inspection_id: str, user_id: str) -> None:
    """inspection → work_schedule/work_assignment → assigned_user_id == caller.

    safety_inspections.assignment_id FK 는 work_schedules(id) 를 가리킨다(컬럼명과 대상 불일치).
    방어적으로 work_assignments.id 로도 조회한다. 부재 404 · 타인 배정 403.
    """
    parsed = _parse_uuid(inspection_id)
    if not parsed:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다")
    insp = (
        supabase.table("safety_inspections")
        .select("id, assignment_id")
        .eq("id", parsed)
        .limit(1)
        .execute()
    )
    if not insp.data:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다")
    parent_id = insp.data[0].get("assignment_id")
    if not parent_id:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다")

    wa_by_id = (
        supabase.table("work_assignments")
        .select("id, assigned_user_id")
        .eq("id", parent_id)
        .limit(1)
        .execute()
    )
    if wa_by_id.data:
        if wa_by_id.data[0].get("assigned_user_id") == user_id:
            return
        raise HTTPException(status_code=403, detail="본인에게 배정된 점검만 업로드할 수 있습니다")

    ws = (
        supabase.table("work_schedules")
        .select("id, assigned_user_id")
        .eq("id", parent_id)
        .limit(1)
        .execute()
    )
    if not ws.data:
        raise HTTPException(status_code=404, detail="점검을 찾을 수 없습니다")
    if ws.data[0].get("assigned_user_id") == user_id:
        return
    wa_on_schedule = (
        supabase.table("work_assignments")
        .select("id")
        .eq("schedule_id", parent_id)
        .eq("assigned_user_id", user_id)
        .limit(1)
        .execute()
    )
    if wa_on_schedule.data:
        return
    raise HTTPException(status_code=403, detail="본인에게 배정된 점검만 업로드할 수 있습니다")


def _decode_signature_png(signature_data: str) -> bytes:
    raw_b64 = signature_data.split(",", 1)[-1].strip()
    if not raw_b64:
        raise HTTPException(status_code=422, detail="서명 데이터가 올바르지 않습니다")
    pad = (-len(raw_b64)) % 4
    if pad:
        raw_b64 += "=" * pad
    try:
        raw = base64.b64decode(raw_b64, validate=True)
    except Exception:
        raise HTTPException(status_code=422, detail="서명 데이터가 올바르지 않습니다")
    if len(raw) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="파일 크기 5MB 초과")
    if raw[:8] != PNG_MAGIC:
        raise HTTPException(status_code=415, detail="서명은 PNG만 허용됩니다")
    return raw


@router.post("/uploads/inspection-photo")
async def upload_inspection_photo(
    file: UploadFile = File(...),
    context: str = Form(...),
    inspection_id: Optional[str] = Form(None),
    factory_id: Optional[str] = Form(None),
    site_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    # factory_id/site_id 는 authorization fact 가 아니다(PWA 호환 입력만 유지).
    _ = factory_id, site_id
    supabase = get_supabase()
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="빈 파일입니다")
    if context not in PHOTO_CONTEXTS:
        raise HTTPException(status_code=422, detail="허용되지 않은 context입니다")
    ext = validate_image_file(file, contents)
    mime = _EXT_TO_MIME[ext]
    insp_id = (inspection_id or "").strip() or None
    if insp_id:
        _assert_inspection_photo_owner(supabase, insp_id, current_user["id"])
    now = datetime.now(timezone.utc)
    storage_path = f"worker-photos/{context}/{now.strftime('%Y-%m')}/{uuid.uuid4()}.{ext}"
    try:
        supabase.storage.from_(PHOTO_BUCKET).upload(
            path=storage_path, file=contents, file_options={"content-type": mime}
        )
    except Exception as e:
        log.error(f"[UploadPhoto] Storage 실패 path={storage_path}: {e}")
        raise HTTPException(status_code=500, detail="사진 업로드에 실패했습니다")
    stable = _stable_ref(storage_path)
    file_name = file.filename or f"photo.{ext}"
    row = {
        "table_name": context,
        "file_category": "inspection_photo",
        "file_url": stable,
        "file_name": file_name,
        "file_size": len(contents),
        "file_ext": ext,
        "mime_type": mime,
        "is_photo": True,
        "uploaded_by": current_user["id"],
    }
    if insp_id:
        row["record_id"] = _parse_uuid(insp_id)
    else:
        row["description"] = "inspection_id omitted"
    try:
        supabase.table("attachments").insert(row).execute()
    except Exception as e:
        log.error(f"[UploadPhoto] attachments 저장 실패 ref={stable}: {e}")
        raise HTTPException(status_code=500, detail="사진 업로드에 실패했습니다")
    try:
        preview = _signed_preview_url(supabase.storage, storage_path)
    except Exception as e:
        log.error(f"[UploadPhoto] signed URL 실패 path={storage_path}: {e}")
        raise HTTPException(status_code=500, detail="사진 업로드에 실패했습니다")
    log.info(f"[UploadPhoto] 저장 context={context} size={len(contents)}")
    return {
        "status": "success",
        "url": preview,
        "data": {"url": preview, "file_name": file_name, "size": len(contents)},
    }


@router.get("/work-assignments")
def list_work_assignments(
    assigned_user_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="CSV 다중값 허용"),
    overdue_only: bool = Query(False),
    limit: int = Query(50, le=200),
    current_user: dict = Depends(get_current_user),
):
    """index.html 미이행 배너용. subject 는 항상 토큰 users.id. tenant-wide 목록 금지."""
    subject = current_user["id"]
    if assigned_user_id and assigned_user_id != subject:
        raise HTTPException(status_code=403, detail="본인에게 배정된 업무만 조회할 수 있습니다")
    supabase = get_supabase()
    q = supabase.table("work_assignments").select("*").eq("assigned_user_id", subject)
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
        items = [
            a for a in items
            if (a.get("overdue_level") or 0) > 0
            or (
                (a.get("due_date") or a.get("scheduled_date") or "") < today
                and not is_wa_done(a.get("status_code"))
            )
        ]
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
    phone: Optional[str] = None
    edu_id: str
    worker_id: Optional[str] = None
    signature_data: Optional[str] = None
    completed_at: Optional[str] = None


@router.post("/education/worker-complete")
def worker_complete_education(
    body: WorkerEduCompleteBody,
    current_user: dict = Depends(get_current_user),
):
    """작업자 교육 이수 확인 (산안법 제29조).

    object gate = AUTH 자기 identity + active education_master 존재.
    education_assignment 필수화는 금지(prod 0행 · PWA 는 master edu_id 만 전송).
    DEDUP v1 = current_user.id + canonical education_code + server date.
    동일 날짜 retry/double-click 만 접음. 동시 double-submit 원자성은 DDL 없이 미보장.
    UNIQUE(user_id, education_code) 금지 — 타 날짜 정기 재이수는 허용.
    body.completed_at 은 호환 입력으로 받되 dedup identity 에 사용하지 않는다.
    """
    supabase = get_supabase()
    user_id = current_user["id"]
    if body.worker_id and str(body.worker_id) != str(user_id):
        raise HTTPException(status_code=403, detail={"error": "FORBIDDEN_IDENTITY"})
    if (body.phone or "").strip():
        resolved, _ = _resolve_worker(body.phone)
        if not resolved or resolved != user_id:
            raise HTTPException(status_code=403, detail={"error": "FORBIDDEN_IDENTITY"})

    edu_uuid = _parse_uuid(body.edu_id)
    if not edu_uuid:
        raise HTTPException(status_code=404, detail={"error": "EDUCATION_NOT_FOUND"})
    master = (
        supabase.table("education_master")
        .select("education_code")
        .eq("id", edu_uuid)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not master.data or not master.data[0].get("education_code"):
        raise HTTPException(status_code=404, detail={"error": "EDUCATION_NOT_FOUND"})
    canonical_code = master.data[0]["education_code"]

    company_id = None
    factory_id = None
    try:
        urow = supabase.table("users").select("company_id, factory_id").eq("id", user_id).limit(1).execute()
        if urow.data:
            company_id = urow.data[0].get("company_id")
            factory_id = urow.data[0].get("factory_id")
        else:
            company_id = current_user.get("company_id")
            factory_id = current_user.get("factory_id")
    except Exception as e:
        log.warning(f"[EduComplete] 소속 조회 실패 user_id={user_id}: {e}")
        company_id = current_user.get("company_id")
        factory_id = current_user.get("factory_id")

    server_date = datetime.now(timezone.utc).date().isoformat()
    existing = (
        supabase.table("education_history")
        .select("id, education_code, completed_at")
        .eq("user_id", user_id)
        .eq("education_code", canonical_code)
        .eq("completed_at", server_date)
        .eq("status_code", "COMPLETED")
        .limit(1)
        .execute()
    )
    if existing.data:
        row = existing.data[0]
        log.info(f"[EduComplete] REPLAY user={user_id} edu={canonical_code} date={server_date}")
        return {
            "status": "success",
            "message": "교육 이수가 확인됐습니다.",
            "data": {
                "id": row["id"],
                "education_code": canonical_code,
                "completed_at": server_date,
                "mode": "REPLAY",
            },
        }

    signature_note = None
    if body.signature_data:
        raw = _decode_signature_png(body.signature_data)
        sig_path = f"signatures/education/{uuid.uuid4()}.png"
        try:
            supabase.storage.from_(PHOTO_BUCKET).upload(
                path=sig_path, file=raw, file_options={"content-type": "image/png"}
            )
        except Exception as e:
            log.error(f"[EduComplete] 서명 저장 실패 user={user_id}: {e}")
            raise HTTPException(status_code=500, detail="이수 기록 저장에 실패했습니다")
        signature_note = _stable_ref(sig_path)

    row = {
        "user_id": user_id,
        "education_code": canonical_code,
        "completed_at": server_date,
        "status_code": "COMPLETED",
    }
    if company_id:
        row["company_id"] = company_id
    if factory_id:
        row["factory_id"] = factory_id
    if signature_note:
        row["memo"] = f"작업자 확인 서명: {signature_note}"
    res = supabase.table("education_history").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="이수 기록 저장에 실패했습니다")
    log.info(f"[EduComplete] CREATED user={user_id} edu={canonical_code}")
    return {
        "status": "success",
        "message": "교육 이수가 확인됐습니다.",
        "data": {
            "id": res.data[0]["id"],
            "education_code": canonical_code,
            "completed_at": server_date,
            "mode": "CREATED",
        },
    }
