"""
routers/uploads.py — v2.0.0 (Capability Wrapper Migration)
Wrapper: transport only (multipart parse, auth, adapter inject)
Capability: upload/core (validate, path build)
Adapter: upload/adapters (Supabase Storage)

v2.0.0 (2026-05-25): Thin wrapper migration — capability consume structure
v1.0.0 (2026-04-24): Initial
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from routers.auth import get_current_user
from db.supabase_client import get_supabase

router = APIRouter(prefix="/uploads", tags=["uploads"])

VALID_CONTEXTS = {"inspection", "report", "emergency", "tbm"}
BUCKET = "inspections"

# === Capability Core (inline until federation-contracts import available) ===

def _cap_validate_upload(contents: bytes, max_size: int = 5 * 1024 * 1024):
    """Capability core: file validation. DB/framework 모름."""
    if len(contents) > max_size:
        raise ValueError(f"File size {len(contents)} exceeds max {max_size}")
    mime = _cap_detect_mime(contents)
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if mime not in allowed:
        raise ValueError(f"Unsupported mime: {mime}")
    ext_map = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
    return {"valid": True, "mime": mime, "ext": ext_map[mime], "size": len(contents)}

def _cap_detect_mime(data: bytes):
    if data[:3] == b"\xff\xd8\xff": return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n": return "image/png"
    if data[:4] == b"RIFF" and len(data) > 11 and data[8:12] == b"WEBP": return "image/webp"
    return None

def _cap_build_path(context: str, ref_id: str, ext: str):
    import uuid
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    seq = uuid.uuid4().hex[:8]
    return f"{context}/{now.strftime('%Y/%m/%d')}/{ref_id}/{seq}.{ext}"

# === Adapter (Supabase Storage) ===

def _adapter_upload(contents: bytes, path: str, mime: str, supabase):
    """Adapter: Supabase Storage upload. capability가 호출하지 않음."""
    try:
        supabase.storage.from_(BUCKET).upload(path, contents, {"content-type": mime})
    except Exception as e:
        raise RuntimeError(f"스토리지 업로드 실패: {e}")
    url = supabase.storage.from_(BUCKET).get_public_url(path)
    return {"url": url, "path": f"{BUCKET}/{path}", "size": len(contents), "mime": mime}

# === Wrapper (transport only) ===

@router.post("/inspection-photo")
async def post_inspection_photo(
    file: UploadFile = File(...),
    context: str = Form("inspection"),
    inspection_id: Optional[str] = Form(None),
    factory_id: Optional[str] = Form(None),
    site_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """점검/신고/긴급/TBM 사진 업로드. 기존 API 100% 호환."""
    # 1. Request parse (wrapper)
    if context not in VALID_CONTEXTS:
        raise HTTPException(status_code=400, detail=f"context는 {VALID_CONTEXTS} 중 하나여야 합니다")
    contents = await file.read()

    # 2. Capability core (framework/DB 모름)
    try:
        result = _cap_validate_upload(contents)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    ref_id = inspection_id or factory_id or site_id or "anon"
    path = _cap_build_path(context, ref_id, result["ext"])

    # 3. Adapter inject (wrapper가 주입)
    upload_result = _adapter_upload(contents, path, result["mime"], get_supabase())

    # 4. Response format (wrapper)
    return upload_result
