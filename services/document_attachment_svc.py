"""Document Attachment Service — WO-TAI-DOCUMENT-260-P1B-SECURE-ATTACHMENT-IMPLEMENT-001

File/image field snapshot contract.

Bucket: company-docs (private)
Path:   attachments/document/{doc_id}/{field_id}/{sha256}.{ext}

Stable reference: storage://company-docs/attachments/document/{doc_id}/{field_id}/{sha256}.{ext}

Owner decisions pending (OD-B02, OD-B03, OD-B04 PENDING_OWNER — 2026-10-24):
  ALLOWED_MIME_TYPES: proposed whitelist — Owner 확정 필요
  MAX_FILE_BYTES:     50 MB — Owner 확정 필요
  Storage path format: OD-B04 proposal — Owner 확정 필요

금지:
  - client-supplied sha256 / uploaded_at / uploaded_by_user_id 신뢰
  - Storage 실존 검증 없이 경로 등록 (T07-B 교훈)
  - public Storage URL을 canonical truth로 사용
  - 새 bucket / 새 column / migration 생성
  - Production DB writes outside this module's narrow contract
"""
from __future__ import annotations

import base64 as _base64
import hashlib
import logging as _logging
import re as _re
from typing import Any, Dict, List

from db.supabase_client import get_supabase
from services.time import now_kst, serialize_external_utc

_log = _logging.getLogger(__name__)

_BUCKET = "company-docs"
_STORAGE_PREFIX = "storage://company-docs/"
_ATTACH_PREFIX = "attachments/document"  # OD-B04 PENDING_OWNER: proposed prefix

# OD-B02 PENDING_OWNER: proposed MIME whitelist for file fields
ALLOWED_FILE_MIME_TYPES = frozenset({
    "application/pdf",
    "image/jpeg",
    "image/png",
    "application/haansoft-hwp",
    "application/x-hwp",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
})

# OD-B02 PENDING_OWNER: proposed MIME whitelist for image fields
ALLOWED_IMAGE_MIME_TYPES = frozenset({
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
})

# OD-B03 PENDING_OWNER: proposed size limit (50 MB)
MAX_FILE_BYTES = 50 * 1024 * 1024

_EDITABLE_STATUSES = frozenset({"DRAFT", "IN_PROGRESS", "RETURNED_FOR_EDIT"})

# OD-B06 HOLD PENDING_OWNER: blocked pending Owner source-form confirmation
_OD_B06_HOLD_FIELD_KEYS: frozenset = frozenset({
    "attached_documents_list",
    "attached_plan_list",
})


class AttachmentError(ValueError):
    """File attachment operation failure — maps to HTTP 400/422/404/409 at router."""


def _compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _storage_ref(path: str) -> str:
    return f"{_STORAGE_PREFIX}{path}"


def _ext_from_filename(filename: str) -> str:
    if "." in filename:
        return filename.rsplit(".", 1)[-1].lower()
    return ""


def _upload_bytes(sb, path: str, data: bytes, mime_type: str) -> bool:
    """Upload file to private company-docs bucket.

    Returns:
        True  — new file was uploaded (orphan cleanup required if DB write fails)
        False — path already existed, idempotent reuse (must NOT delete on DB failure)
    """
    try:
        sb.storage.from_(_BUCKET).upload(
            path=path,
            file=data,
            file_options={"content-type": mime_type},
        )
        return True
    except Exception as up_err:
        err_str = str(up_err).lower()
        if any(k in err_str for k in ("already", "duplicate", "exists", "23505")):
            return False  # idempotent reuse — existing file preserved, do not delete
        raise AttachmentError(f"storage upload failed: {up_err}")


# Magic byte prefixes for MIME verification — second-layer check (no library dependency)
_MAGIC: Dict[str, bytes] = {
    "application/pdf": b"%PDF",
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/gif_87": b"GIF87a",
    "image/gif_89": b"GIF89a",
    "image/webp_riff": b"RIFF",
}
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0"   # HWP / DOC / XLS
_OOXML_MAGIC = b"PK\x03\x04"         # XLSX / DOCX (ZIP)
_OLE2_MIMES = frozenset({
    "application/haansoft-hwp", "application/x-hwp",
    "application/msword", "application/vnd.ms-excel",
})
_OOXML_MIMES = frozenset({
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
})


