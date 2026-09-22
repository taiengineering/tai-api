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


# ---------------------------------------------------------------------------
# GET /public/safety-search/sitemap/legal-articles — sitemap list
# Returns [{id, updated_at}] for current-eligible law_articles (paginated).
# Used by tai-www worker to generate /sitemap_legal_articles.xml.
# No auth. Stable pagination via id ORDER.
# ---------------------------------------------------------------------------

@router.get("/sitemap/legal-articles")
async def public_legal_sitemap_articles(
    after_id: str = "",
    limit: int = Query(default=1000, le=2000),
):
    """Cursor-paginated [{id, updated_at}] for sitemap generation.

    Filter: active law_master version match + is_deleted_in_version=False +
    article_text >= 50 chars (thin content excluded per WO spec).
    Cursor: after_id (UUID exclusive lower bound, stable UUID sort).
    Returns plain list; has_more inferred from len == limit.
    """
    client = _legal_supabase_dep()

    masters_res = client.table("law_master").select("current_version_id").eq("is_active", True).execute()
    version_ids = sorted(set(
        r["current_version_id"] for r in masters_res.data if r.get("current_version_id")
    ))
    if not version_ids:
        return []

    collected: list[dict] = []
    cursor = after_id
    CHUNK = 400
    FETCH = min(limit * 2, 4000)  # Overfetch: ~17% thin rate, 2× is sufficient
    MAX_ITER = 20

    for _ in range(MAX_ITER):
        if len(collected) >= limit:
            break

        if len(version_ids) <= CHUNK:
            q = (
                client.table("law_article")
                .select("id,updated_at,article_text")
                .in_("law_version_id", version_ids)
                .eq("is_deleted_in_version", False)
                .filter("article_text", "not.is", "null")
                .order("id")
                .range(0, FETCH - 1)
            )
            if cursor:
                q = q.gt("id", cursor)
            batch = q.execute().data
        else:
            all_chunk: list[dict] = []
            for i in range(0, len(version_ids), CHUNK):
                part = version_ids[i:i + CHUNK]
                q = (
                    client.table("law_article")
                    .select("id,updated_at,article_text")
                    .in_("law_version_id", part)
                    .eq("is_deleted_in_version", False)
                    .filter("article_text", "not.is", "null")
                    .order("id")
                    .range(0, FETCH - 1)
                )
                if cursor:
                    q = q.gt("id", cursor)
                all_chunk.extend(q.execute().data)
            all_chunk.sort(key=lambda r: r["id"])
            seen: set[str] = set()
            batch = []
            for r in all_chunk:
                if r["id"] not in seen:
                    seen.add(r["id"])
                    batch.append(r)
                    if len(batch) >= FETCH:
                        break

        if not batch:
            break

        for r in batch:
            if len(r.get("article_text") or "") >= 50:
                collected.append({"id": r["id"], "updated_at": r.get("updated_at")})

        if len(batch) < FETCH:
            break  # exhausted

        cursor = batch[-1]["id"]

    return collected[:limit]


# ---------------------------------------------------------------------------
# GET /public/safety-search/hub-candidates — Hub keyword aggregation
# Source: keyword_central_extracted (taeng Supabase).
# WO-SEO-HUB-FROM-OPENSEARCH option (b): OpenSearch keywords field is
# analyzed text (Nori), not aggregatable via terms agg. This endpoint
# aggregates from the existing keyword extraction table instead.
# Law articles excluded (separate system, no page_type in this table).
# ---------------------------------------------------------------------------

