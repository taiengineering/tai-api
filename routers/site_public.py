"""
공개 웹용 — 문의 접수(POST /contacts), 파일 첨부(POST /contacts/{id}/attachments),
FAQ 목록(GET /faqs)
관리자 FAQ: prefix /admin/site-faqs
"""
import re
import uuid
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, Header, Query, UploadFile
from pydantic import BaseModel, Field

from db.supabase_client import get_supabase
from services.time import now_kst, serialize_external_utc

logger = logging.getLogger("site_public")
router = APIRouter(tags=["공개 웹"])


def _now() -> str:
    return serialize_external_utc(now_kst())


_CATEGORY_LABEL = {
    "introduction": "TAI Safe 도입",
    "diagnosis": "법령진단 문의",
    "tech": "기술지원",
    "partner": "제휴·파트너",
    "etc": "기타 문의",
}


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


# ── POST /contacts → inquiries 저장 + Slack(#tai-ops) 알림 ──────────

class PublicContactBody(BaseModel):
    name: str = Field(..., min_length=1)
    email: str = Field(..., min_length=3)
    content: str = Field(..., min_length=1)
    category: Optional[str] = None
    title: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    company_name: Optional[str] = None   # 구 필드 호환
    inquiry_type: Optional[str] = None   # 구 필드 호환
    source: Optional[str] = "marketing"
    page_url: Optional[str] = None


@router.post("/contacts")
def submit_public_contact(body: PublicContactBody):
    """공개 문의 접수 → inquiries 저장 + Slack 알림"""
    supabase = get_supabase()
    category = (body.category or body.inquiry_type or "").strip() or None
    company = (body.company or body.company_name or "").strip() or None
    row = {
        "name": body.name.strip(),
        "email": body.email.strip(),
        "phone": (body.phone or "").strip() or None,
        "company": company,
        "category": category,
        "title": (body.title or "").strip() or None,
        "content": body.content.strip(),
        "source": (body.source or "marketing").strip(),
        "page_url": (body.page_url or "").strip() or None,
        "inquiry_type": "INQUIRY",
        "is_member": False,
        "created_at": _now(),
        "updated_at": _now(),
    }
    try:
        res = supabase.table("inquiries").insert(row).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"저장 실패: {e!s}")

    saved = res.data[0] if res.data else row

    # WO-SLACK-EVENT-HUB-001 PR-①: writer 의 직접 Slack 발송 제거.
    # Slack authority = 운영 DB trigger trg_inquiries_notify → POST /internal/inbox/notify
    # → slack_dispatcher(INQUIRY_CREATED). 이곳에서 이중발송 금지.

    return {"status": "success", "data": saved}


# ── POST /contacts/{inquiry_id}/attachments ───────────────────────

CONTACT_BUCKET = "company-docs"
CONTACT_ATTACH_MAX_FILES = 5
CONTACT_ATTACH_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file

_ALLOWED_EXTS: dict = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "txt": "text/plain",
    "zip": "application/zip",
    "hwp": "application/x-hwp",
    "hwpx": "application/haansofthwp",
}


def _contact_stable_ref(storage_path: str) -> str:
    return f"storage://{CONTACT_BUCKET}/{storage_path}"


def _parse_inquiry_uuid(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="유효하지 않은 문의 ID입니다.")


