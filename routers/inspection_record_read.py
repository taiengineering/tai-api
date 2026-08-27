"""OBJ-05 CLOSEOUT-01 — inspection record read + authenticated photo upload.

canonical runtime:
    authenticated caller
    → ownership/scope guard (_ensure_inspection_own)
    → resolver passthrough (GET /record) 또는 document_svc 저장 (POST /photos)

invariant:
    - AUTH BEFORE READ/UPLOAD: get_current_user → ownership guard → resolver/storage.
    - GET /record 는 resolve_inspection_record 결과를 가공하지 않고 그대로 반환.
    - POST /photos 는 worker optional-auth 엔드포인트를 재사용하지 않는다.
    - signed URL 은 응답 preview 전용. DB 에는 photo_ref(stable storage://) 만 의미 있다.
    - 판단 로직 추가 금지.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from db.supabase_client import get_supabase
from routers.auth import get_current_user
from routers.inspection_checklist import _ensure_inspection_own
from services import document_svc
from services.inspection_record_resolver import InspectionRecordError, resolve_inspection_record
from services.upload_service import _detect_mime, _validate_file

router = APIRouter(prefix="/inspection", tags=["점검 레코드 Read"])

STORAGE_REF_PREFIX = "storage://company-docs/"
PHOTO_SIGNED_TTL_SECONDS = 600

_STATUS_404 = frozenset({"INSPECTION_NOT_FOUND"})
_STATUS_409 = frozenset({
    "LEGACY_STATUS_UNRESOLVED",
    "RESULT_CODE_UNRESOLVED",
    "JOURNAL_REVISION_GAP",
})


def _raise_resolver_http(exc: InspectionRecordError) -> None:
    code = exc.code
    if code in _STATUS_404:
        status = 404
    elif code in _STATUS_409:
        status = 409
    else:
        status = 500
    raise HTTPException(status_code=status, detail={"code": code})


def _inspection_factory_id(sb, inspection_id: str):
    insp = (
        sb.table("safety_inspections")
        .select("id, factory_id")
        .eq("id", inspection_id)
        .limit(1)
        .execute()
    )
    rows = insp.data or []
    if not rows:
        return None
    return rows[0].get("factory_id")


def _signed_preview_url(sb, storage_path: str) -> str | None:
    try:
        result = sb.storage.from_(document_svc.BUCKET).create_signed_url(
            storage_path, PHOTO_SIGNED_TTL_SECONDS
        )
    except Exception:
        return None
    if isinstance(result, dict):
        return result.get("signedURL") or result.get("signed_url")
    return None


@router.get("/{inspection_id}/record")
async def get_inspection_record(
    inspection_id: str,
    current: dict = Depends(get_current_user),
):
    """현재 유효 점검 레코드를 resolver 결과 그대로 반환 (READ-ONLY)."""
    sb = get_supabase()
    _ensure_inspection_own(sb, inspection_id, current)
    try:
        return resolve_inspection_record(inspection_id, sb)
    except InspectionRecordError as exc:
        _raise_resolver_http(exc)


@router.post("/{inspection_id}/photos")
async def upload_inspection_photo(
    inspection_id: str,
    file: UploadFile = File(...),
    current: dict = Depends(get_current_user),
):
    """점검 사진 1장 업로드. 저장 정본은 storage:// photo_ref. signed URL 은 preview 만."""
    sb = get_supabase()
    _ensure_inspection_own(sb, inspection_id, current)

    contents = await file.read()
    ext = _validate_file(file, contents)
    mime = _detect_mime(contents)
    if not mime:
        raise HTTPException(status_code=415, detail="허용되지 않은 파일 형식입니다. jpeg/png/webp만 가능")

    company_id = current.get("company_id")
    if not company_id:
        raise HTTPException(status_code=400, detail="회사 정보를 확인할 수 없습니다.")

    factory_id = _inspection_factory_id(sb, inspection_id)
    file_name = file.filename or f"inspection.{ext}"

    doc = await document_svc.upload_document(
        file_bytes=contents,
        file_name=file_name,
        mime_type=mime,
        company_id=company_id,
        category="inspection",
        factory_id=factory_id,
        linked_table="safety_inspections",
        linked_id=inspection_id,
        uploaded_by=current.get("id"),
    )
    storage_path = (doc or {}).get("storage_path") or ""
    photo_ref = f"{STORAGE_REF_PREFIX}{storage_path}"
    preview_url = _signed_preview_url(sb, storage_path)

    return {"photo_ref": photo_ref, "preview_url": preview_url}
