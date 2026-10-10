"""
Reference Form public API — WO-REF05-REF09-CMS-FILE-INTEGRATION-006
P0 repair: WO-REF05-REF09-INTEGRATION-P0-REPAIR-007
Final P0:  WO-REF05-REF09-INTEGRATION-FINAL-P0-008

GET /reference-forms/{slug}                         — public detail (PUBLISHED + CLEARED)
GET /reference-forms/{slug}/preview/{file_id}       — anonymous preview (no-store)
GET /reference-forms/{slug}/files/{file_id}/download — member download (auth, server proxy)

DB contract: PR #594 (20261011120000/1/2 migrations)
- View field: canonical_slug  (not slug)
- File PK:    reference_form_files.id  (not file_id)
- File path:  reference_form_files.file_ref          (storage://bucket/path format)
- Preview:    reference_form_preview_artifacts.preview_ref  (storage://bucket/path format)
- Preview SHA: reference_form_preview_artifacts.source_file_sha256
- Approval:   reference_form_approvals.approved_file_hashes  [{file_id, sha256}]

Security gates enforced at every request (not only at publish time):
  1. PUBLISHED + content_hash = approved_content_hash  (view WHERE clause)
  2. Active approval exists with is_current=true        (view JOIN)
  3. All active sources have rights_status = CLEARED    (_check_sources_cleared)
  4. File is QA_PASS + approved_at IS NOT NULL          (_find_qa_file + file row)
  5. SHA256 matches approval record                     (qa_pass_files cross-check)
  6. Preview: is_published=true, QA_PASS, SHA match     (preview artifact checks)
  7. file_id + SHA256 in current approved_file_hashes   (_verify_approval_binding — TOCTOU guard)
  8. Storage ref stripped and bucket validated           (_parse_storage_ref)
Storage paths and approval IDs are never returned to callers.
"""
from __future__ import annotations

import logging
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from supabase import Client

from db.supabase_client import get_supabase
from routers.auth import get_current_user

log = logging.getLogger("reference_forms")

router = APIRouter(prefix="/reference-forms", tags=["Reference forms"])

_VIEW = "reference_form_public_view"
_FILES = "reference_form_files"
_PREVIEW = "reference_form_preview_artifacts"
_CONTENT = "reference_form_content"
_SOURCES = "reference_form_sources"
_RELATIONS = "reference_form_relations"
_APPROVALS = "reference_form_approvals"

_MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024  # matches reference-forms bucket file_size_limit

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\-]")
_ALLOWED_BUCKETS = frozenset({"reference-forms", "reference-forms-preview"})


def _safe_filename(relative_path: str) -> str:
    raw = relative_path.rsplit("/", 1)[-1] if relative_path else "download"
    cleaned = _SAFE_FILENAME_RE.sub("_", raw)
    return cleaned or "download"


def _parse_storage_ref(raw_ref: str, expected_bucket: str) -> str:
    """
    Parse storage://bucket/path → return bucket-relative path for create_signed_url.
    Validates bucket is in the allowed set and matches expected_bucket.
    Blocks path traversal (any '..' segment). Raises 500 on invalid ref
    (violation of the internal DB data contract, not a caller error).
    """
    prefix = "storage://"
    if not raw_ref or not raw_ref.startswith(prefix):
        log.error("Storage ref missing storage:// prefix: %r", raw_ref)
        raise HTTPException(status_code=500, detail="STORAGE_REF_INVALID")

    rest = raw_ref[len(prefix):]
    slash_idx = rest.find("/")
    if slash_idx < 1:
        log.error("Storage ref missing bucket or path: %r", raw_ref)
        raise HTTPException(status_code=500, detail="STORAGE_REF_INVALID")

    bucket = rest[:slash_idx]
    path = rest[slash_idx + 1:]

    if bucket not in _ALLOWED_BUCKETS:
        log.error("Storage ref unknown bucket=%r in ref=%r", bucket, raw_ref)
        raise HTTPException(status_code=500, detail="STORAGE_REF_INVALID")
    if bucket != expected_bucket:
        log.error("Storage ref bucket mismatch: expected=%r got=%r", expected_bucket, bucket)
        raise HTTPException(status_code=500, detail="STORAGE_REF_INVALID")
    if not path or ".." in path.split("/"):
        log.error("Storage ref path invalid or traversal attempt: %r", path)
        raise HTTPException(status_code=500, detail="STORAGE_REF_INVALID")

    return path


