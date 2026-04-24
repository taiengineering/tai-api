"""
services/upload_service.py — 사진 업로드 서비스
Supabase Storage 'inspections' 버킷에 파일 저장
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile

from db.supabase_client import get_supabase

BUCKET = "inspections"
MAX_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp"}
MIME_TO_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def _validate_file(file: UploadFile, contents: bytes) -> str:
    """파일 검증 후 확장자 반환."""
    # 크기 검증
    if len(contents) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="파일 크기 5MB 초과")

    # MIME 검증 (Content-Type 신뢰 금지 → magic bytes 확인)
    mime = _detect_mime(contents)
    if mime not in ALLOWED_MIMES:
        raise HTTPException(
            status_code=415,
            detail=f"허용되지 않은 파일 형식: {mime or file.content_type}. jpeg/png/webp만 가능",
        )
    return MIME_TO_EXT[mime]


def _detect_mime(data: bytes) -> str | None:
    """파일 magic bytes로 MIME 타입 감지."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def upload_inspection_photo(
    file: UploadFile,
    contents: bytes,
    context: str,
    user_id: str,
    inspection_id: str | None = None,
    factory_id: str | None = None,
    site_id: str | None = None,
) -> dict:
    """사진을 Supabase Storage에 업로드하고 public URL 반환."""
    ext = _validate_file(file, contents)

    # 경로 생성
    now = datetime.now(timezone.utc)
    ref_id = inspection_id or factory_id or site_id or "anon"
    seq = uuid.uuid4().hex[:8]
    path = f"{context}/{now.strftime('%Y/%m/%d')}/{ref_id}/{seq}.{ext}"

    # Supabase Storage 업로드
    supabase = get_supabase()
    try:
        supabase.storage.from_(BUCKET).upload(
            path, contents, {"content-type": f"image/{ext}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"스토리지 업로드 실패: {e}")

    url = supabase.storage.from_(BUCKET).get_public_url(path)

    return {
        "url": url,
        "path": f"{BUCKET}/{path}",
        "size": len(contents),
        "mime": f"image/{ext}",
    }
