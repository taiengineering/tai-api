"""
Reference Form public API — WO-REF05-REF09-CMS-FILE-INTEGRATION-006

GET /reference-forms/{slug}                       — public detail (PUBLISHED + CLEARED only)
GET /reference-forms/{slug}/preview/{file_id}     — anonymous preview (no-store)
GET /reference-forms/{slug}/files/{file_id}/download — member download (auth required)

Data source: reference_form_public_view (PR #594 schema).
Storage paths are never exposed in responses.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response

from db.supabase_client import get_supabase
from routers.auth import get_current_user

log = logging.getLogger("reference_forms")

router = APIRouter(prefix="/reference-forms", tags=["Reference forms"])

_VIEW = "reference_form_public_view"
_FILES_TABLE = "reference_form_files"
_PREVIEW_TABLE = "reference_form_preview_artifacts"


def _published_form(sb, slug: str) -> dict:
    """Fetch one row from the public view — 404 if absent (draft/unpublished/no-rights)."""
    try:
        res = sb.table(_VIEW).select("*").eq("slug", slug).limit(1).execute()
    except Exception as exc:
        log.error("reference_form_public_view query failed for slug=%s: %s", slug, exc)
        raise HTTPException(status_code=503, detail="REFERENCE_FORM_UNAVAILABLE")
    if not res.data:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return res.data[0]


def _find_qa_file(form: dict, file_id: str) -> dict:
    """Look up file_id in qa_pass_files JSONB array — 404 if not present."""
    qa_files = form.get("qa_pass_files") or []
    match = next((f for f in qa_files if str(f.get("file_id")) == file_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")
    return match


# ---------------------------------------------------------------------------
# GET /reference-forms/{slug}
# ---------------------------------------------------------------------------

@router.get("/{slug}")
def get_reference_form(slug: str):
    """Public detail — only PUBLISHED + rights_status=CLEARED forms visible."""
    sb = get_supabase()
    form = _published_form(sb, slug)
    return {"status": "ok", "data": form}


# ---------------------------------------------------------------------------
# GET /reference-forms/{slug}/preview/{file_id}
# ---------------------------------------------------------------------------

@router.get("/{slug}/preview/{file_id}")
def get_reference_form_preview(slug: str, file_id: str):
    """Anonymous preview — QA-approved preview artifact only, no-store."""
    sb = get_supabase()
    form = _published_form(sb, slug)
    _find_qa_file(form, file_id)

    try:
        res = sb.table(_PREVIEW_TABLE).select(
            "content_type,preview_data"
        ).eq("source_file_id", file_id).limit(1).execute()
    except Exception as exc:
        log.error("Preview query failed for file_id=%s: %s", file_id, exc)
        raise HTTPException(status_code=503, detail="PREVIEW_UNAVAILABLE")

    if not res.data:
        raise HTTPException(status_code=404, detail="PREVIEW_NOT_FOUND")

    artifact = res.data[0]
    return Response(
        content=artifact["preview_data"],
        media_type=artifact.get("content_type", "application/pdf"),
        headers={"Cache-Control": "no-store"},
    )


# ---------------------------------------------------------------------------
# GET /reference-forms/{slug}/files/{file_id}/download
# ---------------------------------------------------------------------------

@router.get("/{slug}/files/{file_id}/download")
def download_reference_form_file(
    slug: str,
    file_id: str,
    user: dict = Depends(get_current_user),
):
    """Member-only download — server proxy; storage path never exposed."""
    sb = get_supabase()
    form = _published_form(sb, slug)
    _find_qa_file(form, file_id)

    try:
        res = sb.table(_FILES_TABLE).select(
            "storage_path,content_type,file_name"
        ).eq("file_id", file_id).limit(1).execute()
    except Exception as exc:
        log.error("File table query failed for file_id=%s: %s", file_id, exc)
        raise HTTPException(status_code=503, detail="FILE_UNAVAILABLE")

    if not res.data:
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")

    row = res.data[0]
    storage_path: str = row["storage_path"]
    content_type: str = row.get("content_type") or "application/octet-stream"
    file_name: str = row.get("file_name") or "download"

    try:
        signed = sb.storage.from_("reference-forms").create_signed_url(
            storage_path, expires_in=30
        )
        signed_url = signed.get("signedURL") or signed.get("signedUrl") or ""
        if not signed_url:
            raise ValueError("empty signed URL")
    except Exception as exc:
        log.error("Signed URL failed for file_id=%s: %s", file_id, exc)
        raise HTTPException(status_code=500, detail="DOWNLOAD_UNAVAILABLE")

    try:
        r = httpx.get(signed_url, follow_redirects=True, timeout=30)
        r.raise_for_status()
    except Exception as exc:
        log.error("File proxy fetch failed for file_id=%s: %s", file_id, exc)
        raise HTTPException(status_code=502, detail="FILE_FETCH_FAILED")

    return Response(
        content=r.content,
        media_type=content_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{file_name}"',
        },
    )
