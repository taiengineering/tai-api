"""Public Safety Search router — WO-TAI-SHARED-SEARCH-F3 §32-§35, §40-§41.

Routes:
    GET /public/safety-search       — Shared Search (OpenSearch backend)
    GET /public/safety-search/kosha — External KOSHA Smart Search (unchanged §42)

OpenSearch config missing → HTTP 503 SHARED_SEARCH_UNAVAILABLE (§41).
No silent fallback to empty MemorySearchReader in production.
Legal applicability not produced here (§7).
CHEM PUBLIC exposure follows KOSHA_MSDS_PUBLIC_MODE env var (§28).
"""
from __future__ import annotations

import os
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from services import safe_help_svc
from services.kosha_safety_materials.display import load_public_material

from services.kosha_smart_search import (
    MAX_PAGE_SIZE,
    SmartSearchQueryError,
    search_kosha_public,
)
from services.shared_search.opensearch_client import (
    ENV_URL,
    OpenSearchUnavailable,
    get_client,
)

router = APIRouter(prefix="/public/safety-search", tags=["Public safety search"])


# ---------------------------------------------------------------------------
# Object-type allowlist + type→object_type map (§33)
# ---------------------------------------------------------------------------
_PUBLIC_OBJECT_TYPES: list[str] = [
    "GUIDE",
    "SAFETY_MATERIAL",
    "CSI_ACCIDENT",
    "CHEM",
    "KNOWLEDGE",
    "PRECEDENT",
    "LEGAL",
]

_TYPE_MAP: dict[str, list[str]] = {
    "guide":     ["GUIDE"],
    "material":  ["SAFETY_MATERIAL"],
    "accident":  ["CSI_ACCIDENT"],
    "chem":      ["CHEM"],
    "knowledge": ["KNOWLEDGE"],
    "precedent": ["PRECEDENT"],
    "law":       ["LEGAL"],
    "legal":     ["LEGAL"],
}


# ---------------------------------------------------------------------------
# GET /public/safety-search — Shared Search (F3 OpenSearch backend)
# ---------------------------------------------------------------------------

