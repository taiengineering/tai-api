"""
공개 웹용 — 문의 접수(POST /contacts),
단일 요청 문의+첨부(POST /contacts/with-attachments),
첨부 재시도(POST /contacts/{id}/attachments, 60분 창),
FAQ 목록(GET /faqs)
관리자 FAQ: prefix /admin/site-faqs
"""
import re
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Header, Query, UploadFile
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


# ── 공개 첨부 공통 상수 ──────────────────────────────────────────────

CONTACT_BUCKET = "company-docs"
CONTACT_ATTACH_MAX_FILES = 5
CONTACT_ATTACH_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
_ATTACH_WINDOW = timedelta(hours=1)           # 재시도 허용 창

_ALLOWED_EXTS: dict = {
    "pdf":  "application/pdf",
    "doc":  "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls":  "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "png":  "image/png",
    "jpg":  "image/jpeg",
    "jpeg": "image/jpeg",
    "txt":  "text/plain",
    "zip":  "application/zip",
    "hwp":  "application/x-hwp",
    "hwpx": "application/haansofthwp",
}

# 위험 파일 헤더 — 확장자 무관 거부
_DANGEROUS_HEADERS: tuple = (
    b'MZ',           # Windows PE 실행파일
    b'\x7fELF',      # Linux ELF 실행파일
    b'#!/',          # 쉘 스크립트
)