@router.get("/hub-candidates")
async def public_hub_candidates(
    min_domain_span: int = Query(default=2, ge=1, le=10),
    min_docs: int = Query(default=5, ge=1, le=10000),
    limit: int = Query(default=200, ge=1, le=500),
):
    """Aggregate keyword_central_extracted → hub candidate list.

    Returns keywords that appear across multiple content domains,
    sorted by domain_span desc, total_docs desc.
    Used for owner curation of ~100 static safety hub keywords.
    """
    from collections import defaultdict
    from db.supabase_client import get_supabase

    sb = get_supabase()
    rows = (
        sb.table("keyword_central_extracted")
        .select("page_type,central_keyword")
        .eq("relevance", "relevant")
        .not_.is_("central_keyword", "null")
        .execute()
    ).data or []

    kw_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        kw = (r.get("central_keyword") or "").strip()
        pt = r.get("page_type") or ""
        if kw and pt:
            kw_counts[kw][pt] += 1

    result = []
    for kw, domain_counts in kw_counts.items():
        total_docs = sum(domain_counts.values())
        domain_span = len(domain_counts)
        if total_docs >= min_docs and domain_span >= min_domain_span:
            result.append({
                "keyword": kw,
                "total_docs": total_docs,
                "domain_span": domain_span,
                "domains": sorted(domain_counts.keys()),
                "per_domain_counts": dict(domain_counts),
            })

    result.sort(key=lambda x: (-x["domain_span"], -x["total_docs"]))
    return result[:limit]


# ---------------------------------------------------------------------------
# GET /public/safety-search/hub/equipment — Equipment hub list (DB-backed)
# WO-SEO-HUB-EXPAND Part A. Source SoT: csi_accident_snapshot_items.object_minor.
# Blocklist (일반어·비검색어) and label normalization applied.
# ---------------------------------------------------------------------------

_EQUIPMENT_BLOCKLIST: frozenset = frozenset({
    "기타", "자재", "공구류", "건물", "질병", "차량", "지반", "지지대", "벽체",
    "핀", "비산물", "부석", "건설폐기물", "지하매설물", "불명", "해당없음",
    "기타장비", "없음",
})

_EQUIPMENT_NORMALIZATION: dict[str, str] = {
    "기중기(이동식크레인 등)": "이동식크레인",
    "고소작업차(고소작업대 등)": "고소작업대",
    "특수거푸집(갱폼 등)": "갱폼",
    "항타 및 항발기": "항타기",
    "굴착기(포크레인 등)": "굴착기",
    "기중기": "이동식크레인",
    "흙막이(가시설)": "흙막이가시설",
    "시스템 동바리": "시스템동바리",
    "파이프 서포트": "파이프서포트",
    "콘크리트 펌프카": "콘크리트펌프",
    "이동식 크레인": "이동식크레인",
    "타워 크레인": "타워크레인",
}


@router.get("/hub/equipment")
async def public_hub_equipment_list():
    """DB-backed equipment hub list from CSI object_minor.

    Queries csi_accident_snapshot_items.object_minor with pagination,
    applies blocklist and normalization, returns sorted [{value, display_name}].
    """
    from db.supabase_client import get_supabase

    sb = get_supabase()
    _FETCH = 1000
    offset = 0
    seen_raw: set[str] = set()
    normalized_set: set[str] = set()

    while True:
        result = (
            sb.table("csi_accident_snapshot_items")
            .select("object_minor")
            .not_.is_("object_minor", "null")
            .range(offset, offset + _FETCH - 1)
            .execute()
        )
        batch = result.data or []
        if not batch:
            break

        for r in batch:
            raw = (r.get("object_minor") or "").strip()
            if not raw or raw in seen_raw:
                continue
            seen_raw.add(raw)
            normalized = _EQUIPMENT_NORMALIZATION.get(raw, raw)
            if normalized and normalized not in _EQUIPMENT_BLOCKLIST:
                normalized_set.add(normalized)

        if len(batch) < _FETCH:
            break
        offset += _FETCH

    return sorted(
        [{"value": v, "display_name": v} for v in normalized_set],
        key=lambda x: x["value"],
    )


# ---------------------------------------------------------------------------
# GET /public/safety-search/hub/accident — Accident type hub list
# WO-SEO-HUB-EXPAND Part B. Source SoT: CSI accident_type taxonomy (hardcoded).
# Standard Korean construction safety accident type classification.
# ---------------------------------------------------------------------------

