"""TAI Safe 통합 문서 서비스 v1.0.0"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from db.supabase_client import get_supabase
from services.time import now_kst, serialize_business_datetime

RETENTION_DEFAULTS = {
    "inspection": 3,
    "certificate": None,
    "education": 3,
    "safety_plan": 5,
    "risk_assessment": 3,
    "msds": None,
    "corrective": 3,
    "report": 3,
    "contract": 5,
    "tbm": 3,
    "equipment": None,
    "facility_drawing": None,
    "general": 1,
}

BUCKET = "company-docs"


def _build_path(company_id: str, category: str, ext: str) -> str:
    now = now_kst()
    file_uuid = str(uuid.uuid4())
    suffix = f".{ext}" if ext else ""
    return f"{company_id}/{category}/{now.strftime('%Y-%m')}/{file_uuid}{suffix}"


def _get_ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _build_retention_until(years: Optional[int]) -> Optional[str]:
    if not years:
        return None
    now = now_kst()
    return date(now.year + years, now.month, now.day).isoformat()


async def upload_document(
    file_bytes: bytes,
    file_name: str,
    mime_type: str,
    company_id: str,
    category: str = "general",
    source: str = "USER_UPLOAD",
    factory_id: Optional[str] = None,
    linked_table: Optional[str] = None,
    linked_id: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    tags: Optional[List[str]] = None,
    uploaded_by: Optional[str] = None,
    retention_years: Optional[int] = None,
    generated_by: Optional[str] = None,
    generation_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    sb = get_supabase()
    ext = _get_ext(file_name or "")
    storage_path = _build_path(company_id, category, ext)

    sb.storage.from_(BUCKET).upload(
        path=storage_path,
        file=file_bytes,
        file_options={"content-type": mime_type},
    )

    if retention_years is None:
        retention_years = RETENTION_DEFAULTS.get(category)
    retention_until = _build_retention_until(retention_years)

    record: Dict[str, Any] = {
        "company_id": company_id,
        "factory_id": factory_id,
        "category": category,
        "source": source,
        "file_name": file_name,
        "storage_path": storage_path,
        "bucket_id": BUCKET,
        "file_size": len(file_bytes),
        "mime_type": mime_type,
        "file_ext": ext,
        "linked_table": linked_table,
        "linked_id": linked_id,
        "title": title or file_name,
        "description": description,
        "tags": tags or [],
        "is_photo": (mime_type or "").startswith("image/"),
        "uploaded_by": uploaded_by,
        "generated_by": generated_by,
        "generation_params": generation_params,
        "retention_years": retention_years,
        "retention_until": retention_until,
    }
    record = {k: v for k, v in record.items() if v is not None}

    result = sb.table("documents").insert(record).execute()
    return result.data[0] if result.data else record


async def register_generated(
    file_bytes: bytes,
    file_name: str,
    mime_type: str,
    company_id: str,
    category: str,
    generated_by: str,
    generation_params: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """자동생성 문서 등록 (PDF 등)."""
    return await upload_document(
        file_bytes=file_bytes,
        file_name=file_name,
        mime_type=mime_type,
        company_id=company_id,
        category=category,
        source="AUTO_GENERATED",
        generated_by=generated_by,
        generation_params=generation_params,
        **kwargs,
    )


async def list_documents(
    company_id: str,
    category: Optional[str] = None,
    factory_id: Optional[str] = None,
    linked_table: Optional[str] = None,
    linked_id: Optional[str] = None,
    search: Optional[str] = None,
    tags: Optional[List[str]] = None,
    page: int = 1,
    per_page: int = 20,
) -> Dict[str, Any]:
    sb = get_supabase()
    query = sb.table("documents").select("*", count="exact")
    query = query.eq("company_id", company_id).eq("is_active", True).is_("deleted_at", "null")

    if category:
        query = query.eq("category", category)
    if factory_id:
        query = query.eq("factory_id", factory_id)
    if linked_table and linked_id:
        query = query.eq("linked_table", linked_table).eq("linked_id", linked_id)
    if search:
        query = query.or_(f"title.ilike.%{search}%,file_name.ilike.%{search}%,description.ilike.%{search}%")
    if tags:
        query = query.contains("tags", tags)

    offset = (page - 1) * per_page
    query = query.order("uploaded_at", desc=True).range(offset, offset + per_page - 1)
    result = query.execute()
    total = result.count or 0

    return {
        "items": result.data or [],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
    }


async def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
    sb = get_supabase()
    result = sb.table("documents").select("*").eq("id", doc_id).limit(1).execute()
    if result.data:
        return result.data[0]
    return None


async def get_signed_url(doc_id: str, expires_in: int = 3600) -> Optional[str]:
    sb = get_supabase()
    doc = await get_document(doc_id)
    if not doc:
        return None
    result = sb.storage.from_(doc["bucket_id"]).create_signed_url(doc["storage_path"], expires_in)
    return result.get("signedURL") or result.get("signed_url")


async def get_attachments(linked_table: str, linked_id: str) -> List[Dict[str, Any]]:
    sb = get_supabase()
    result = (
        sb.table("documents")
        .select("*")
        .eq("linked_table", linked_table)
        .eq("linked_id", linked_id)
        .eq("is_active", True)
        .is_("deleted_at", "null")
        .order("uploaded_at", desc=True)
        .execute()
    )
    return result.data or []


async def update_document(doc_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sb = get_supabase()
    allowed = {"title", "description", "tags", "category"}
    payload = {k: v for k, v in updates.items() if k in allowed}
    if not payload:
        return None
    result = sb.table("documents").update(payload).eq("id", doc_id).execute()
    if result.data:
        return result.data[0]
    return None


async def soft_delete(doc_id: str) -> bool:
    sb = get_supabase()
    result = sb.table("documents").update(
        {"deleted_at": serialize_business_datetime(now_kst()), "is_active": False}
    ).eq("id", doc_id).execute()
    return bool(result.data)


async def get_stats(company_id: str) -> List[Dict[str, Any]]:
    sb = get_supabase()
    result = sb.table("v_document_stats").select("*").eq("company_id", company_id).execute()
    return result.data or []


async def get_expiring(company_id: str, days: int = 90) -> List[Dict[str, Any]]:
    sb = get_supabase()
    result = (
        sb.table("v_documents_expiring")
        .select("*")
        .eq("company_id", company_id)
        .lte("days_remaining", days)
        .execute()
    )
    return result.data or []