# ---------------------------------------------------------------------------
# Shared query helpers
# ---------------------------------------------------------------------------

def _load_view_row(sb, canonical_slug: str) -> dict:
    """
    Query reference_form_public_view by canonical_slug.
    View already enforces: PUBLISHED, content_hash = approved_content_hash,
    is_current APPROVED approval exists.
    """
    try:
        res = (
            sb.table(_VIEW)
            .select("*")
            .eq("canonical_slug", canonical_slug)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        log.error("View query failed slug=%s: %s", canonical_slug, exc)
        raise HTTPException(status_code=503, detail="REFERENCE_FORM_UNAVAILABLE")
    if not res.data:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return res.data[0]


def _check_sources_cleared(sb, form_id: str) -> str:
    """
    Verify at least one active source exists and ALL are CLEARED.
    Returns source_name of first active source.
    Raises 404 if any source is REVIEW_REQUIRED or BLOCKED, or if none exist.
    Rights can change after publish, so this is re-checked per request.
    """
    try:
        res = (
            sb.table(_SOURCES)
            .select("source_name,rights_status")
            .eq("form_id", form_id)
            .eq("is_active", True)
            .execute()
        )
    except Exception as exc:
        log.error("Sources query failed form_id=%s: %s", form_id, exc)
        raise HTTPException(status_code=503, detail="REFERENCE_FORM_UNAVAILABLE")
    sources = res.data or []
    if not sources:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    for s in sources:
        if s.get("rights_status") != "CLEARED":
            raise HTTPException(status_code=404, detail="NOT_FOUND")
    return sources[0]["source_name"]


def _load_body_html(sb, form_id: str) -> str:
    """Load body_html from reference_form_content (lang=ko). Returns '' on error."""
    try:
        res = (
            sb.table(_CONTENT)
            .select("body_html")
            .eq("form_id", form_id)
            .eq("lang", "ko")
            .limit(1)
            .execute()
        )
    except Exception as exc:
        log.error("Content query failed form_id=%s: %s", form_id, exc)
        return ""
    return (res.data[0].get("body_html") or "") if res.data else ""


def _load_related_forms(sb, form_id: str) -> list:
    """
    Load published related forms via reference_form_relations.
    Checks the view so only PUBLISHED + CLEARED forms appear.
    """
    try:
        rel_res = (
            sb.table(_RELATIONS)
            .select("related_form_id")
            .eq("form_id", form_id)
            .execute()
        )
    except Exception:
        return []
    related_ids = [r["related_form_id"] for r in (rel_res.data or [])]
    if not related_ids:
        return []
    try:
        view_res = (
            sb.table(_VIEW)
            .select("canonical_slug,title")
            .in_("id", related_ids)
            .execute()
        )
    except Exception:
        return []
    return [
        {"slug": r["canonical_slug"], "title": r["title"]}
        for r in (view_res.data or [])
    ]


def _find_qa_file(view_row: dict, file_id: str) -> dict:
    """
    Find file_id in view's qa_pass_files JSONB array.
    Raises 404 if absent (file not approved / doesn't belong to this form).
    """
    qa_files = view_row.get("qa_pass_files") or []
    match = next((f for f in qa_files if str(f.get("file_id")) == file_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")
    return match


def _verify_approval_binding(sb, form_id: str, file_id: str, sha256: str) -> None:
    """
    Per-request TOCTOU guard: file_id + sha256 must be present in the current
    APPROVED approval's approved_file_hashes JSONB.  This is a fresh DB read
    separate from the view load so approval revocations take effect immediately
    even if the view was queried moments earlier.
    """
    try:
        res = (
            sb.table(_APPROVALS)
            .select("approved_file_hashes")
            .eq("form_id", form_id)
            .eq("is_current", True)
            .eq("approval_status", "APPROVED")
            .limit(1)
            .execute()
        )
    except Exception as exc:
        log.error("Approval query failed form_id=%s: %s", form_id, exc)
        raise HTTPException(status_code=503, detail="APPROVAL_CHECK_UNAVAILABLE")
    if not res.data:
        raise HTTPException(status_code=404, detail="FILE_NOT_APPROVED")
    approved_hashes = res.data[0].get("approved_file_hashes") or []
    match = next(
        (h for h in approved_hashes if str(h.get("file_id")) == file_id),
        None,
    )
    if not match:
        raise HTTPException(status_code=404, detail="FILE_NOT_APPROVED")
    if match.get("sha256") != sha256:
        raise HTTPException(status_code=404, detail="FILE_NOT_APPROVED")


# ---------------------------------------------------------------------------
# GET /reference-forms/{slug}
# ---------------------------------------------------------------------------

@router.get("/{slug}")
def get_reference_form(slug: str, sb: Client = Depends(get_supabase)):
    """
    Public detail.
    Gates: PUBLISHED, content hash approved, all active sources CLEARED.
    Never exposes storage paths, approval IDs, or internal file_ref.
    """
    view_row = _load_view_row(sb, slug)
    form_id = str(view_row["id"])

    source_name = _check_sources_cleared(sb, form_id)
    body_html = _load_body_html(sb, form_id)
    related_forms = _load_related_forms(sb, form_id)

    data = {
        "slug": view_row["canonical_slug"],
        "title": view_row["title"],
        "description": view_row.get("description"),
        "body_html": body_html,
        "source_name": source_name,
        "published_at": (
            str(view_row["published_at"]) if view_row.get("published_at") else None
        ),
        "qa_pass_files": view_row.get("qa_pass_files") or [],
        "formats": view_row.get("formats") or [],
        "related_forms": related_forms,
    }
    return {"status": "ok", "data": data}


# ---------------------------------------------------------------------------
# GET /reference-forms/{slug}/preview/{file_id}
# ---------------------------------------------------------------------------

@router.get("/{slug}/preview/{file_id}")
def get_reference_form_preview(slug: str, file_id: str, sb: Client = Depends(get_supabase)):
    """
    Anonymous preview.
    Gates: form PUBLISHED+CLEARED, file QA_PASS, preview is_published+QA_PASS+SHA match,
    file_id+SHA in current approved_file_hashes, storage ref parsed and validated.
    Proxied from reference-forms-preview bucket; no-store.
    """
    view_row = _load_view_row(sb, slug)
    form_id = str(view_row["id"])
    _check_sources_cleared(sb, form_id)

    qa_match = _find_qa_file(view_row, file_id)
    approved_sha256: str = qa_match.get("sha256", "")

    # Load file row → get preview_artifact_id and cross-check sha256
    try:
        file_res = (
            sb.table(_FILES)
            .select("id,form_id,sha256,preview_artifact_id,is_active,qa_status")
            .eq("id", file_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        log.error("File query failed file_id=%s: %s", file_id, exc)
        raise HTTPException(status_code=503, detail="PREVIEW_UNAVAILABLE")

    if not file_res.data:
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")

    file_row = file_res.data[0]
    if str(file_row.get("form_id", "")) != form_id:
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")
    if not file_row.get("is_active") or file_row.get("qa_status") != "QA_PASS":
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")
    if file_row.get("sha256") != approved_sha256:
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")

    preview_artifact_id = file_row.get("preview_artifact_id")
    if not preview_artifact_id:
        raise HTTPException(status_code=404, detail="PREVIEW_NOT_FOUND")

    # Load preview artifact
    try:
        pa_res = (
            sb.table(_PREVIEW)
            .select("form_id,preview_ref,source_file_sha256,is_published,qa_status")
            .eq("id", str(preview_artifact_id))
            .limit(1)
            .execute()
        )
    except Exception as exc:
        log.error("Preview artifact query failed id=%s: %s", preview_artifact_id, exc)
        raise HTTPException(status_code=503, detail="PREVIEW_UNAVAILABLE")

    if not pa_res.data:
        raise HTTPException(status_code=404, detail="PREVIEW_NOT_FOUND")

    pa = pa_res.data[0]
    if str(pa.get("form_id", "")) != form_id:
        raise HTTPException(status_code=404, detail="PREVIEW_NOT_FOUND")
    if not pa.get("is_published") or pa.get("qa_status") != "QA_PASS":
        raise HTTPException(status_code=404, detail="PREVIEW_NOT_FOUND")
    if pa.get("source_file_sha256") != approved_sha256:
        raise HTTPException(status_code=404, detail="PREVIEW_NOT_FOUND")

    # P0-2: per-request approval binding (TOCTOU guard)
    _verify_approval_binding(sb, form_id, file_id, approved_sha256)

    # P0-1: parse and validate storage ref → bucket-relative path for SDK
    preview_path = _parse_storage_ref(pa["preview_ref"], "reference-forms-preview")

    try:
        signed = sb.storage.from_("reference-forms-preview").create_signed_url(
            preview_path, expires_in=60
        )
        signed_url = signed.get("signedURL") or signed.get("signedUrl") or ""
        if not signed_url:
            raise ValueError("empty signed URL")
    except Exception as exc:
        log.error("Preview signed URL failed path=%s: %s", preview_path, exc)
        raise HTTPException(status_code=503, detail="PREVIEW_UNAVAILABLE")

    try:
        r = httpx.get(signed_url, follow_redirects=True, timeout=30)
        r.raise_for_status()
    except Exception as exc:
        log.error("Preview fetch failed path=%s: %s", preview_path, exc)
        raise HTTPException(status_code=502, detail="PREVIEW_FETCH_FAILED")

    content_type = r.headers.get("content-type", "application/pdf")
    return Response(
        content=r.content,
        media_type=content_type,
        headers={"Cache-Control": "no-store"},
    )


# ---------------------------------------------------------------------------
# GET /reference-forms/{slug}/files/{file_id}/download
# ---------------------------------------------------------------------------

@router.get("/{slug}/files/{file_id}/download")
def download_reference_form_file(
    slug: str,
    file_id: str,
    sb: Client = Depends(get_supabase),
    user: dict = Depends(get_current_user),
):
    """
    Member-only download.
    Gates: form PUBLISHED+CLEARED, file QA_PASS+approved_at+SHA match,
    file_id+SHA in current approved_file_hashes, storage ref parsed and validated.
    20 MB limit; server proxy from reference-forms bucket; no-store.
    Storage path (file_ref) never returned to caller.
    """
    view_row = _load_view_row(sb, slug)
    form_id = str(view_row["id"])
    _check_sources_cleared(sb, form_id)

    qa_match = _find_qa_file(view_row, file_id)
    approved_sha256: str = qa_match.get("sha256", "")

    # Load file row → get file_ref for storage proxy
    try:
        file_res = (
            sb.table(_FILES)
            .select("id,form_id,file_ref,sha256,is_active,qa_status,approved_at")
            .eq("id", file_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        log.error("File query failed file_id=%s: %s", file_id, exc)
        raise HTTPException(status_code=503, detail="DOWNLOAD_UNAVAILABLE")

    if not file_res.data:
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")

    file_row = file_res.data[0]
    if str(file_row.get("form_id", "")) != form_id:
        raise HTTPException(status_code=403, detail="FILE_NOT_IN_FORM")
    if not file_row.get("is_active") or file_row.get("qa_status") != "QA_PASS":
        raise HTTPException(status_code=404, detail="FILE_NOT_FOUND")
    if file_row.get("approved_at") is None:
        raise HTTPException(status_code=404, detail="FILE_NOT_APPROVED")
    if file_row.get("sha256") != approved_sha256:
        raise HTTPException(status_code=404, detail="HASH_MISMATCH")

    # P0-2: per-request approval binding (TOCTOU guard)
    _verify_approval_binding(sb, form_id, file_id, approved_sha256)

    # P0-1: parse and validate storage ref → bucket-relative path for SDK
    file_path = _parse_storage_ref(file_row["file_ref"], "reference-forms")
    filename = _safe_filename(file_path)

    try:
        signed = sb.storage.from_("reference-forms").create_signed_url(
            file_path, expires_in=30
        )
        signed_url = signed.get("signedURL") or signed.get("signedUrl") or ""
        if not signed_url:
            raise ValueError("empty signed URL")
    except Exception as exc:
        log.error("Signed URL failed file_id=%s: %s", file_id, exc)
        raise HTTPException(status_code=500, detail="DOWNLOAD_UNAVAILABLE")

    try:
        r = httpx.get(signed_url, follow_redirects=True, timeout=60)
        r.raise_for_status()
    except Exception as exc:
        log.error("File fetch failed file_id=%s: %s", file_id, exc)
        raise HTTPException(status_code=502, detail="FILE_FETCH_FAILED")

    if len(r.content) > _MAX_DOWNLOAD_BYTES:
        raise HTTPException(status_code=422, detail="FILE_TOO_LARGE")

    content_type = r.headers.get("content-type", "application/octet-stream")
    return Response(
        content=r.content,
        media_type=content_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