def _verify_magic_bytes(file_bytes: bytes, declared_mime: str) -> None:
    """Best-effort magic bytes verification — blocks trivially mislabeled uploads.

    Does not replace the MIME whitelist; adds a second layer.
    Passes silently for types without a registered signature.
    """
    if len(file_bytes) < 4:
        raise AttachmentError("file too small to determine type")
    head = file_bytes[:16]
    if declared_mime == "application/pdf":
        if not head.startswith(b"%PDF"):
            raise AttachmentError("file magic bytes do not match declared MIME (expected PDF)")
    elif declared_mime == "image/jpeg":
        if not head.startswith(b"\xff\xd8\xff"):
            raise AttachmentError("file magic bytes do not match declared MIME (expected JPEG)")
    elif declared_mime == "image/png":
        if not head.startswith(b"\x89PNG\r\n\x1a\n"):
            raise AttachmentError("file magic bytes do not match declared MIME (expected PNG)")
    elif declared_mime == "image/gif":
        if not (head.startswith(b"GIF87a") or head.startswith(b"GIF89a")):
            raise AttachmentError("file magic bytes do not match declared MIME (expected GIF)")
    elif declared_mime == "image/webp":
        if not (head.startswith(b"RIFF") and len(file_bytes) >= 12 and file_bytes[8:12] == b"WEBP"):
            raise AttachmentError("file magic bytes do not match declared MIME (expected WebP)")
    elif declared_mime in _OLE2_MIMES:
        if not head.startswith(_OLE2_MAGIC):
            raise AttachmentError("file magic bytes do not match declared MIME (expected OLE2 document)")
    elif declared_mime in _OOXML_MIMES:
        if not head.startswith(_OOXML_MAGIC):
            raise AttachmentError("file magic bytes do not match declared MIME (expected OOXML/ZIP)")


