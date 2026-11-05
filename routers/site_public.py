"""
공개 웹용 — 문의 접수(POST /contacts),
단일 요청 문의+첨부(POST /contacts/with-attachments),
첨부 재시도(POST /contacts/{id}/attachments, 60분 창 + 소유자 토큰),
FAQ 목록(GET /faqs)
관리자 FAQ: prefix /admin/site-faqs
"""
import base64
import hashlib
import hmac
import logging
import os
import re
import uuid
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


def _get_upload_signing_key() -> bytes:
    """SUPABASE_SERVICE_ROLE_KEY 에서 첨부 전용 서명키 파생 (새 비밀 불필요).
    환경변수 미설정 시 RuntimeError — 토큰 발급·검증 불가(fail-closed).
    """
    base = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
    if not base:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY 미설정 — 첨부 토큰 발급 불가")
    return hmac.new(base.encode(), b"contact-upload-v1", hashlib.sha256).digest()


def _generate_upload_token(inquiry_id: str, created_at: datetime) -> str:
    """문의 ID + 생성 시각(시간 단위)을 HMAC 서명한 일회성 업로드 토큰."""
    epoch_hour = int(created_at.timestamp()) // 3600
    msg = f"{inquiry_id}:{epoch_hour}".encode()
    h = hmac.new(_get_upload_signing_key(), msg, hashlib.sha256)
    return base64.urlsafe_b64encode(h.digest()).rstrip(b"=").decode()


def _verify_upload_token(token: str, inquiry_id: str, created_at_str: str) -> bool:
    """재시도 토큰 검증 — 실패 시 False."""
    if not token:
        return False
    try:
        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        expected = _generate_upload_token(inquiry_id, created_at)
        return hmac.compare_digest(token.encode(), expected.encode())
    except Exception:
        return False


def _contact_stable_ref(storage_path: str) -> str:
    return f"storage://{CONTACT_BUCKET}/{storage_path}"


def _parse_inquiry_uuid(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="유효하지 않은 문의 ID입니다.")


def _get_idem_derive_key() -> Optional[bytes]:
    """문의 ID 파생용 HMAC 키 — 환경변수 미설정 시 None."""
    base = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
    if not base:
        return None
    return hmac.new(base.encode(), b"contact-idem-v1", hashlib.sha256).digest()


def _derive_inquiry_id(client_key: Optional[str]) -> Optional[str]:
    """클라이언트 UUID → HMAC 파생 inquiry_id.
    client_key와 반환값은 서버 비밀키 없이 상호 도출 불가.
    UUID 형식 불일치 또는 환경변수 미설정 시 None.
    """
    if not client_key:
        return None
    try:
        uuid.UUID(str(client_key).strip())
    except (ValueError, AttributeError, TypeError):
        return None
    key = _get_idem_derive_key()
    if not key:
        return None
    h = hmac.new(key, str(client_key).strip().encode(), hashlib.sha256).digest()
    return str(uuid.UUID(bytes=h[:16]))


def _build_existing_response(supabase, inquiry_id: str, created_str: str) -> dict:
    """기존 문의 재전송 응답 — 개인정보 제외, 첨부 현황 포함."""
    try:
        attach_rows = (
            supabase.table("attachments")
            .select("id")
            .eq("record_id", inquiry_id)
            .eq("table_name", "inquiries")
            .execute()
        )
        attachments_count = len(attach_rows.data) if attach_rows and attach_rows.data else 0
    except Exception:
        attachments_count = 0
    attachments_status = "none" if attachments_count == 0 else "has_attachments"

    upload_token = None
    if inquiry_id:
        try:
            created_at = datetime.fromisoformat((created_str or "").replace("Z", "+00:00"))
            upload_token = _generate_upload_token(inquiry_id, created_at)
        except Exception:
            pass

    return {
        "status": "existing",
        "inquiry_id": inquiry_id,
        "upload_token": upload_token,
        "attachments_status": attachments_status,
        "attachments_count": attachments_count,
    }


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
    # 한도+1 바이트만 읽어 대용량 파일이 메모리를 소진하지 않도록 제한
    raw = await f.read(CONTACT_ATTACH_MAX_BYTES + 1)
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
    """Storage 파일 정리 (best-effort). 실패 시 로그 기록."""
    for path in paths or []:
        try:
            supabase.storage.from_(CONTACT_BUCKET).remove([path])
        except Exception as e:
            logger.error("[ContactAttach] Storage 정리 실패 path=%s err=%s", path, e)