_ACCIDENT_TYPE_HUBS: list[dict] = [
    {"value": "물체에 맞음",   "display_name": "물체에 맞음"},
    {"value": "끼임",          "display_name": "끼임"},
    {"value": "넘어짐",        "display_name": "넘어짐"},
    {"value": "부딪힘",        "display_name": "부딪힘"},
    {"value": "떨어짐",        "display_name": "떨어짐"},
    {"value": "절단·베임",     "display_name": "절단·베임"},
    {"value": "깔림·뒤집힘",   "display_name": "깔림·뒤집힘"},
    {"value": "찔림",          "display_name": "찔림"},
    {"value": "감전",          "display_name": "감전"},
    {"value": "화재",          "display_name": "화재"},
    {"value": "폭발",          "display_name": "폭발"},
    {"value": "질식",          "display_name": "질식"},
    {"value": "산소결핍",      "display_name": "산소결핍"},
]


@router.get("/hub/accident")
async def public_hub_accident_type_list():
    """Curated accident type hub list from CSI taxonomy.

    Returns [{value, display_name}] for all 13 active accident type hubs.
    """
    return _ACCIDENT_TYPE_HUBS


# ---------------------------------------------------------------------------
# GET /public/safety-search/hub/task — Work process hub list (DB-backed)
# WO-SEO-HUB-TASK. Source SoT: csi_accident_snapshot_items.work_process.
# Blocklist and label normalization applied. ~30 hub values expected.
# ---------------------------------------------------------------------------

_TASK_BLOCKLIST: frozenset = frozenset({
    "기타", "이동", "정리작업", "준비작업", "확인 및 점검작업",
    "물뿌리기 작업", "반출작업",
})

_TASK_NORMALIZATION: dict[str, str] = {
    "상차 및 하역작업": "하역작업",
    "보수 및 교체작업": "보수작업",
    "부설 및 다짐작업": "다짐작업",
    "장약 및 발파작업": "발파작업",
    "항타 및 항발작업": "항타작업",
    "형틀 및 목공": "형틀목공",
}


@router.get("/hub/task")
async def public_hub_task_list():
    """DB-backed work process hub list from CSI work_process.

    Queries csi_accident_snapshot_items.work_process with pagination,
    applies blocklist and normalization, returns sorted [{value, display_name}].
    """
    from db.supabase_client import get_supabase

    sb = get_supabase()
    _FETCH = 1000
    offset = 0
    seen_raw: set[str] = set()
    normalized_set: set[str] = set()

    while True:
        result = (
            sb.table("csi_accident_snapshot_items")
            .select("work_process")
            .not_.is_("work_process", "null")
            .range(offset, offset + _FETCH - 1)
            .execute()
        )
        batch = result.data or []
        if not batch:
            break

        for r in batch:
            raw = (r.get("work_process") or "").strip()
            if not raw or raw in seen_raw:
                continue
            seen_raw.add(raw)
            normalized = _TASK_NORMALIZATION.get(raw, raw)
            if normalized and normalized not in _TASK_BLOCKLIST:
                normalized_set.add(normalized)

        if len(batch) < _FETCH:
            break
        offset += _FETCH

    return sorted(
        [{"value": v, "display_name": v} for v in normalized_set],
        key=lambda x: x["value"],
    )


# ---------------------------------------------------------------------------
# GET /public/safety-search/hub/law — Law hub list (DB-backed)
# WO-SEO-HUB-LAW. Source SoT: leg-prod law_master (is_active=True).
# Returns laws with article_count >= min_articles (default 20).
# Paginates law_article to build per-law counts in Python.
# ---------------------------------------------------------------------------


def _slug_law_name(name: str) -> str:
    """정규화: 법령명에서 특수문자(「」()（）) 제거 + strip."""
    import re
    s = str(name or "").strip()
    s = re.sub(r'[「」『』【】\[\]()（）]', '', s)
    return s.strip()


