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

import hashlib
import re as _re
from typing import Any, Dict

from db.supabase_client import get_supabase
from services.time import now_kst, serialize_external_utc

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


def _upload_bytes(sb, path: str, data: bytes, mime_type: str) -> None:
    """Upload file to private company-docs bucket.

    Idempotent: sha256-keyed path — if path already exists, silently skip.
    """
    try:
        sb.storage.from_(_BUCKET).upload(
            path=path,
            file=data,
            file_options={"content-type": mime_type},
        )
    except Exception as up_err:
        err_str = str(up_err).lower()
        if any(k in err_str for k in ("already", "duplicate", "exists", "23505")):
            return  # sha256-keyed path — identical content assumed, idempotent
        raise AttachmentError(f"storage upload failed: {up_err}")


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
    _upload_bytes(sb, storage_path, file_bytes, mime_type)

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
        .select("id,runtime_data_json")
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

    storage_ref = snapshot.get("storage_ref", "")
    if not storage_ref.startswith(_STORAGE_PREFIX):
        raise AttachmentError(f"invalid storage_ref: {storage_ref!r}")
    path = storage_ref[len(_STORAGE_PREFIX):]

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