@router.get("")
async def public_shared_search(
    q: str = Query(..., min_length=1, description="검색어"),
    type: Optional[str] = Query(
        None,
        description="object_type 필터. 허용값: " + ", ".join(_TYPE_MAP.keys()),
    ),
    within: Optional[str] = Query(None, description="결과 내 검색어 (optional narrowing)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    """Shared Search public endpoint (OpenSearch + Nori).

    - Blank q → 422 (§35).
    - OpenSearch not configured → 503 SHARED_SEARCH_UNAVAILABLE (§41).
    - CHEM excluded unless KOSHA_MSDS_PUBLIC_MODE active (§28).
    - Legal applicability: 0 fields produced (§7).
    """
    if not q or not q.strip():
        raise HTTPException(status_code=422, detail="query 'q' is required")

    within_query = within.strip() if within and within.strip() else None

    # Build object_type filter (§33)
    object_types: list[str]
    if type:
        mapped = _TYPE_MAP.get(type.lower())
        if mapped is None:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown type '{type}'. Allowed: {list(_TYPE_MAP.keys())}",
            )
        object_types = mapped
    else:
        object_types = list(_PUBLIC_OBJECT_TYPES)

    # CHEM public mode check (§28)
    chem_mode = (os.environ.get("KOSHA_MSDS_PUBLIC_MODE") or "off").strip().lower()
    if "CHEM" in object_types and chem_mode not in ("seo_preview", "full"):
        object_types = [ot for ot in object_types if ot != "CHEM"]

    # Build OpenSearch reader — 503 if not configured (§41)
    try:
        client = get_client()
    except OpenSearchUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SHARED_SEARCH_UNAVAILABLE",
                "message": str(exc),
                "hint": f"Set {ENV_URL} environment variable.",
            },
        ) from exc

    from services.shared_search.opensearch_reader import OpenSearchSearchReader
    from services.shared_search.retrieval import SharedRetrievalEngine

    reader = OpenSearchSearchReader(client)
    engine = SharedRetrievalEngine(reader)

    try:
        response = engine.search(
            q,
            visibility_scopes=["PUBLIC"],
            object_types=object_types,
            page=page,
            page_size=page_size,
            within_query=within_query,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OpenSearchUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "SHARED_SEARCH_UNAVAILABLE", "message": str(exc)},
        ) from exc

    return response.to_dict()


# ---------------------------------------------------------------------------
# GET /public/safety-search/kosha — External KOSHA Smart Search (§42)
# Unchanged from pre-F3. External provider. Not in Shared Search index.
# ---------------------------------------------------------------------------

@router.get("/kosha")
async def public_kosha_smart_search(
    q: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE),
):
    """External KOSHA Smart Search — retained as-is (WO §42)."""
    try:
        return await search_kosha_public(q=q, page=page, page_size=page_size)
    except SmartSearchQueryError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc


# ---------------------------------------------------------------------------
# GET /public/safety-search/knowledge/{canonical_id} — KNOWLEDGE detail
# Identity: safe_help_content.doc_id. Not slug. Status must be PUBLISHED.
# ---------------------------------------------------------------------------

def _build_knowledge_detail(canonical_id: str, row: dict) -> dict:
    answer_short = row.get("answer_short") or None
    body = row.get("body") or None

    if answer_short:
        summary = answer_short
    elif body:
        text = re.sub(r"<[^>]+>", " ", body)
        text = re.sub(r"\s+", " ", text).strip()
        summary = text[:200] if text else None
    else:
        summary = None

    return {
        "object_type": "KNOWLEDGE",
        "canonical_id": canonical_id,
        "title": row.get("title"),
        "summary": summary,
        "detail": {
            "doc_id": row.get("doc_id"),
            "type": row.get("type"),
            "slug": row.get("slug"),
            "question": row.get("question"),
            "answer_short": answer_short,
            "body": body,
            "menu_group": row.get("menu_group"),
            "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
        },
    }


@router.get("/knowledge/{canonical_id}")
async def public_knowledge_detail(canonical_id: str):
    """KNOWLEDGE canonical detail for Public Search results.

    Identity: safe_help_content.doc_id (not slug).
    404 for non-PUBLISHED or missing doc_id.
    """
    row = safe_help_svc.get_published_by_doc_id(canonical_id)
    if row is None:
        raise HTTPException(status_code=404, detail="KNOWLEDGE_NOT_FOUND")
    return _build_knowledge_detail(canonical_id, row)


# ---------------------------------------------------------------------------
# GET /public/safety-search/material/{canonical_id} — SAFETY_MATERIAL detail
# Eligibility: latest COMPLETED snapshot member + no active storage hold.
# ---------------------------------------------------------------------------

_mat_store = None
_mat_signer = None


def _mat_store_dep():
    global _mat_store
    if _mat_store is None:
        from services.kosha_safety_materials.display import SupabaseDisplayStore
        _mat_store = SupabaseDisplayStore()
    return _mat_store


def _mat_signer_dep():
    global _mat_signer
    if _mat_signer is None:
        from services.kosha_safety_materials.storage.r2_store import (
            credentials_from_env,
            make_s3_client,
        )
        from services.kosha_safety_materials.storage.signed_url import R2GetSigner
        creds = credentials_from_env()
        _mat_signer = R2GetSigner(make_s3_client(creds))
    return _mat_signer


def _build_material_search_detail(canonical_id: str, display: dict) -> dict:
    return {
        "object_type": "SAFETY_MATERIAL",
        "canonical_id": canonical_id,
        "title": display.get("title") or "",
        "summary": display.get("description"),
        "detail": display,
    }


@router.get("/material/{canonical_id}")
async def public_material_detail(
    canonical_id: str,
    store=Depends(_mat_store_dep),
):
    """SAFETY_MATERIAL search detail. Eligibility: snapshot member + no active hold.

    503 if no current snapshot.
    404 if not a snapshot member or has an active storage hold.
    Signer is initialized only after eligibility is confirmed (fail-closed ordering).
    """
    from services.kosha_safety_materials.storage.r2_store import R2Error

    snap = store.latest_completed()
    if not snap or snap.get("status") != "COMPLETED":
        raise HTTPException(status_code=503, detail="CURRENT_SNAPSHOT_UNAVAILABLE")

    if not store.membership_has(snap["id"], canonical_id):
        raise HTTPException(status_code=404, detail="MATERIAL_NOT_FOUND")

    if store.hold_active(canonical_id):
        raise HTTPException(status_code=404, detail="MATERIAL_NOT_FOUND")

    try:
        signer = _mat_signer_dep()
        display = load_public_material(canonical_id, store=store, signer=signer)
    except R2Error as exc:
        if exc.code == "R2_INTEGRATION_BLOCKED":
            raise HTTPException(status_code=503, detail="STORAGE_UNAVAILABLE") from exc
        raise

    if display is None:
        raise HTTPException(status_code=404, detail="MATERIAL_NOT_FOUND")

    if display.get("id") != canonical_id:
        raise HTTPException(status_code=503, detail="MATERIAL_IDENTITY_MISMATCH")

    return _build_material_search_detail(canonical_id, display)