def _cleanup_db_rows(supabase, ids: list) -> None:
    """attachments 테이블 행 정리 (best-effort). 실패 시 로그 기록."""
    for row_id in ids or []:
        try:
            supabase.table("attachments").delete().eq("id", str(row_id)).execute()
        except Exception as e:
            logger.error("[ContactAttach] DB행 정리 실패 id=%s err=%s", row_id, e)


async def _upload_attachments(supabase, validated: list, inquiry_id: str) -> tuple:
    """
    검증 완료 파일을 Storage + attachments 테이블에 저장.
    Returns (results, None) 성공, ([], 오류메시지) 실패.
    실패 시 업로드된 Storage 파일과 삽입된 DB 행 모두 정리 (불일치 방지).
    """
    uploaded_paths: list = []
    inserted_db_ids: list = []   # R2: Storage+DB 불일치 방지용 추적
    results = []
    month_prefix = now_kst().strftime("%Y-%m")

    for raw, fname, ext, mime in validated:
        # 간이 중복 방지 — (record_id, file_name, file_size) 존재 시 재업로드 생략.
        # 한계: 동일 이름·크기 ≠ 동일 내용. 기존 파일 덮어쓰지 않음.
        try:
            dup = (
                supabase.table("attachments")
                .select("id")
                .eq("record_id", inquiry_id)
                .eq("table_name", "inquiries")
                .eq("file_name", fname)
                .eq("file_size", len(raw))
                .limit(1)
                .execute()
            )
            if dup.data:
                results.append({
                    "id": dup.data[0].get("id"),
                    "file_name": fname,
                    "file_size": len(raw),
                    "file_ext": ext,
                    "mime_type": mime,
                })
                continue
        except Exception:
            pass  # dedup 조회 실패 시 → 일반 업로드 진행

        storage_path = f"contact-attachments/{month_prefix}/{inquiry_id}/{uuid.uuid4()}.{ext}"
        try:
            supabase.storage.from_(CONTACT_BUCKET).upload(
                path=storage_path, file=raw, file_options={"content-type": mime}
            )
            uploaded_paths.append(storage_path)
        except Exception:
            logger.error("[ContactAttach] Storage 업로드 실패")
            _cleanup_storage(supabase, uploaded_paths)
            _cleanup_db_rows(supabase, inserted_db_ids)
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
        except Exception:
            logger.error("[ContactAttach] DB 저장 실패")
            _cleanup_storage(supabase, uploaded_paths)
            _cleanup_db_rows(supabase, inserted_db_ids)
            return [], "파일 저장에 실패했습니다"

        saved_row = ins.data[0] if ins.data else {}
        db_id = saved_row.get("id") if saved_row else None
        if db_id:
            inserted_db_ids.append(str(db_id))

        results.append({
            "id": db_id,
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
    idempotency_key: Optional[str] = Form(default=None),  # R4: 클라이언트 중복 방지 키
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

        # R4: 파일 있을 때 서명키 미리 확인 — 없으면 첨부 후 재시도 불능 → 503 선차단
        if validated:
            try:
                _get_upload_signing_key()
            except RuntimeError:
                raise HTTPException(
                    status_code=503,
                    detail="첨부 서비스를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
                )

    supabase = get_supabase()

    # 중복 방지 — client_key → HMAC 파생 inquiry_id (contact-idem-v1 R2)
    # client_key와 inquiry_id는 서버 비밀키 없이 상호 도출 불가
    derived_id = _derive_inquiry_id(idempotency_key)
    if derived_id:
        idem_check = (
            supabase.table("inquiries")
            .select("id, created_at")
            .eq("id", derived_id)
            .limit(1)
            .execute()
        )
        if idem_check.data:
            existing = idem_check.data[0]
            return _build_existing_response(
                supabase,
                str(existing["id"]),
                existing.get("created_at", ""),
            )

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
    if derived_id:
        row["id"] = derived_id  # HMAC 파생 ID → DB PRIMARY KEY
    try:
        res = supabase.table("inquiries").insert(row).execute()
    except Exception as e:
        # 동시 요청 충돌(unique 위반) → SELECT 재조회
        if derived_id and any(k in str(e).lower() for k in ("unique", "duplicate", "23505")):
            conflict_res = (
                supabase.table("inquiries")
                .select("id, created_at")
                .eq("id", derived_id)
                .limit(1)
                .execute()
            )
            if conflict_res.data:
                existing = conflict_res.data[0]
                return _build_existing_response(
                    supabase,
                    str(existing["id"]),
                    existing.get("created_at", ""),
                )
        raise HTTPException(status_code=500, detail="저장 실패")

    saved = res.data[0] if res.data else row
    inquiry_id = str(saved.get("id", "")) if saved else ""

    # ③ 파일 업로드 (문의 생성 성공 후)
    attach_status = "ok"
    attach_results = []
    if validated:
        if not inquiry_id:
            # R2: 파일이 있는데 inquiry_id 없으면 성공으로 처리 금지
            attach_status = "failed"
        else:
            attach_results, err = await _upload_attachments(supabase, validated, inquiry_id)
            if err:
                attach_status = "failed"

    # ④ 재시도용 업로드 토큰 생성 (inquiry_id 있을 때만)
    upload_token = None
    if inquiry_id:
        try:
            created_at_str = saved.get("created_at", "")
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            upload_token = _generate_upload_token(inquiry_id, created_at)
        except Exception:
            pass

    return {
        "status": "success",
        "data": saved,
        "upload_token": upload_token,
        "attachments_status": attach_status,
        "attachments": attach_results,
    }


# ── POST /contacts/{inquiry_id}/attachments (첨부 재시도, 60분 창) ──────

@router.post("/contacts/{inquiry_id}/attachments")
async def retry_contact_attachments(
    inquiry_id: str,
    files: List[UploadFile] = File(...),
    x_upload_token: Optional[str] = Header(None, alias="X-Upload-Token"),
):
    """공개 문의 파일 첨부 재시도 — 소유자 토큰 + 접수 후 60분 이내, 최대 5개"""
    parsed_id = _parse_inquiry_uuid(inquiry_id)

    # R2: 토큰 없으면 즉시 거부 (401)
    if not x_upload_token:
        raise HTTPException(status_code=401, detail="첨부 재시도 권한이 없습니다.")

    supabase = get_supabase()

    # inquiry 존재 확인
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

    # R2: 토큰 검증 (문의 소유자 확인 — 타인의 UUID로는 불가)
    if not _verify_upload_token(x_upload_token, parsed_id, created_str):
        raise HTTPException(status_code=403, detail="유효하지 않은 첨부 권한입니다.")

    # R2: 60분 창 확인 — 파싱 실패 시 허용하지 않고 차단
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
        # R2: 타임스탬프 파싱 실패 시 차단 (R1에서는 pass였음)
        raise HTTPException(status_code=403, detail="첨부 시간 검증에 실패했습니다.")

    if not files:
        raise HTTPException(status_code=400, detail="파일이 없습니다.")
    if len(files) > CONTACT_ATTACH_MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"파일은 최대 {CONTACT_ATTACH_MAX_FILES}개까지 첨부할 수 있습니다.",
        )

    # 기존 첨부 목록 조회 — dedup 판단 겸용 (name+size 기준)
    existing_rows = (
        supabase.table("attachments")
        .select("id, file_name, file_size")
        .eq("table_name", "inquiries")
        .eq("record_id", parsed_id)
        .execute()
    )
    already_stored = {
        (r.get("file_name"), r.get("file_size"))
        for r in (existing_rows.data or [])
    }
    already_count = len(existing_rows.data or [])

    # 파일 검증
    validated = []
    for f in files:
        validated.append(await _read_and_validate(f))

    # 중복 제외 실제 신규 수로 한도 확인
    # (부분 저장 후 재시도 시 이미 저장된 파일을 제외해 거짓 거부 방지)
    net_new = sum(
        1 for raw, fname, ext, mime in validated
        if (fname, len(raw)) not in already_stored
    )
    if already_count + net_new > CONTACT_ATTACH_MAX_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"첨부 파일 한도({CONTACT_ATTACH_MAX_FILES}개)를 초과합니다.",
        )

    # 업로드 (_upload_attachments 내부에서 dedup 재확인)
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
