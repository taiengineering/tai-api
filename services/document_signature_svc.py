"""Document Signature Service — OBJ02-C2-SIG-B

Profile Signature + Document Signature Snapshot contract.

Bucket: company-docs (private)
Profile path:  signatures/profile/{user_id}/{sha256}.png
Document path: signatures/document/{runtime_document_id}/{runtime_field_id}/{sha256}.png

Stable reference format: storage://company-docs/<path>

금지:
  - public Storage URL을 canonical truth로 사용
  - dataURL을 DB 문자열 값으로 저장
  - client timestamp / client signer_id 신뢰
  - 새 bucket 생성 / 새 column 생성 / migration 생성
  - Production DB writes outside this module's narrow contract
"""
from __future__ import annotations

import base64
import hashlib
import re as _re
import struct
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase
from services.time import now_kst, serialize_external_utc

_BUCKET = "company-docs"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB
_MAX_WIDTH = 4096
_MAX_HEIGHT = 2048
_STORAGE_PREFIX = "storage://company-docs/"

_EDITABLE_STATUSES = frozenset({"DRAFT", "IN_PROGRESS", "RETURNED_FOR_EDIT"})


class SignatureError(ValueError):
    """Signature operation failure — maps to HTTP 400/422."""


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_storage_ref(ref: str) -> str:
    """Parse 'storage://company-docs/some/path.png' → 'some/path.png'."""
    if not isinstance(ref, str) or not ref.startswith(_STORAGE_PREFIX):
        raise SignatureError(f"invalid storage_ref: {ref!r}")
    path = ref[len(_STORAGE_PREFIX):]
    if not path:
        raise SignatureError("storage_ref path is empty")
    return path


def _compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_png(data: bytes) -> None:
    """Validate PNG magic bytes, max file size, and max dimensions."""
    if len(data) > _MAX_BYTES:
        raise SignatureError(f"PNG exceeds max size {_MAX_BYTES} bytes")
    if len(data) < 24:
        raise SignatureError("data too short to be a valid PNG")
    if data[:8] != _PNG_MAGIC:
        raise SignatureError("not a valid PNG (magic bytes mismatch)")
    # IHDR: width at bytes 16-19, height at bytes 20-23
    width = struct.unpack(">I", data[16:20])[0]
    height = struct.unpack(">I", data[20:24])[0]
    if width > _MAX_WIDTH or height > _MAX_HEIGHT:
        raise SignatureError(
            f"PNG dimensions {width}x{height} exceed max {_MAX_WIDTH}x{_MAX_HEIGHT}"
        )


_DATA_URI_PREFIX = "data:image/png;base64,"
_MAX_ENCODED_BYTES = 2 * 1024 * 1024  # ~1.5× raw 1 MiB PNG ceiling

def _decode_data_uri(data_uri: str) -> bytes:
    """Decode data URI → raw bytes. Exact prefix 'data:image/png;base64,' only."""
    if not isinstance(data_uri, str) or not data_uri.startswith(_DATA_URI_PREFIX):
        raise SignatureError("only data:image/png;base64, data URIs are supported")
    b64 = data_uri[len(_DATA_URI_PREFIX):]
    if not b64:
        raise SignatureError("data URI payload is empty")
    if len(b64) > _MAX_ENCODED_BYTES:
        raise SignatureError(
            f"data URI encoded payload exceeds limit ({_MAX_ENCODED_BYTES} chars)"
        )
    try:
        return base64.b64decode(b64, validate=True)
    except Exception:
        raise SignatureError("invalid base64 in data URI")