@router.get("/hub/law")
async def public_hub_law_list(
    min_articles: int = Query(default=20, ge=1, le=5000),
):
    """DB-backed law hub list from law_master.

    Returns is_active laws that have >= min_articles articles.
    Sorted by display_name (law_name).
    value = slug(law_name) for URL use.
    """
    client = _legal_supabase_dep()

    # Step 1: All active law masters
    masters_res = client.table("law_master").select(
        "id,law_name,law_name_short,ministry_name,law_type_code,current_version_id"
    ).eq("is_active", True).execute()
    masters = masters_res.data or []
    if not masters:
        return []

    # Build version_id → master map
    vid_to_master: dict[str, dict] = {}
    for m in masters:
        vid = m.get("current_version_id")
        if vid and m.get("law_name"):
            vid_to_master[vid] = m

    if not vid_to_master:
        return []

    version_ids = list(vid_to_master.keys())

    # Step 2: Count articles per version_id via pagination
    # law_article rows can be 29k+ but we only select law_version_id (tiny payload).
    from collections import Counter
    version_counts: Counter = Counter()
    _FETCH = 1000
    offset = 0

    while True:
        batch = (
            client.table("law_article")
            .select("law_version_id")
            .eq("is_deleted_in_version", False)
            .range(offset, offset + _FETCH - 1)
            .execute()
        ).data or []
        if not batch:
            break
        for r in batch:
            vid = r.get("law_version_id")
            if vid and vid in vid_to_master:
                version_counts[vid] += 1
        if len(batch) < _FETCH:
            break
        offset += _FETCH

    # Step 3: Filter and build result
    result = []
    for vid, master in vid_to_master.items():
        count = version_counts.get(vid, 0)
        if count < min_articles:
            continue
        law_name = master.get("law_name") or ""
        slug = _slug_law_name(law_name)
        if not slug:
            continue
        result.append({
            "value": slug,
            "display_name": law_name,
            "article_count": count,
            "ministry": master.get("ministry_name"),
            "law_type": master.get("law_type_code"),
        })

    return sorted(result, key=lambda x: x["display_name"])


# ---------------------------------------------------------------------------
# GET /public/safety-search/hub/law/detail?name= — Single law detail
# WO-SEO-HUB-LAW. Returns law meta + first 30 articles for SSR hub page.
# ---------------------------------------------------------------------------

@router.get("/hub/law/detail")
async def public_hub_law_detail(
    name: str = Query(..., max_length=200),
):
    """Single law meta + first 30 articles (for SSR hub page).

    name = slug(law_name) or law_name. Matched via slug normalization.
    Returns: {meta: {law_name, ministry, law_type, enforcement_date},
              articles: [{id, article_no, article_sub_no, article_title}]}
    """
    client = _legal_supabase_dep()
    name_stripped = _slug_law_name(name)

    # Find matching law_master by slug match
    masters_res = client.table("law_master").select(
        "id,law_name,law_name_short,ministry_name,law_type_code,current_version_id"
    ).eq("is_active", True).execute()
    masters = masters_res.data or []

    master = None
    for m in masters:
        if _slug_law_name(m.get("law_name") or "") == name_stripped:
            master = m
            break

    if not master:
        raise HTTPException(status_code=404, detail="LAW_NOT_FOUND")

    vid = master.get("current_version_id")
    if not vid:
        raise HTTPException(status_code=404, detail="LAW_NO_VERSION")

    # Fetch first 30 articles ordered by article_no
    articles_res = (
        client.table("law_article")
        .select("id,article_no,article_sub_no,article_title")
        .eq("law_version_id", vid)
        .eq("is_deleted_in_version", False)
        .order("article_no", desc=False)
        .limit(30)
        .execute()
    )
    articles = articles_res.data or []

    return {
        "meta": {
            "law_name": master.get("law_name"),
            "law_name_short": master.get("law_name_short"),
            "ministry": master.get("ministry_name"),
            "law_type": master.get("law_type_code"),
        },
        "articles": [
            {
                "id": str(a.get("id") or ""),
                "article_no": a.get("article_no"),
                "article_sub_no": a.get("article_sub_no"),
                "article_title": a.get("article_title"),
            }
            for a in articles
        ],
    }