@router.post("/contacts/{inquiry_id}/attachments")
async def upload_contact_attachments(
    inquiry_id: str,
    files: List[UploadFile] = File(...),
):
    """공개 문의 파일 첨부 — inquiry_id 하나당 최대 5개, 각 10MB 이하"""
    parsed_id = _parse_inquiry_uuid(inquiry_id)
    supabase = get_supabase()

    # inquiry 존재 확인
    check = supabase.table("inquiries").select("id").eq("id", parsed_id).limit(1).execute()
    if not check.data:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")

    if len(files) == 0:
        raise HTTPException(status_code=400, detail="파일이 없습니다.")
    if len(files) > CONTACT_ATTACH_MAX_FILES:
        raise HTTPException(status_code=400, detail=f"파일은 최대 {CONTACT_ATTACH_MAX_FILES}개까지 첨부할 수 있습니다.")

    # 기존 첨부 수 확인
    existing = supabase.table("attachments").select("id", count="exact").eq("table_name", "inquiries").eq("record_id", parsed_id).execute()
    already = existing.count or 0
    if already + len(files) > CONTACT_ATTACH_MAX_FILES:
        raise HTTPException(status_code=400, detail=f"첨부 파일 한도({CONTACT_ATTACH_MAX_FILES}개)를 초과합니다.")

    now = now_kst()
    month_prefix = now.strftime("%Y-%m")
    results = []

    for f in files:
        raw = await f.read()
        if not raw:
            raise HTTPException(status_code=400, detail=f"빈 파일입니다: {f.filename}")
        if len(raw) > CONTACT_ATTACH_MAX_BYTES:
            raise HTTPException(status_code=400, detail=f"파일 크기 초과(10MB): {f.filename}")

        fname = (f.filename or "file").strip()
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext not in _ALLOWED_EXTS:
            raise HTTPException(status_code=400, detail=f"허용되지 않는 파일 형식입니다: {fname}")
        mime = _ALLOWED_EXTS[ext]

        storage_path = f"contact-attachments/{month_prefix}/{parsed_id}/{uuid.uuid4()}.{ext}"
        try:
            supabase.storage.from_(CONTACT_BUCKET).upload(
                path=storage_path, file=raw, file_options={"content-type": mime}
            )
        except Exception as e:
            logger.error(f"[ContactAttach] Storage 실패 path={storage_path}: {e}")
            raise HTTPException(status_code=500, detail="파일 저장에 실패했습니다.")

        stable = _contact_stable_ref(storage_path)
        row = {
            "table_name": "inquiries",
            "record_id": parsed_id,
            "file_category": "contact_attachment",
            "file_url": stable,
            "file_name": fname,
            "file_size": len(raw),
            "file_ext": ext,
            "mime_type": mime,
            "is_photo": ext in ("png", "jpg", "jpeg"),
        }
        try:
            ins = supabase.table("attachments").insert(row).execute()
        except Exception as e:
            logger.error(f"[ContactAttach] DB 저장 실패 ref={stable}: {e}")
            raise HTTPException(status_code=500, detail="파일 저장에 실패했습니다.")

        saved_row = ins.data[0] if ins.data else row
        results.append({
            "id": saved_row.get("id"),
            "file_name": fname,
            "file_size": len(raw),
            "file_ext": ext,
            "mime_type": mime,
        })

    return {"status": "success", "data": {"attachments": results}}


# ── GET /faqs ─────────────────────────────────────────────────────

@router.get("/faqs")
def list_public_faqs():
    """게시된 FAQ 목록 (공개, 인증 불필요)"""
    supabase = get_supabase()
    try:
        res = (
            supabase.table("site_faqs")
            .select("id, question, answer, sort_order")
            .eq("is_published", True)
            .order("sort_order", desc=False)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "success", "data": {"items": res.data or []}}


# ── 관리자 FAQ CRUD /admin/site-faqs (Bearer 권장) ────────────────

admin_router = APIRouter(prefix="/admin/site-faqs", tags=["관리 - 공개 FAQ"])


class FaqCreate(BaseModel):
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    sort_order: int = 0
    is_published: bool = True


class FaqUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    sort_order: Optional[int] = None
    is_published: Optional[bool] = None


def _require_bearer(authorization: Optional[str]):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")


@admin_router.get("")
def admin_list_faqs(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    _require_bearer(authorization)
    supabase = get_supabase()
    offset = (page - 1) * size
    res = (
        supabase.table("site_faqs")
        .select("*", count="exact")
        .order("sort_order")
        .range(offset, offset + size - 1)
        .execute()
    )
    return {
        "status": "success",
        "data": {
            "items": res.data or [],
            "total": res.count or 0,
            "page": page,
            "size": size,
        },
    }


@admin_router.post("")
def admin_create_faq(body: FaqCreate, authorization: Optional[str] = Header(None)):
    _require_bearer(authorization)
    supabase = get_supabase()
    now = _now()
    row = {
        "question": body.question.strip(),
        "answer": body.answer.strip(),
        "sort_order": body.sort_order,
        "is_published": body.is_published,
        "created_at": now,
        "updated_at": now,
    }
    res = supabase.table("site_faqs").insert(row).execute()
    return {"status": "success", "data": res.data[0] if res.data else {}}


@admin_router.patch("/{faq_id}")
def admin_patch_faq(
    faq_id: str,
    body: FaqUpdate,
    authorization: Optional[str] = Header(None),
):
    _require_bearer(authorization)
    supabase = get_supabase()
    raw = body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)
    patch = {k: v for k, v in raw.items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="변경할 필드가 없습니다.")
    patch["updated_at"] = _now()
    res = supabase.table("site_faqs").update(patch).eq("id", faq_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="FAQ를 찾을 수 없습니다.")
    return {"status": "success", "data": res.data[0]}


@admin_router.delete("/{faq_id}")
def admin_delete_faq(faq_id: str, authorization: Optional[str] = Header(None)):
    _require_bearer(authorization)
    supabase = get_supabase()
    res = supabase.table("site_faqs").delete().eq("id", faq_id).execute()
    return {"status": "success", "deleted": bool(res.data)}