def _bytes_to_data_uri(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _storage_ref(path: str) -> str:
    return f"{_STORAGE_PREFIX}{path}"


def _private_upload(sb, path: str, data: bytes) -> None:
    """Upload PNG to private company-docs bucket.

    Idempotent: if same path exists and SHA256 matches, skip silently.
    If path exists with different content: FAIL-CLOSE.
    """
    sha = _compute_sha256(data)
    try:
        sb.storage.from_(_BUCKET).upload(
            path=path,
            file=data,
            file_options={"content-type": "image/png"},
        )
    except Exception as up_err:
        err_str = str(up_err).lower()
        if any(k in err_str for k in ("already", "duplicate", "exists", "23505")):
            try:
                existing = sb.storage.from_(_BUCKET).download(path)
                if _compute_sha256(existing) == sha:
                    return  # identical content — idempotent reuse
            except Exception:
                pass
            raise SignatureError(f"storage collision at {path}: hash mismatch")
        raise SignatureError(f"storage upload failed: {up_err}")


def _private_download(sb, path: str) -> bytes:
    """Download from private company-docs bucket."""
    try:
        return sb.storage.from_(_BUCKET).download(path)
    except Exception as e:
        raise SignatureError(f"storage download failed for {path}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Profile Signature
# ─────────────────────────────────────────────────────────────────────────────

def save_profile_signature(
    user_id: str,
    data_uri: str,
) -> Dict[str, Any]:
    """Save authenticated user's profile signature.

    Writes PNG to: signatures/profile/{user_id}/{sha256}.png
    Updates: users.signature_url (stable ref), users.signature_registered_at (server clock)

    Returns:
        {"signature_url": "storage://...", "signature_registered_at": "...", "sha256": "..."}
    """
    png_bytes = _decode_data_uri(data_uri)
    _validate_png(png_bytes)
    sha = _compute_sha256(png_bytes)
    path = f"signatures/profile/{user_id}/{sha}.png"
    sb = get_supabase()
    _private_upload(sb, path, png_bytes)
    stable_ref = _storage_ref(path)
    now = serialize_external_utc(now_kst())
    update_res = sb.table("users").update({
        "signature_url": stable_ref,
        "signature_registered_at": now,
    }).eq("id", user_id).execute()
    if not update_res.data:
        raise SignatureError("profile signature update returned 0 rows — user record not found")
    return {
        "signature_url": stable_ref,
        "signature_registered_at": now,
        "sha256": sha,
    }


def get_profile_signature(user_id: str) -> Optional[Dict[str, Any]]:
    """Return profile signature data URI for preview. None if no signature registered.

    Returns:
        {"data_uri": "data:image/png;base64,...", "signature_registered_at": "..."}
        or None
    """
    sb = get_supabase()
    res = (
        sb.table("users")
        .select("signature_url,signature_registered_at")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if not res.data:
        return None
    ref = res.data.get("signature_url")
    if not ref:
        return None
    path = _parse_storage_ref(ref)
    data = _private_download(sb, path)
    _validate_png(data)
    return {
        "data_uri": _bytes_to_data_uri(data),
        "signature_registered_at": res.data.get("signature_registered_at"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Document Signature Apply
# ─────────────────────────────────────────────────────────────────────────────

def apply_profile_to_document(
    doc_id: str,
    field_key: str,
    current_user: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply authenticated user's profile signature to a document signature field.

    Contract:
    - Reads profile signature from users.signature_url (server SoT)
    - Downloads private PNG, validates, computes SHA256
    - Copies immutable snapshot to: signatures/document/{doc_id}/{field_id}/{sha256}.png
    - Writes structured signature_snapshot JSON to runtime_data_json[field_key]
    - signer_user_id and signed_at are server-determined (not client-supplied)

    Returns:
        {"signature_snapshot": {...}}

    Raises:
        SignatureError on any failure (maps to 400/422/404 at router level).
    """
    sb = get_supabase()
    user_id = str(current_user.get("id") or "").strip()
    if not user_id:
        raise SignatureError("authenticated user id unavailable")

    # 1. Load document — check editable status
    doc_res = (
        sb.table("runtime_document_data")
        .select("id,form_schema_id,runtime_data_json,status,version,updated_at")
        .eq("id", doc_id)
        .single()
        .execute()
    )
    if not doc_res.data:
        raise SignatureError("document not found")
    doc = doc_res.data
    expected_updated_at = doc.get("updated_at")

    if doc["status"] not in _EDITABLE_STATUSES:
        raise SignatureError(
            f"document status '{doc['status']}' does not allow editing; "
            f"editable: {sorted(_EDITABLE_STATUSES)}"
        )

    # 2. Verify field exists in schema and is signature type
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
        raise SignatureError(f"field_key not found in schema: {field_key!r}")
    field_row = field_rows[0]
    if field_row.get("input_type") != "signature":
        raise SignatureError(
            f"field {field_key!r} is not a signature field "
            f"(input_type={field_row.get('input_type')!r})"
        )
    runtime_field_id = str(field_row["id"])

    # 3. Load user's profile signature
    user_res = (
        sb.table("users")
        .select("signature_url,signature_registered_at")
        .eq("id", user_id)
        .single()
        .execute()
    )
    if not user_res.data or not user_res.data.get("signature_url"):
        raise SignatureError("no profile signature registered for this user")
    profile_ref = user_res.data["signature_url"]
    profile_registered_at = user_res.data.get("signature_registered_at")

    # 4. Download and validate profile signature bytes
    profile_path = _parse_storage_ref(profile_ref)
    png_bytes = _private_download(sb, profile_path)
    _validate_png(png_bytes)
    sha = _compute_sha256(png_bytes)

    # 5. Write immutable document snapshot copy
    doc_path = f"signatures/document/{doc_id}/{runtime_field_id}/{sha}.png"
    _private_upload(sb, doc_path, png_bytes)
    doc_storage_ref = _storage_ref(doc_path)

    # 6. Build immutable signature snapshot
    now = serialize_external_utc(now_kst())
    snapshot: Dict[str, Any] = {
        "_type": "signature_snapshot",
        "version": 1,
        "field_id": runtime_field_id,
        "field_key": field_key,
        "storage_ref": doc_storage_ref,
        "sha256": sha,
        "mime_type": "image/png",
        "byte_size": len(png_bytes),
        "signer_user_id": user_id,
        "signed_at": now,
        "source": "PROFILE_SIGNATURE",
        "profile_signature_registered_at": profile_registered_at,
    }

    # 7. Merge into runtime_data_json — optimistic concurrency guard (CORR-01)
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
        raise SignatureError(
            "DOCUMENT_SIGNATURE_CONFLICT: document was modified concurrently or status changed"
        )

    return {"signature_snapshot": snapshot}


# ─────────────────────────────────────────────────────────────────────────────
# Signature resolution for renderer
# ─────────────────────────────────────────────────────────────────────────────

_SHA256_RE = _re.compile(r'^[0-9a-f]{64}$')


def _validate_snapshot_canonical(
    fkey: str,
    val: Any,
    expected_field_id: str,
    document_id: Optional[str] = None,
) -> None:
    """Validate canonical snapshot structure. Raises SignatureError on any violation."""
    if not isinstance(val, dict):
        raise SignatureError(
            f"signature field {fkey!r}: expected object, got {type(val).__name__}"
        )
    if val.get("_type") != "signature_snapshot":
        raise SignatureError(
            f"signature field {fkey!r}: _type must be 'signature_snapshot'"
        )
    if val.get("version") != 1:
        raise SignatureError(
            f"signature field {fkey!r}: unsupported snapshot version {val.get('version')!r}"
        )
    if val.get("field_key") != fkey:
        raise SignatureError(
            f"signature field {fkey!r}: field_key mismatch in snapshot {val.get('field_key')!r}"
        )
    if expected_field_id and str(val.get("field_id", "")) != expected_field_id:
        raise SignatureError(
            f"signature field {fkey!r}: field_id mismatch "
            f"(expected={expected_field_id!r}, got={str(val.get('field_id', ''))!r})"
        )
    if val.get("mime_type") != "image/png":
        raise SignatureError(
            f"signature field {fkey!r}: mime_type must be 'image/png'"
        )
    byte_size = val.get("byte_size")
    if not isinstance(byte_size, int) or isinstance(byte_size, bool) or byte_size <= 0:
        raise SignatureError(
            f"signature field {fkey!r}: byte_size must be a positive integer"
        )
    sha_val = val.get("sha256", "")
    if not _SHA256_RE.match(str(sha_val)):
        raise SignatureError(
            f"signature field {fkey!r}: sha256 must be a 64-char lowercase hex string"
        )
    if not val.get("signer_user_id"):
        raise SignatureError(f"signature field {fkey!r}: signer_user_id is required")
    if not val.get("signed_at"):
        raise SignatureError(f"signature field {fkey!r}: signed_at is required")
    if val.get("source") != "PROFILE_SIGNATURE":
        raise SignatureError(
            f"signature field {fkey!r}: source must be 'PROFILE_SIGNATURE'"
        )
    storage_ref = val.get("storage_ref")
    if not storage_ref:
        raise SignatureError(f"signature field {fkey!r}: storage_ref is required")
    if document_id:
        expected_prefix = (
            f"storage://company-docs/signatures/document/{document_id}/"
        )
        if not storage_ref.startswith(expected_prefix):
            raise SignatureError(
                f"signature field {fkey!r}: storage_ref does not match document path"
            )


def resolve_signature_images_for_render(
    runtime_data_json: Dict[str, Any],
    fields: List[Dict[str, Any]],
    document_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve signature field images for rendering (FAIL-CLOSE on non-null malformed snapshots).

    Downloads private PNG for each signature_snapshot in runtime_data_json,
    validates SHA256, returns data URIs + evidence manifest entries.

    Returns:
        {
            "images": {field_key: "data:image/png;base64,..."},
            "manifest": [{"type": "signature", ...}]
        }

    Hash mismatch or malformed non-null snapshot → raises SignatureError (FAIL-CLOSE).
    None value → treated as missing (no error).
    """
    images: Dict[str, str] = {}
    manifest: List[Dict[str, Any]] = []

    sig_fields = [f for f in fields if f.get("input_type") == "signature"]
    if not sig_fields:
        return {"images": images, "manifest": manifest}

    sb = get_supabase()
    for field in sig_fields:
        fkey = field.get("field_key")
        if not fkey:
            continue
        runtime_field_id = str(field.get("id", ""))
        val = runtime_data_json.get(fkey)
        if val is None:
            continue  # genuinely missing — OK

        # CORR-04: non-null → must be canonical; malformed → FAIL-CLOSE
        _validate_snapshot_canonical(fkey, val, runtime_field_id, document_id)

        storage_ref = val["storage_ref"]
        expected_sha = val["sha256"]

        path = _parse_storage_ref(storage_ref)
        data = _private_download(sb, path)
        actual_sha = _compute_sha256(data)
        if actual_sha != expected_sha:
            raise SignatureError(
                f"signature hash mismatch for field {fkey!r}: "
                f"expected {expected_sha}, got {actual_sha}"
            )
        if len(data) != val["byte_size"]:
            raise SignatureError(
                f"signature field {fkey!r}: byte_size mismatch "
                f"(snapshot={val['byte_size']}, actual={len(data)})"
            )
        _validate_png(data)
        images[fkey] = _bytes_to_data_uri(data)
        manifest.append({
            "type": "signature",
            "field_id": val.get("field_id"),
            "field_key": fkey,
            "storage_ref": storage_ref,
            "sha256": expected_sha,
            "mime_type": val.get("mime_type", "image/png"),
            "byte_size": val.get("byte_size"),
            "signer_user_id": val.get("signer_user_id"),
            "signed_at": val.get("signed_at"),
            "source": val.get("source"),
        })

    return {"images": images, "manifest": manifest}


def validate_required_signatures(
    runtime_data_json: Dict[str, Any],
    fields: List[Dict[str, Any]],
) -> None:
    """Raise SignatureError if any REQUIRED_BY_HUMAN signature field lacks a canonical snapshot."""
    for field in fields:
        if (field.get("input_type") == "signature"
                and field.get("required_status") == "REQUIRED_BY_HUMAN"):
            fkey = field.get("field_key")
            if not fkey:
                continue
            val = runtime_data_json.get(fkey)
            if not (isinstance(val, dict) and val.get("_type") == "signature_snapshot"):
                raise SignatureError(
                    f"required signature missing for field {fkey!r}"
                )