# 확장자별 허용 매직 바이트 (None = txt 특수 처리: null 바이트 없어야 함)
_MAGIC: dict = {
    "pdf":  (b"%PDF",),
    "png":  (b"\x89PNG",),
    "jpg":  (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "zip":  (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    "docx": (b"PK\x03\x04", b"PK\x05\x06"),
    "xlsx": (b"PK\x03\x04", b"PK\x05\x06"),
    "hwpx": (b"PK\x03\x04", b"PK\x05\x06"),
    "doc":  (b"\xd0\xcf\x11\xe0",),
    "xls":  (b"\xd0\xcf\x11\xe0",),
    "hwp":  (b"\xd0\xcf\x11\xe0",),
    "txt":  None,
}


def _contact_stable_ref(storage_path: str) -> str:
    return f"storage://{CONTACT_BUCKET}/{storage_path}"


def _parse_inquiry_uuid(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="유효하지 않은 문의 ID입니다.")


def _has_dangerous_header(raw: bytes) -> bool:
    for h in _DANGEROUS_HEADERS:
        if raw[: len(h)] == h:
            return True
    return False


def _file_magic_ok(raw: bytes, ext: str) -> bool:
    if _has_dangerous_header(raw):
        return False
    expected = _MAGIC.get(ext)
    if expected is None:  # txt
        return b"\x00" not in raw[:512]
    for magic in expected:
        if raw[: len(magic)] == magic:
            return True
    return False


async def _read_and_validate(f: UploadFile) -> tuple:
    """(raw, fname, ext, mime) 반환. 검증 실패 시 HTTPException."""
    raw = await f.read()
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(raw) > CONTACT_ATTACH_MAX_BYTES:
        raise HTTPException(status_code=400, detail="파일 크기 한도(10MB)를 초과했습니다.")
    fname = (f.filename or "file").strip()
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="허용되지 않는 파일 형식입니다.")
    if not _file_magic_ok(raw, ext):
        raise HTTPException(status_code=400, detail="파일 내용이 형식과 일치하지 않습니다.")
    return raw, fname, ext, _ALLOWED_EXTS[ext]


def _cleanup_storage(supabase, paths: list) -> None:
    """Storage 파일 정리 (best-effort, 오류 무시)"""
    for path in paths or []:
        try:
            supabase.storage.from_(CONTACT_BUCKET).remove([path])
        except Exception:
            pass


async def _upload_attachments(supabase, validated: list, inquiry_id: str) -> tuple:
    """
    검증 완료 파일을 Storage + attachments 테이블에 저장.
    Returns (results, None) 성공, ([], 오류메시지) 실패.
    실패 시 업로드된 Storage 파일 모두 정리.
    """
    uploaded_paths: list = []
    results = []
    month_prefix = now_kst().strftime("%Y-%m")

    for raw, fname, ext, mime in validated:
        storage_path = f"contact-attachments/{month_prefix}/{inquiry_id}/{uuid.uuid4()}.{ext}"
        try:
            supabase.storage.from_(CONTACT_BUCKET).upload(
                path=storage_path, file=raw, file_options={"content-type": mime}
            )
            uploaded_paths.append(storage_path)
        except Exception as e:
            logger.error("[ContactAttach] Storage 업로드 실패")
            _cleanup_storage(supabase, uploaded_paths)
            return [], "파일 저장에 실패했습니다"

        row = {
            "table_name": "inquiries",
            "record_id": inquiry_id,
            "file_category": "contact_attachment",
            "file_url": _contact_stable_ref(storage_path),
            "file_name": fname,
            "file_size": len(raw),
            "file_ext": ext,
            "mime_type": mime,
            "is_photo": ext in ("png", "jpg", "jpeg"),
        }
        try:
            ins = supabase.table("attachments").insert(row).execute()
        except Exception as e:
            logger.error("[ContactAttach] DB 저장 실패")
            _cleanup_storage(supabase, uploaded_paths)
            return [], "파일 저장에 실패했습니다"

        saved_row = ins.data[0] if ins.data else row
        results.append({
            "id": saved_row.get("id"),
            "file_name": fname,
            "file_size": len(raw),
            "file_ext": ext,
            "mime_type": mime,
        })

    return results, None


# ── POST /contacts/with-attachments (단일 요청 — 보안 주경로) ──────────
# 반드시 /contacts/{inquiry_id}/attachments 보다 먼저 등록해야 한다.

@router.post("/contacts/with-attachments")
async def submit_contact_with_attachments(
    name: str = Form(..., min_length=1),
    email: str = Form(..., min_length=3),
    content: str = Form(..., min_length=1),
    source: str = Form(default="marketing"),
    page_url: Optional[str] = Form(default=None),
    files: Optional[List[UploadFile]] = File(default=None),
):
    """공개 문의 접수 + 파일 첨부 단일 요청 — 문의 ID가 외부에 먼저 노출되지 않음"""
    # ① 파일 검증 (문의 생성 전 — 검증 실패 시 DB 접촉 불필요)
    validated = []
    if files:
        file_list = [f for f in files if f and f.filename]
        if len(file_list) > CONTACT_ATTACH_MAX_FILES:
            raise HTTPException(
                status_code=400,
                detail=f"파일은 최대 {CONTACT_ATTACH_MAX_FILES}개까지 첨부할 수 있습니다.",
            )
        for f in file_list:
            validated.append(await _read_and_validate(f))

    supabase = get_supabase()

    # ② 문의 생성
    row = {
        "name": name.strip(),
        "email": email.strip(),
        "content": content.strip(),
        "source": (source or "marketing").strip(),
        "page_url": (page_url or "").strip() or None,
        "inquiry_type": "INQUIRY",
        "is_member": False,
        "created_at": _now(),
        "updated_at": _now(),
    }
    try:
        res = supabase.table("inquiries").insert(row).execute()
    except Exception:
        raise HTTPException(status_code=500, detail="저장 실패")

    saved = res.data[0] if res.data else row
    inquiry_id = str(saved.get("id", "")) if saved else ""

    # ③ 파일 업로드 (문의 생성 성공 후)
    attach_status = "ok"
    attach_results = []
    if validated and inquiry_id:
        attach_results, err = await _upload_attachments(supabase, validated, inquiry_id)
        if err:
            attach_status = "failed"

    return {
        "status": "success",
        "data": saved,
        "attachments_status": attach_status,
        "attachments": attach_results,
    }


# ── POST /contacts/{inquiry_id}/attachments (첨부 재시도, 60분 창) ──────

@router.post("/contacts/{inquiry_id}/attachments")
async def retry_contact_attachments(
    inquiry_id: str,
    files: List[UploadFile] = File(...),
):
    """공개 문의 파일 첨부 재시도 — 접수 후 60분 이내, 최대 5개"""
    parsed_id = _parse_inquiry_uuid(inquiry_id)
    supabase = get_supabase()

    # inquiry 존재 + 60분 시간 창 확인
    check = (
        supabase.table("inquiries")
        .select("id, created_at")
        .eq("id", parsed_id)
        .limit(1)
        .execute()
    )
    if not check.data:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")

    created_str = (check.data[0] or {}).get("created_at", "")
    try:
        created_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        if datetime.now(timezone.utc) - created_at > _ATTACH_WINDOW:
            raise HTTPException(
                status_code=403,
                detail="첨부 가능 시간이 만료됐습니다 (접수 후 1시간 이내만 허용).",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # 타임스탬프 파싱 실패 시 허용(방어적)

    if not files:
        raise HTTPException(status_code=400, detail="파일이 없습니다.")
    if len(files) > CONTACT_ATTACH_MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"파일은 최대 {CONTACT_ATTACH_MAX_FILES}개까지 첨부할 수 있습니다.",
        )

    # 기존 첨부 수 확인 (한도 초과 방지)
    existing = (
        supabase.table("attachments")
        .select("id", count="exact")
        .eq("table_name", "inquiries")
        .eq("record_id", parsed_id)
        .execute()
    )
    already = existing.count or 0
    if already + len(files) > CONTACT_ATTACH_MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"첨부 파일 한도({CONTACT_ATTACH_MAX_FILES}개)를 초과합니다.",
        )

    # 파일 검증
    validated = []
    for f in files:
        validated.append(await _read_and_validate(f))

    # 업로드
    results, err = await _upload_attachments(supabase, validated, parsed_id)
    if err:
        raise HTTPException(status_code=500, detail="파일 저장에 실패했습니다.")

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
