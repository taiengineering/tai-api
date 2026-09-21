"""Public Safety Search router — WO-TAI-SHARED-SEARCH-F3 §32-§35, §40-§41.

Routes:
    GET /public/safety-search          — Shared Search (OpenSearch backend)
    GET /public/safety-search/sections — Domain-sectioned search (WO-MKT-SEARCH-06R-1)
    GET /public/safety-search/kosha    — External KOSHA Smart Search (unchanged §42)

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
from services.shared_search.production_bindings import get_current_legal_article_by_id

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

# Section order for /sections endpoint (§12 fixed presentation order)
_SECTION_TYPES: list[tuple[str, str]] = [
    ("guide",     "GUIDE"),
    ("material",  "SAFETY_MATERIAL"),
    ("accident",  "CSI_ACCIDENT"),
    ("chem",      "CHEM"),
    ("knowledge", "KNOWLEDGE"),
    ("precedent", "PRECEDENT"),
    ("law",       "LEGAL"),
]


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
# GET /public/safety-search/sections — Domain-sectioned search (WO-MKT-SEARCH-06R-1)
# One independent search per domain. Single client/reader/engine per request.
# KOSHA excluded (external provider). Legal applicability: 0 fields (§7).
# ---------------------------------------------------------------------------

def _search_public_section(
    engine: object,
    q: str,
    object_type: str,
    section_type: str,
    section_size: int,
    within_query: Optional[str],
) -> dict:
    """Execute one domain search and return a section payload.

    Requests section_size+1 items to determine has_more without a
    separate count query. Returns exactly section_size items to callers.
    """
    try:
        resp = engine.search(
            q,
            visibility_scopes=["PUBLIC"],
            object_types=[object_type],
            page=1,
            page_size=section_size + 1,
            within_query=within_query,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OpenSearchUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "SHARED_SEARCH_UNAVAILABLE", "message": str(exc)},
        ) from exc

    raw = resp.items
    has_more = len(raw) > section_size
    items = [r.to_dict() for r in raw[:section_size]]
    return {
        "type":        section_type,
        "object_type": object_type,
        "status":      "ok" if items else "empty",
        "items":       items,
        "page":        1,
        "page_size":   section_size,
        "has_more":    has_more,
    }


@router.get("/sections")
async def public_search_sections(
    q: str = Query(..., min_length=1, description="검색어"),
    within: Optional[str] = Query(None, description="결과 내 검색어 (optional narrowing)"),
    section_size: int = Query(5, ge=1, le=10, description="섹션당 초기 결과 수 (1-10)"),
):
    """Domain-sectioned Public Search.

    Returns 7 internal-domain sections in fixed order (§12):
      guide → GUIDE
      material → SAFETY_MATERIAL
      accident → CSI_ACCIDENT
      chem → CHEM
      knowledge → KNOWLEDGE
      precedent → PRECEDENT
      law → LEGAL

    KOSHA is NOT included (external provider, use /kosha endpoint).
    Each domain is searched independently with the same engine.
    has_more is determined by requesting section_size+1 items (no total count).
    Legal applicability: 0 fields produced (§7).
    CHEM: excluded unless KOSHA_MSDS_PUBLIC_MODE active (§28).
    OpenSearch not configured → 503 SHARED_SEARCH_UNAVAILABLE.
    """
    if not q or not q.strip():
        raise HTTPException(status_code=422, detail="query 'q' is required")

    within_query = within.strip() if within and within.strip() else None

    chem_mode = (os.environ.get("KOSHA_MSDS_PUBLIC_MODE") or "off").strip().lower()
    chem_public = chem_mode in ("seo_preview", "full")

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

    sections = []
    for section_type, object_type in _SECTION_TYPES:
        if object_type == "CHEM" and not chem_public:
            sections.append({
                "type":        section_type,
                "object_type": object_type,
                "status":      "empty",
                "items":       [],
                "page":        1,
                "page_size":   section_size,
                "has_more":    False,
            })
            continue
        sections.append(
            _search_public_section(engine, q, object_type, section_type, section_size, within_query)
        )

    return {
        "query":        q,
        "within":       within_query,
        "section_size": section_size,
        "sections":     sections,
    }


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


# ---------------------------------------------------------------------------
# GET /public/safety-search/legal/{canonical_id} — LEGAL detail
# canonical_id = law_article.id (UUID).
# Eligibility: law_master.is_active AND current_version_id match AND not deleted.
# ---------------------------------------------------------------------------

_legal_supabase = None


def _legal_supabase_dep():
    global _legal_supabase
    if _legal_supabase is None:
        from supabase import create_client
        _legal_supabase = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
    return _legal_supabase


def _build_legal_detail(canonical_id: str, row: dict) -> dict:
    law_name = row.get("law_name") or ""
    article_no = row.get("article_no")
    article_sub_no = row.get("article_sub_no")
    article_title = row.get("article_title")

    if law_name and article_no:
        title_parts = [law_name, f"제{article_no}조"]
        if article_sub_no:
            title_parts[-1] = title_parts[-1] + f"의{article_sub_no}"
        if article_title:
            title_parts.append(f"({article_title})")
        title = " ".join(title_parts)
    else:
        title = article_title or f"law_article/{canonical_id}"

    return {
        "object_type": "LEGAL",
        "canonical_id": canonical_id,
        "title": title,
        "summary": None,
        "detail": {
            "law_article_id": canonical_id,
            "law_name": law_name or None,
            "article_no": article_no,
            "article_sub_no": article_sub_no,
            "article_title": article_title,
            "article_text": row.get("article_text"),
            "enforcement_date": row.get("enforcement_date"),
            "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
        },
    }


@router.get("/legal/{canonical_id}")
async def public_legal_detail(canonical_id: str):
    """LEGAL canonical detail for Public Search results.

    canonical_id = law_article.id (UUID).
    Eligibility: law_master.is_active AND current_version_id match AND not deleted.
    404 for non-eligible or missing.
    503 LEGAL_IDENTITY_MISMATCH if row.id != requested canonical_id.
    503 LEGAL_DETAIL_INCOMPLETE if article_text is absent.
    """
    client = _legal_supabase_dep()
    row = get_current_legal_article_by_id(client, canonical_id)
    if row is None:
        raise HTTPException(status_code=404, detail="LEGAL_NOT_FOUND")

    row_id = str(row.get("id") or "")
    if row_id != canonical_id:
        raise HTTPException(status_code=503, detail="LEGAL_IDENTITY_MISMATCH")

    article_text = row.get("article_text")
    if not article_text or not article_text.strip():
        raise HTTPException(status_code=503, detail="LEGAL_DETAIL_INCOMPLETE")

    return _build_legal_detail(canonical_id, row)