async def upload_file_to_field(
    doc_id: str,
    field_key: str,
    file_bytes: bytes,
    original_file_name: str,
    mime_type: str,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    """Upload a file to a document's file/image field.

    Contract (OD-B01 APPROVED — A안 조건부 승인):
    1. Verifies document editable status
    2. Resolves field_key → field_id from active schema (input_type must be file or image)
    3. Validates MIME type whitelist (OD-B02 PENDING_OWNER: proposed whitelist)
    4. Validates file size (OD-B03 PENDING_OWNER: 50 MB proposed limit)
    5. Computes sha256 server-side
    6. Uploads to storage (idempotent, sha256-keyed path)
    7. Assembles FileSnapshot and writes to runtime_data_json[field_key]

    Returns:
        {"file_snapshot": {...}}

    Raises:
        AttachmentError on any failure (maps to 400/404/409 at router).
    """
    sb = get_supabase()
    user_id = str(current_user.get("id") or "").strip()
    if not user_id:
        raise AttachmentError("authenticated user id unavailable")

    # 0. OD-B06 HOLD: server-side block for deferred field keys
    if field_key in _OD_B06_HOLD_FIELD_KEYS:
        raise AttachmentError(
            f"field_key {field_key!r} is currently HOLD pending Owner decision (OD-B06); "
            "attachment upload blocked"
        )

    # 1. Load document — check editable status
    doc_res = (
        sb.table("runtime_document_data")
        .select("id,form_schema_id,runtime_data_json,status,version,updated_at")
        .eq("id", doc_id)
        .single()
        .execute()
    )
    if not doc_res.data:
        raise AttachmentError("document not found")
    doc = doc_res.data
    expected_updated_at = doc.get("updated_at")

    if doc["status"] not in _EDITABLE_STATUSES:
        raise AttachmentError(
            f"document status '{doc['status']}' does not allow editing; "
            f"editable: {sorted(_EDITABLE_STATUSES)}"
        )

    # 2. Verify field exists in schema and has file/image type
    schema_id = doc["form_schema_id"]
    field_res = (
        sb.table("runtime_field")
        .select("id,field_key,input_type")
        .eq("form_schema_id", schema_id)
        .eq("field_key", field_key)
        .execute()
    )
    field_rows = field_res.data or []
    if not field_rows:
        raise AttachmentError(f"field_key not found in schema: {field_key!r}")
    field_row = field_rows[0]
    input_type = field_row.get("input_type")
    if input_type not in ("file", "image"):
        raise AttachmentError(
            f"field {field_key!r} is not a file/image field "
            f"(input_type={input_type!r})"
        )
    runtime_field_id = str(field_row["id"])

    # 3. Validate MIME type (OD-B02 PENDING_OWNER: proposed whitelist)
    if input_type == "image":
        allowed = ALLOWED_IMAGE_MIME_TYPES
    else:
        allowed = ALLOWED_FILE_MIME_TYPES
    if mime_type not in allowed:
        raise AttachmentError(
            f"mime_type {mime_type!r} not allowed for {input_type} fields; "
            f"allowed: {sorted(allowed)}"
        )

    # 4. Validate file size (OD-B03 PENDING_OWNER: 50 MB proposed limit)
    byte_count = len(file_bytes)
    if byte_count == 0:
        raise AttachmentError("file is empty")
    if byte_count > MAX_FILE_BYTES:
        mb = byte_count / (1024 * 1024)
        raise AttachmentError(
            f"file size {mb:.1f} MB exceeds limit of {MAX_FILE_BYTES // (1024 * 1024)} MB"
        )

    # 4a. Magic bytes check — second layer beyond MIME header trust
    _verify_magic_bytes(file_bytes, mime_type)

    # 5. Compute sha256 server-side
    sha = _compute_sha256(file_bytes)

    # 6. Build storage path (OD-B04 PENDING_OWNER: proposed format)
    #    attachments/document/{doc_id}/{field_id}/{sha256}.{ext}
    ext = _ext_from_filename(original_file_name)
    storage_path = f"{_ATTACH_PREFIX}/{doc_id}/{runtime_field_id}/{sha}"
    if ext:
        storage_path = f"{storage_path}.{ext}"
    doc_storage_ref = _storage_ref(storage_path)

    # 7. Upload to company-docs bucket (idempotent, sha256-keyed)
    is_new_upload = _upload_bytes(sb, storage_path, file_bytes, mime_type)

    # 8. Assemble FileSnapshot
    now = serialize_external_utc(now_kst())
    snapshot: Dict[str, Any] = {
        "_type": "file_snapshot",
        "version": 1,
        "field_id": runtime_field_id,
        "field_key": field_key,
        "storage_ref": doc_storage_ref,
        "sha256": sha,
        "mime_type": mime_type,
        "byte_size": byte_count,
        "original_file_name": original_file_name,
        "uploaded_by_user_id": user_id,
        "uploaded_at": now,
    }

    # 9. Merge into runtime_data_json — optimistic concurrency guard
    existing_json = doc.get("runtime_data_json") or {}
    merged = {**existing_json, field_key: snapshot}
    update_res = (
        sb.table("runtime_document_data")
        .update({"runtime_data_json": merged, "updated_at": now})
        .eq("id", doc_id)
        .eq("updated_at", expected_updated_at)
        .in_("status", list(_EDITABLE_STATUSES))
        .execute()
    )
    if not update_res.data:
        # Orphan cleanup: only safe when THIS request uploaded a NEW file.
        # If the path was reused (idempotent), the file belongs to a prior upload — do NOT delete.
        if is_new_upload:
            try:
                sb.storage.from_(_BUCKET).remove([storage_path])
            except Exception as cleanup_err:
                # Log for manual recovery — do not suppress silently
                _log.warning(
                    "orphan_storage_cleanup_failed path=%r error=%r doc_id=%r field_key=%r",
                    storage_path, str(cleanup_err), doc_id, field_key,
                )
        raise AttachmentError(
            "DOCUMENT_ATTACHMENT_CONFLICT: document was modified concurrently or status changed"
        )

    return {"file_snapshot": snapshot}


def get_file_signed_url(
    doc_id: str,
    field_key: str,
    current_user: Dict[str, Any],
    expires_in: int = 3600,
) -> str:
    """Get a signed download URL for a file snapshot field.

    Returns:
        Signed URL string

    Raises:
        AttachmentError if not found or validation fails.
    """
    sb = get_supabase()

    doc_res = (
        sb.table("runtime_document_data")
        .select("id,form_schema_id,runtime_data_json")
        .eq("id", doc_id)
        .single()
        .execute()
    )
    if not doc_res.data:
        raise AttachmentError("document not found")

    rdj = doc_res.data.get("runtime_data_json") or {}
    snapshot = rdj.get(field_key)
    if not snapshot or not isinstance(snapshot, dict):
        raise AttachmentError(f"no file snapshot for field {field_key!r}")
    if snapshot.get("_type") != "file_snapshot":
        raise AttachmentError(f"field {field_key!r} is not a file_snapshot")

    # Binding validation: verify storage_ref path matches doc_id/field_id from schema
    schema_id = doc_res.data.get("form_schema_id")
    field_res = (
        sb.table("runtime_field")
        .select("id")
        .eq("form_schema_id", schema_id)
        .eq("field_key", field_key)
        .execute()
    )
    field_rows = field_res.data or []
    if not field_rows:
        raise AttachmentError(f"field_key not found in schema: {field_key!r}")
    runtime_field_id = str(field_rows[0]["id"])

    expected_path_prefix = f"{_ATTACH_PREFIX}/{doc_id}/{runtime_field_id}/"
    storage_ref = snapshot.get("storage_ref", "")
    if not storage_ref.startswith(_STORAGE_PREFIX):
        raise AttachmentError(f"invalid storage_ref: {storage_ref!r}")
    path = storage_ref[len(_STORAGE_PREFIX):]
    if not path.startswith(expected_path_prefix):
        raise AttachmentError(
            f"storage_ref path mismatch for field {field_key!r}: "
            f"expected prefix {expected_path_prefix!r}"
        )

    try:
        result = sb.storage.from_(_BUCKET).create_signed_url(path, expires_in)
        signed_url = result.get("signedURL") or result.get("signed_url")
        if not signed_url:
            raise AttachmentError("storage signed URL creation returned empty")
        return signed_url
    except AttachmentError:
        raise
    except Exception as e:
        raise AttachmentError(f"signed URL error: {e}")


async def remove_file_from_field(
    doc_id: str,
    field_key: str,
    current_user: Dict[str, Any],
) -> None:
    """Remove a file snapshot from a document field.

    Sets runtime_data_json[field_key] = None with optimistic concurrency.
    Storage file is NOT deleted (sha256-idempotent path — safe to retain).

    Raises:
        AttachmentError on any failure.
    """
    sb = get_supabase()
    user_id = str(current_user.get("id") or "").strip()
    if not user_id:
        raise AttachmentError("authenticated user id unavailable")

    # OD-B06 HOLD: also blocked for remove
    if field_key in _OD_B06_HOLD_FIELD_KEYS:
        raise AttachmentError(
            f"field_key {field_key!r} is currently HOLD pending Owner decision (OD-B06)"
        )

    doc_res = (
        sb.table("runtime_document_data")
        .select("id,form_schema_id,runtime_data_json,status,updated_at")
        .eq("id", doc_id)
        .single()
        .execute()
    )
    if not doc_res.data:
        raise AttachmentError("document not found")
    doc = doc_res.data
    expected_updated_at = doc.get("updated_at")

    if doc["status"] not in _EDITABLE_STATUSES:
        raise AttachmentError(
            f"document status '{doc['status']}' does not allow editing; "
            f"editable: {sorted(_EDITABLE_STATUSES)}"
        )

    schema_id = doc["form_schema_id"]
    field_res = (
        sb.table("runtime_field")
        .select("id,field_key,input_type")
        .eq("form_schema_id", schema_id)
        .eq("field_key", field_key)
        .execute()
    )
    field_rows = field_res.data or []
    if not field_rows:
        raise AttachmentError(f"field_key not found in schema: {field_key!r}")
    if field_rows[0].get("input_type") not in ("file", "image"):
        raise AttachmentError(
            f"field {field_key!r} is not a file/image field "
            f"(input_type={field_rows[0].get('input_type')!r})"
        )

    now = serialize_external_utc(now_kst())
    existing_json = doc.get("runtime_data_json") or {}
    merged = {**existing_json, field_key: None}
    update_res = (
        sb.table("runtime_document_data")
        .update({"runtime_data_json": merged, "updated_at": now})
        .eq("id", doc_id)
        .eq("updated_at", expected_updated_at)
        .in_("status", list(_EDITABLE_STATUSES))
        .execute()
    )
    if not update_res.data:
        raise AttachmentError(
            "DOCUMENT_ATTACHMENT_CONFLICT: document was modified concurrently or status changed"
        )


def resolve_attachment_images_for_render(
    runtime_data_json: Dict[str, Any],
    fields: List[Dict[str, Any]],
) -> Dict[str, str]:
    """Resolve image field snapshots to base64 data URIs for inline HTML rendering.

    Only processes fields with input_type == 'image' that hold a valid FileSnapshot.
    File fields render filename only — no inline data URI.

    Returns:
        {field_key: "data:{mime};base64,{b64}"} for successfully fetched images.
        Missing or failed fields are omitted (renderer falls back to filename).
    """
    sb = get_supabase()
    result: Dict[str, str] = {}

    image_keys = {
        f.get("field_key")
        for f in fields
        if f.get("input_type") == "image" and f.get("field_key")
    }

    for field_key in image_keys:
        snap = runtime_data_json.get(field_key)
        if not isinstance(snap, dict) or snap.get("_type") != "file_snapshot":
            continue
        storage_ref = snap.get("storage_ref", "")
        if not storage_ref.startswith(_STORAGE_PREFIX):
            continue
        path = storage_ref[len(_STORAGE_PREFIX):]
        mime_type = snap.get("mime_type") or "image/jpeg"

        try:
            file_bytes = sb.storage.from_(_BUCKET).download(path)
            b64 = _base64.b64encode(file_bytes).decode("ascii")
            result[field_key] = f"data:{mime_type};base64,{b64}"
        except Exception as fetch_err:
            # Fail open for rendering: image unavailable → renderer shows filename
            _log.warning(
                "attachment_image_fetch_failed field_key=%r path=%r error=%r",
                field_key, path, str(fetch_err),
            )

    return result
