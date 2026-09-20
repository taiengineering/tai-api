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
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

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
