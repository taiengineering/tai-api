"""MSDS Customer Original Version — /me/msds/factories/{factory_id}/products/{product_id}/versions.

factory_id Canonical Scope 재사용 (OBJ-MSDS-02 strict auth).
documents pipeline 재사용 (company-docs bucket, company_id path).
Evidence Lock: register RPC 성공 후 document/storage 불변.
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from services.document_svc import BUCKET, _build_path, _get_ext, upload_document
from services.msds_product_svc import (
    MsdsProductError,
    _require_factory_scope,
)
from services.time import now_kst

# PDF magic bytes prefix
_PDF_MAGIC = b"%PDF-"
_PDF_MAX_BYTES = 20 * 1024 * 1024  # 20 MiB
_ALLOWED_EXTENSIONS = frozenset(["pdf"])
_ALLOWED_MIME = frozenset(["application/pdf"])

_RPC_REGISTER = "register_customer_msds_version"
_RPC_PROMOTE  = "promote_customer_msds_version"
_RPC_VOID     = "void_customer_msds_version"

_VALID_RPC_RESULTS = frozenset([
    "NEW_VERSION", "NO_CHANGE",
    "PROMOTED", "ALREADY_CURRENT",
    "VOIDED", "ALREADY_VOID",
])


# ─── PDF Validation ───────────────────────────────────────────────────────────

def validate_pdf(file_bytes: bytes, file_name: str, mime_type: str) -> None:
    """PDF 파일 유효성 검증. 실패 시 MsdsProductError 발생."""
    if not file_bytes:
        raise MsdsProductError(422, "INVALID_MSDS_PDF", "빈 파일은 허용되지 않습니다.")

    if len(file_bytes) > _PDF_MAX_BYTES:
        raise MsdsProductError(413, "MSDS_FILE_TOO_LARGE", f"MSDS 파일은 20MB 이하여야 합니다.")

    ext = _get_ext(file_name or "")
    if ext not in _ALLOWED_EXTENSIONS:
        raise MsdsProductError(422, "INVALID_MSDS_PDF", "PDF 파일만 허용됩니다.")

    if (mime_type or "").split(";")[0].strip().lower() not in _ALLOWED_MIME:
        raise MsdsProductError(422, "INVALID_MSDS_PDF", "MIME 타입이 application/pdf여야 합니다.")

    if not file_bytes.startswith(_PDF_MAGIC):
        raise MsdsProductError(422, "INVALID_MSDS_PDF", "유효한 PDF 파일이 아닙니다.")


# ─── Hash ────────────────────────────────────────────────────────────────────

def calculate_sha256(file_bytes: bytes) -> str:
    """SHA-256 lowercase hex."""
    return hashlib.sha256(file_bytes).hexdigest()


# ─── Document Contract Validation ────────────────────────────────────────────

def _require_valid_msds_document(
    sb,
    doc_id: str,
    factory_id: str,
    product_id: str,
) -> Dict[str, Any]:
    """documents 레코드의 MSDS contract 검증. 실패 시 MsdsProductError."""
    res = sb.table("documents").select("*").eq("id", doc_id).limit(1).execute()
    if not res.data:
        raise MsdsProductError(404, "DOCUMENT_NOT_FOUND", "문서를 찾을 수 없습니다.")

    doc = res.data[0]

    if not doc.get("is_active", True) or doc.get("deleted_at"):
        raise MsdsProductError(404, "DOCUMENT_NOT_FOUND", "문서를 찾을 수 없습니다.")

    if doc.get("category") != "msds":
        raise MsdsProductError(422, "DOCUMENT_INVALID_CATEGORY", "category=msds 문서만 허용됩니다.")

    if str(doc.get("factory_id") or "") != str(factory_id):
        raise MsdsProductError(422, "DOCUMENT_FACTORY_MISMATCH", "문서의 시설이 일치하지 않습니다.")

    if doc.get("linked_table") != "chemical_products":
        raise MsdsProductError(422, "DOCUMENT_LINKED_TABLE_MISMATCH", "문서 연결 테이블이 올바르지 않습니다.")

    if str(doc.get("linked_id") or "") != str(product_id):
        raise MsdsProductError(422, "DOCUMENT_LINKED_ID_MISMATCH", "문서 연결 제품이 일치하지 않습니다.")

    if str(doc.get("bucket_id") or "") != BUCKET:
        raise MsdsProductError(422, "DOCUMENT_INVALID_BUCKET", "문서 버킷이 올바르지 않습니다.")

    return doc


# ─── Duplicate Pre-check ─────────────────────────────────────────────────────

def _find_existing_sha(sb, product_id: str, sha256: str) -> Optional[Dict[str, Any]]:
    res = (
        sb.table("customer_msds_versions")
        .select("*")
        .eq("chemical_product_id", product_id)
        .eq("content_sha256", sha256)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


# ─── RPC helpers ─────────────────────────────────────────────────────────────

def _rpc_register(
    sb,
    factory_id: str,
    product_id: str,
    document_id: str,
    sha256: str,
    source_revision_date,
    source_revision_no,
    supplier_name,
    created_source: str,
    created_by,
) -> Dict[str, Any]:
    params = {
        "p_factory_id": factory_id,
        "p_chemical_product_id": product_id,
        "p_document_id": document_id,
        "p_content_sha256": sha256,
        "p_source_revision_date": source_revision_date,
        "p_source_revision_no": source_revision_no,
        "p_supplier_name": supplier_name,
        "p_created_source": created_source,
        "p_created_by": created_by,
    }
    res = sb.rpc(_RPC_REGISTER, params).execute()
    data = res.data if hasattr(res, "data") else res
    if isinstance(data, list):
        data = data[0] if data else {}
    return data or {}


def _rpc_promote(sb, factory_id: str, product_id: str, version_id: str) -> Dict[str, Any]:
    params = {
        "p_factory_id": factory_id,
        "p_chemical_product_id": product_id,
        "p_version_id": version_id,
    }
    res = sb.rpc(_RPC_PROMOTE, params).execute()
    data = res.data if hasattr(res, "data") else res
    if isinstance(data, list):
        data = data[0] if data else {}
    return data or {}


def _rpc_void(
    sb, factory_id: str, product_id: str, version_id: str, void_reason: str
) -> Dict[str, Any]:
    params = {
        "p_factory_id": factory_id,
        "p_chemical_product_id": product_id,
        "p_version_id": version_id,
        "p_void_reason": void_reason,
    }
    res = sb.rpc(_RPC_VOID, params).execute()
    data = res.data if hasattr(res, "data") else res
    if isinstance(data, list):
        data = data[0] if data else {}
    return data or {}


# ─── Version row fetch ────────────────────────────────────────────────────────

def _get_version_or_404(
    sb, factory_id: str, product_id: str, version_id: str
) -> Dict[str, Any]:
    res = (
        sb.table("customer_msds_versions")
        .select("*")
        .eq("id", version_id)
        .eq("chemical_product_id", product_id)
        .eq("factory_id", factory_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise MsdsProductError(404, "MSDS_VERSION_NOT_FOUND", "MSDS Version을 찾을 수 없습니다.")
    return res.data[0]


def _enrich_version(sb, version: Dict[str, Any]) -> Dict[str, Any]:
    """Version row에 document 메타데이터 attach."""
    doc_id = version.get("document_id")
    if not doc_id:
        return version
    doc_res = (
        sb.table("documents")
        .select("id, file_name, mime_type, file_size, uploaded_at")
        .eq("id", doc_id)
        .limit(1)
        .execute()
    )
    version = dict(version)
    version["document"] = doc_res.data[0] if doc_res.data else None
    return version


# ─── Public API ──────────────────────────────────────────────────────────────

def list_versions(
    sb,
    current_user: Dict[str, Any],
    factory_id: str,
    product_id: str,
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    _require_factory_scope(sb, current_user, factory_id)
    _assert_product_belongs_to_factory(sb, factory_id, product_id)

    query = (
        sb.table("customer_msds_versions")
        .select("*")
        .eq("chemical_product_id", product_id)
        .eq("factory_id", factory_id)
    )
    if status:
        query = query.eq("record_status", status.upper())

    query = query.order("version_no", desc=True)
    res = query.execute()
    all_rows = res.data or []
    total = len(all_rows)

    rows = all_rows[offset:] if offset else all_rows
    rows = rows[:limit] if limit else rows

    return ([_enrich_version(sb, r) for r in rows], total)


def get_version(
    sb,
    current_user: Dict[str, Any],
    factory_id: str,
    product_id: str,
    version_id: str,
) -> Dict[str, Any]:
    _require_factory_scope(sb, current_user, factory_id)
    _assert_product_belongs_to_factory(sb, factory_id, product_id)
    version = _get_version_or_404(sb, factory_id, product_id, version_id)
    return _enrich_version(sb, version)


def get_current_version(
    sb,
    current_user: Dict[str, Any],
    factory_id: str,
    product_id: str,
) -> Dict[str, Any]:
    _require_factory_scope(sb, current_user, factory_id)
    _assert_product_belongs_to_factory(sb, factory_id, product_id)

    res = (
        sb.table("customer_msds_versions")
        .select("*")
        .eq("chemical_product_id", product_id)
        .eq("factory_id", factory_id)
        .eq("is_current", True)
        .eq("record_status", "ACTIVE")
        .limit(1)
        .execute()
    )
    if not res.data:
        raise MsdsProductError(404, "CURRENT_MSDS_NOT_FOUND", "현행 MSDS Version이 없습니다.")
    return _enrich_version(sb, res.data[0])


def make_current(
    sb,
    current_user: Dict[str, Any],
    factory_id: str,
    product_id: str,
    version_id: str,
) -> Dict[str, Any]:
    _require_factory_scope(sb, current_user, factory_id)
    _assert_product_belongs_to_factory(sb, factory_id, product_id)
    _get_version_or_404(sb, factory_id, product_id, version_id)

    result = _rpc_promote(sb, factory_id, product_id, version_id)
    rpc_status = result.get("status")

    if rpc_status == "PRODUCT_NOT_FOUND":
        raise MsdsProductError(404, "PRODUCT_NOT_FOUND", "제품을 찾을 수 없습니다.")
    if rpc_status == "VERSION_NOT_FOUND":
        raise MsdsProductError(404, "MSDS_VERSION_NOT_FOUND", "MSDS Version을 찾을 수 없습니다.")
    if rpc_status == "VERSION_VOID":
        raise MsdsProductError(409, "MSDS_VERSION_VOID", "VOID 처리된 Version은 Current로 변경할 수 없습니다.")
    if rpc_status not in ("PROMOTED", "ALREADY_CURRENT"):
        raise MsdsProductError(500, "PROMOTE_FAILED", f"Current 전환 실패: {rpc_status}")

    return _get_version_or_404(sb, factory_id, product_id, version_id)


def void_version(
    sb,
    current_user: Dict[str, Any],
    factory_id: str,
    product_id: str,
    version_id: str,
    void_reason: str,
) -> Dict[str, Any]:
    _require_factory_scope(sb, current_user, factory_id)
    _assert_product_belongs_to_factory(sb, factory_id, product_id)

    if not void_reason or not void_reason.strip():
        raise MsdsProductError(422, "VOID_REASON_REQUIRED", "void_reason은 필수입니다.")

    _get_version_or_404(sb, factory_id, product_id, version_id)

    result = _rpc_void(sb, factory_id, product_id, version_id, void_reason.strip())
    rpc_status = result.get("status")

    if rpc_status == "PRODUCT_NOT_FOUND":
        raise MsdsProductError(404, "PRODUCT_NOT_FOUND", "제품을 찾을 수 없습니다.")
    if rpc_status == "VERSION_NOT_FOUND":
        raise MsdsProductError(404, "MSDS_VERSION_NOT_FOUND", "MSDS Version을 찾을 수 없습니다.")
    if rpc_status not in ("VOIDED", "ALREADY_VOID"):
        raise MsdsProductError(500, "VOID_FAILED", f"VOID 처리 실패: {rpc_status}")

    return _get_version_or_404(sb, factory_id, product_id, version_id)


async def get_download_url(
    sb,
    current_user: Dict[str, Any],
    factory_id: str,
    product_id: str,
    version_id: str,
) -> Dict[str, Any]:
    from services.document_svc import get_document, get_signed_url as _get_signed_url

    _require_factory_scope(sb, current_user, factory_id)
    _assert_product_belongs_to_factory(sb, factory_id, product_id)
    version = _get_version_or_404(sb, factory_id, product_id, version_id)

    doc_id = version.get("document_id")
    doc = await get_document(doc_id)
    if not doc:
        raise MsdsProductError(404, "DOCUMENT_NOT_FOUND", "원본 문서를 찾을 수 없습니다.")

    url = await _get_signed_url(doc_id)
    if not url:
        raise MsdsProductError(500, "SIGNED_URL_FAILED", "다운로드 URL 생성에 실패했습니다.")

    return {
        "url": url,
        "expires_in": 3600,
        "file_name": doc.get("file_name"),
        "mime_type": doc.get("mime_type"),
        "file_size": doc.get("file_size"),
    }


async def create_version(
    sb,
    current_user: Dict[str, Any],
    factory_id: str,
    product_id: str,
    file_bytes: bytes,
    file_name: str,
    mime_type: str,
    source_revision_date: Optional[str] = None,
    source_revision_no: Optional[str] = None,
    supplier_name: Optional[str] = None,
    created_source: str = "PDF",
    _upload_fn: Optional[Callable] = None,
    _cleanup_storage_fn: Optional[Callable] = None,
    _cleanup_document_fn: Optional[Callable] = None,
) -> Tuple[Dict[str, Any], str]:
    """PDF 업로드 → document 생성 → Version 등록. (version_row, rpc_status) 반환."""
    # 1. Auth
    _require_factory_scope(sb, current_user, factory_id)
    product = _assert_product_belongs_to_factory(sb, factory_id, product_id)

    # 2. PDF validation
    validate_pdf(file_bytes, file_name, mime_type)

    # 3. SHA256
    sha256 = calculate_sha256(file_bytes)

    # 4. Duplicate pre-check (race-safe: DB RPC re-checks with lock)
    existing = _find_existing_sha(sb, product_id, sha256)
    if existing:
        return (_enrich_version(sb, existing), "NO_CHANGE")

    # 5. Derive company_id from factory
    company_id = _get_factory_company_id(sb, factory_id)

    # 6. Upload storage + create document
    upload_fn = _upload_fn or _default_upload
    storage_path = None
    doc_id = None

    doc = await upload_fn(
        file_bytes=file_bytes,
        file_name=file_name,
        mime_type=mime_type,
        company_id=company_id,
        category="msds",
        factory_id=factory_id,
        linked_table="chemical_products",
        linked_id=product_id,
        uploaded_by=current_user.get("id"),
    )
    doc_id = doc.get("id") if doc else None
    storage_path = doc.get("storage_path") if doc else None

    if not doc_id:
        if storage_path:
            await _compensate(sb, None, storage_path, _cleanup_storage_fn, _cleanup_document_fn)
        raise MsdsProductError(500, "DOCUMENT_CREATE_FAILED", "문서 생성에 실패했습니다.")

    # 7. Service-level document contract pre-validation
    try:
        _require_valid_msds_document(sb, doc_id, factory_id, product_id)
    except MsdsProductError:
        # Cleanup temp assets before re-raising
        await _compensate(sb, doc_id, storage_path, _cleanup_storage_fn, _cleanup_document_fn)
        raise

    # 8. Register version via RPC
    try:
        result = _rpc_register(
            sb,
            factory_id=factory_id,
            product_id=product_id,
            document_id=doc_id,
            sha256=sha256,
            source_revision_date=source_revision_date,
            source_revision_no=source_revision_no,
            supplier_name=supplier_name,
            created_source=created_source,
            created_by=current_user.get("id"),
        )
    except Exception as e:
        await _compensate(sb, doc_id, storage_path, _cleanup_storage_fn, _cleanup_document_fn)
        raise MsdsProductError(500, "VERSION_REGISTER_FAILED", "Version 등록에 실패했습니다.") from e

    rpc_status = result.get("status")

    if rpc_status == "PRODUCT_NOT_FOUND":
        await _compensate(sb, doc_id, storage_path, _cleanup_storage_fn, _cleanup_document_fn)
        raise MsdsProductError(404, "PRODUCT_NOT_FOUND", "제품을 찾을 수 없습니다.")

    if rpc_status in (
        "DOCUMENT_NOT_FOUND", "DOCUMENT_INACTIVE", "DOCUMENT_INVALID_CATEGORY",
        "DOCUMENT_FACTORY_MISMATCH", "DOCUMENT_LINKED_TABLE_MISMATCH",
        "DOCUMENT_LINKED_ID_MISMATCH",
    ):
        await _compensate(sb, doc_id, storage_path, _cleanup_storage_fn, _cleanup_document_fn)
        raise MsdsProductError(422, rpc_status, f"문서 계약 위반: {rpc_status}")

    if rpc_status == "DOCUMENT_ALREADY_USED":
        await _compensate(sb, doc_id, storage_path, _cleanup_storage_fn, _cleanup_document_fn)
        raise MsdsProductError(409, "DOCUMENT_ALREADY_USED", "이미 다른 Version에 사용된 문서입니다.")

    if rpc_status == "NO_CHANGE":
        # Concurrent duplicate race: cleanup temp assets, return existing
        await _compensate(sb, doc_id, storage_path, _cleanup_storage_fn, _cleanup_document_fn)
        existing_id = result.get("version_id")
        if existing_id:
            row = (
                sb.table("customer_msds_versions")
                .select("*")
                .eq("id", existing_id)
                .limit(1)
                .execute()
            )
            if row.data:
                return (_enrich_version(sb, row.data[0]), "NO_CHANGE")
        raise MsdsProductError(409, "DUPLICATE_MSDS_FILE", "동일한 파일이 이미 등록되어 있습니다.")

    if rpc_status != "NEW_VERSION":
        await _compensate(sb, doc_id, storage_path, _cleanup_storage_fn, _cleanup_document_fn)
        raise MsdsProductError(500, "VERSION_REGISTER_FAILED", f"예상치 못한 RPC 결과: {rpc_status}")

    # Evidence Lock acquired — read back full version row
    version_id = result.get("version_id")
    version_res = (
        sb.table("customer_msds_versions")
        .select("*")
        .eq("id", version_id)
        .limit(1)
        .execute()
    )
    if not version_res.data:
        raise MsdsProductError(500, "VERSION_REGISTER_FAILED", "Version 등록 후 조회 실패.")

    return (_enrich_version(sb, version_res.data[0]), "NEW_VERSION")


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _assert_product_belongs_to_factory(
    sb, factory_id: str, product_id: str
) -> Dict[str, Any]:
    res = (
        sb.table("chemical_products")
        .select("*")
        .eq("id", product_id)
        .eq("factory_id", factory_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise MsdsProductError(404, "PRODUCT_NOT_FOUND", "제품을 찾을 수 없습니다.")
    return res.data[0]


def _get_factory_company_id(sb, factory_id: str) -> str:
    res = (
        sb.table("factories")
        .select("company_id")
        .eq("id", factory_id)
        .limit(1)
        .execute()
    )
    if not res.data or not res.data[0].get("company_id"):
        raise MsdsProductError(500, "FACTORY_COMPANY_MISSING", "시설의 회사 정보를 찾을 수 없습니다.")
    return res.data[0]["company_id"]


async def _default_upload(**kwargs) -> Dict[str, Any]:
    """기본 document upload — document_svc.upload_document 위임."""
    return await upload_document(**kwargs)


async def _compensate(
    sb,
    doc_id: Optional[str],
    storage_path: Optional[str],
    cleanup_storage_fn: Optional[Callable],
    cleanup_document_fn: Optional[Callable],
) -> None:
    """Version 등록 실패 시 임시 document/storage 정리 (best-effort)."""
    # Storage
    if storage_path:
        try:
            fn = cleanup_storage_fn or _default_cleanup_storage
            await fn(storage_path)
        except Exception:
            pass

    # Document (only if not yet Evidence-Locked)
    if doc_id:
        try:
            fn = cleanup_document_fn or _default_cleanup_document
            await fn(doc_id)
        except Exception:
            pass


async def _default_cleanup_storage(storage_path: str) -> None:
    from db.supabase_client import get_supabase
    sb = get_supabase()
    try:
        sb.storage.from_(BUCKET).remove([storage_path])
    except Exception:
        pass


async def _default_cleanup_document(doc_id: str) -> None:
    from services.document_svc import soft_delete
    try:
        await soft_delete(doc_id)
    except Exception:
        pass


# ─── Document Lock Guard ──────────────────────────────────────────────────────

def is_msds_evidence_document(sb, doc_id: str) -> bool:
    """documents.id가 customer_msds_versions에 의해 참조되면 True (Evidence Lock)."""
    res = (
        sb.table("customer_msds_versions")
        .select("id")
        .eq("document_id", doc_id)
        .limit(1)
        .execute()
    )
    return bool(res.data)
