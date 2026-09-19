"""Public Safety Search router.

WO-TAI-SHARED-SEARCH-F3 §32-§35.

Routes:
    GET /public/safety-search        — Shared Search (F3, §32)
    GET /public/safety-search/kosha  — External KOSHA Smart Search (unchanged, §45)

The Shared Search route wraps `SharedRetrievalEngine` which is backed by
`SupabaseSearchReader` in production and `MemorySearchReader` in tests.

Zero new router files — this existing file is extended, not copied.
Legal authority is never produced here (§29).  CHEM PUBLIC exposure
follows `KOSHA_MSDS_PUBLIC_MODE` env var (enforced by the adapter layer, §28).
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from services.kosha_smart_search import (
    MAX_PAGE_SIZE,
    SmartSearchQueryError,
    search_kosha_public,
)

router = APIRouter(prefix="/public/safety-search", tags=["Public safety search"])


# ---------------------------------------------------------------------------
# /public/safety-search — Shared Search (F3)
# ---------------------------------------------------------------------------

# Public-facing object_type allowlist (§33).
# Callers may further restrict via `type` query param.
_PUBLIC_OBJECT_TYPES = [
    "GUIDE",
    "SAFETY_MATERIAL",
    "CSI_ACCIDENT",
    "CHEM",
    "KNOWLEDGE",
    "PRECEDENT",
    "LEGAL",
]

# Map user-facing `type` strings to internal object_types (§33).
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


def _get_supabase_client():
    """Lazy Supabase client for production. Returns None when env vars absent
    (test environments call the route with a mocked reader instead)."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return None
    from supabase import create_client
    return create_client(url, key)


def _build_reader(client):
    """Build the appropriate reader based on whether the client is available."""
    if client is None:
        # No production client — return empty MemorySearchReader.
        from services.shared_search.retrieval import MemorySearchReader
        return MemorySearchReader([])
    from services.shared_search.retrieval import SupabaseSearchReader
    return SupabaseSearchReader(client)


@router.get("")
async def public_shared_search(
    q: str = Query(..., min_length=1, description="검색어"),
    type: Optional[str] = Query(
        None,
        description="object_type 필터. 허용값: " + ", ".join(_TYPE_MAP.keys()),
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    """Shared Search public endpoint.

    - Returns `422` on blank query (§35).
    - CHEM is included when `KOSHA_MSDS_PUBLIC_MODE` is seo_preview or full (§28).
    - Legal authority (applicability/compliance) is NOT produced here (§29).
    - Results ordered by tier precedence, then source_updated_at DESC (§24).
    """
    if not q or not q.strip():
        raise HTTPException(status_code=422, detail="query 'q' is required")

    # Build object_type restriction from `type` param (§33).
    object_types: list[str] = []
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

    # CHEM public mode check (§28): only include CHEM when mode is active.
    chem_mode = (os.environ.get("KOSHA_MSDS_PUBLIC_MODE") or "off").strip().lower()
    if "CHEM" in object_types and chem_mode not in ("seo_preview", "full"):
        object_types = [ot for ot in object_types if ot != "CHEM"]

    from services.shared_search.retrieval import SharedRetrievalEngine
    client = _get_supabase_client()
    reader = _build_reader(client)
    engine = SharedRetrievalEngine(reader)

    try:
        response = engine.search(
            q,
            visibility_scopes=["PUBLIC"],
            object_types=object_types,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return response.to_dict()


# ---------------------------------------------------------------------------
# /public/safety-search/kosha — External KOSHA Smart Search (§45)
# Unchanged from pre-F3.  Not merged into Shared Search index.
# ---------------------------------------------------------------------------

@router.get("/kosha")
async def public_kosha_smart_search(
    q: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE),
):
    """External KOSHA Smart Search — retained as-is (WO §45)."""
    try:
        return await search_kosha_public(q=q, page=page, page_size=page_size)
    except SmartSearchQueryError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
