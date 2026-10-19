"""WO-CHEM-07 dormant KOSHA MSDS public router.

Prefix: /public/kosha/msds

Implemented but NOT registered in router_registry (WO §16). The
router delegates every read to services.kosha_msds.read; it does not
open a Supabase table directly, does not join tables, does not
compute hashes, and does not carry any DML path.

WO-CHEM-SEO-PREVIEW-LIVE-001 adds a mode-flag layer (env var
KOSHA_MSDS_PUBLIC_MODE) so activation can be flipped without code:

  * off          → 503 Service Unavailable (dormant, default)
  * seo_preview  → serve the 1,997-chemical preview slice
                   (view kosha_msds_seo_preview_current)
  * full         → serve the full PUBLISHED_FULL catalog
                   (view kosha_msds_current)

Router registration in router_registry/public.py is still a separate
future WO. This file remains not-imported by the app.

WO-WWW-PERF-004-P0S-OS-PATCH-001:
  PATCH-01  no legacy fallback — OS errors → 503 with stable error codes
  PATCH-02  check_snapshot_gate() called before every OS search
  PATCH-05  per-item match_type / matched_term annotations on q-path
  PATCH-07  scope passed to search_from_chem_ids → hydrate_chem_ids
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query

from services.kosha_msds.contract import (
    ALLOWED_PUBLIC_MODES,
    DEFAULT_PUBLIC_MODE,
    PUBLICATION_SCOPE_FULL,
    PUBLICATION_SCOPE_SEO_PREVIEW,
    PUBLIC_MODE_ENV_VAR,
    PUBLIC_MODE_FULL,
    PUBLIC_MODE_OFF,
    PUBLIC_MODE_SEO_PREVIEW,
)
from services.kosha_msds.opensearch_query import (
    MsdsCandidateEnumerationIncompleteError,
    MsdsCandidateEnumerationIntegrityError,
    MsdsCasIndexNotReadyError,
    MsdsHydrationIntegrityError,
    MsdsOsError,
    MsdsPaginationDepthExceededError,
    MsdsSnapshotGateError,
    check_snapshot_gate,
    os_chem_available,
    search_by_q_os,
    search_os,
)
from services.kosha_msds.read import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    SECTION_MAX,
    SECTION_MIN,
    SectionNoOutOfRange,
    SupabaseMsdsReadStore,
    get_by_chem_id,
    get_section,
    list_current,
    search,
    search_from_chem_ids,
)
from services.kosha_msds.search_adapter import (
    MATCH_BM25_NORI,
    MATCH_IDENTIFIER_EXACT,
    search_by_q,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/public/kosha/msds",
    tags=["KOSHA MSDS public"],
)

_store = None


def get_store():
    """Lazy singleton — same shape used by routers/kosha_public_materials.py.

    In tests, override via FastAPI dependency injection or by
    setting the module-level _store to a MemoryMsdsReadStore.
    """
    global _store
    if _store is None:
        _store = SupabaseMsdsReadStore()
    return _store


def _read_mode() -> str:
    """Read KOSHA_MSDS_PUBLIC_MODE env var. Unknown values → off (fail-safe)."""
    raw = (os.environ.get(PUBLIC_MODE_ENV_VAR) or DEFAULT_PUBLIC_MODE).strip().lower()
    if raw not in ALLOWED_PUBLIC_MODES:
        return PUBLIC_MODE_OFF
    return raw


def _mode_to_scope(mode: str) -> str:
    """Map public mode → CHEM-06 publication scope.

    off is rejected by the caller with 503 before this is called.
    """
    if mode == PUBLIC_MODE_SEO_PREVIEW:
        return PUBLICATION_SCOPE_SEO_PREVIEW
    if mode == PUBLIC_MODE_FULL:
        return PUBLICATION_SCOPE_FULL
    # Defensive: caller must reject "off" first.
    raise ValueError(f"cannot map mode {mode!r} to a scope")


def _require_active_mode() -> str:
    """Return the active mode or raise 503 when dormant.

    Fail-closed: any misconfiguration (unknown value, empty) collapses to
    off, which then raises 503. Callers get an explicit MSDS_PUBLIC_DORMANT
    marker in the response body.
    """
    mode = _read_mode()
    if mode == PUBLIC_MODE_OFF:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "MSDS_PUBLIC_DORMANT",
                "message": (
                    f"KOSHA MSDS public router is dormant. "
                    f"Set {PUBLIC_MODE_ENV_VAR} to one of "
                    f"{sorted(ALLOWED_PUBLIC_MODES - {PUBLIC_MODE_OFF})} "
                    f"to activate."
                ),
            },
        )
    return mode


def _has_any_search_filter(
    chem_id: Optional[str],
    cas_no: Optional[str],
    ke_no: Optional[str],
    en_no: Optional[str],
    un_no: Optional[str],
    name_ko: Optional[str],
    name_en: Optional[str],
) -> bool:
    return any(bool(x) for x in (chem_id, cas_no, ke_no, en_no, un_no, name_ko, name_en))


@router.get("")
def list_or_search_msds(
    q: Optional[str] = Query(default=None, description="Free-text natural-language query. "
                                                        "Routed through CHEM-09 search adapter "
                                                        "(Kiwi + shared terminology dictionary)."),
    chem_id: Optional[str] = Query(default=None),
    cas_no: Optional[str] = Query(default=None),
    ke_no: Optional[str] = Query(default=None),
    en_no: Optional[str] = Query(default=None),
    un_no: Optional[str] = Query(default=None),
    name_ko: Optional[str] = Query(default=None),
    name_en: Optional[str] = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
):
    """List / filter / free-text search the current KOSHA MSDS catalog.

    Precedence:
      - `q` present  → search_by_q_os (CHEM-09 plan → OS BM25/Nori)
      - structured filter present  → search_os AND filter
                                     (chem_id / cas_no / ke_no / en_no /
                                      un_no / name_ko / name_en)
      - nothing        → CHEM-06 read.list_current (chem_id ASC)

    `q` and structured filters are not mixed in one call. If both are
    supplied, `q` wins; structured filters are ignored for that request.

    OS errors raise 503 with stable error codes — no legacy Supabase
    fallback (PATCH-01). check_snapshot_gate() is called before every
    OS operation (PATCH-02).

    Publication scope is derived from the KOSHA_MSDS_PUBLIC_MODE env var
    at request time. Preview mode never leaks non-preview chemicals.
    """
    mode = _require_active_mode()
    scope = _mode_to_scope(mode)
    store = get_store()

    has_q = q is not None and q.strip()
    has_filter = _has_any_search_filter(chem_id, cas_no, ke_no, en_no, un_no, name_ko, name_en)

    if has_q or has_filter:
        try:
            if has_q:
                chem_ids, total, match_meta = search_by_q_os(
                    q=q, limit=limit, offset=offset
                )
                result = search_from_chem_ids(
                    store=store, chem_ids=chem_ids,
                    total=total, limit=limit, offset=offset, scope=scope,
                )
                # PATCH-05/P0-02: per-item CHEM-09 match type from page-scoped per_item_metadata
                per_item = match_meta.get("per_item_metadata") or {}
                ident_kind = match_meta.get("identifier_kind")
                for item in result["items"]:
                    cid = item.get("chem_id")
                    if per_item and cid and cid in per_item:
                        item["match_type"] = per_item[cid]["match_type"]
                        item["matched_term"] = per_item[cid]["matched_term"]
                    else:
                        # Fallback: identifier path → IDENTIFIER_EXACT; free-text → top-level match_type
                        item["match_type"] = (
                            MATCH_IDENTIFIER_EXACT if ident_kind
                            else match_meta.get("match_type") or MATCH_BM25_NORI
                        )
                        item["matched_term"] = match_meta.get("normalized_query")
                result["match_metadata"] = match_meta
                return result
            else:
                chem_ids, total = search_os(
                    chem_id=chem_id, cas_no=cas_no, ke_no=ke_no,
                    en_no=en_no, un_no=un_no,
                    name_ko=name_ko, name_en=name_en,
                    limit=limit, offset=offset,
                )
                return search_from_chem_ids(
                    store=store, chem_ids=chem_ids,
                    total=total, limit=limit, offset=offset, scope=scope,
                )

        except MsdsCasIndexNotReadyError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "MSDS_CAS_INDEX_NOT_READY", "message": str(exc)},
            ) from exc
        except MsdsPaginationDepthExceededError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "MSDS_PAGINATION_DEPTH_EXCEEDED", "message": str(exc)},
            ) from exc
        except MsdsHydrationIntegrityError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "MSDS_HYDRATION_INTEGRITY_FAIL", "message": str(exc)},
            ) from exc
        except MsdsCandidateEnumerationIncompleteError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "MSDS_CANDIDATE_ENUMERATION_INCOMPLETE", "message": str(exc)},
            ) from exc
        except MsdsCandidateEnumerationIntegrityError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "MSDS_CANDIDATE_ENUMERATION_INTEGRITY", "message": str(exc)},
            ) from exc
        except Exception as exc:
            logger.exception("MSDS OS search failed")
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "MSDS_SEARCH_UNAVAILABLE",
                    "message": "MSDS OpenSearch search is currently unavailable",
                },
            ) from exc

    return list_current(store=store, limit=limit, offset=offset, scope=scope)


@router.get("/{chem_id}")
def get_msds_detail(chem_id: str):
    """Return the current chemical detail including its 16 sections.

    Membership is enforced via the scoped view: a chem_id outside the
    active mode's slice returns 404 (WO §11 "preview membership 밖의
    chem_id는 customer-facing으로 노출하지 않는다").
    """
    mode = _require_active_mode()
    scope = _mode_to_scope(mode)
    body = get_by_chem_id(chem_id, store=get_store(), include_sections=True, scope=scope)
    if body is None:
        raise HTTPException(status_code=404, detail="MSDS_CHEMICAL_NOT_FOUND")
    return body


@router.get("/{chem_id}/sections/{section_no}")
def get_msds_section(
    chem_id: str,
    section_no: int = Path(..., ge=SECTION_MIN, le=SECTION_MAX),
):
    """Return one section of a current chemical.

    section_no is validated by FastAPI's Path(ge=1, le=16) → 422 on
    out-of-range. If the chemical is not in the scoped current view,
    404 (regardless of whether a section row exists in the underlying
    table). If the chemical is in-scope but the requested section is
    absent, 404.
    """
    mode = _require_active_mode()
    scope = _mode_to_scope(mode)
    try:
        body = get_section(chem_id, section_no, store=get_store(), scope=scope)
    except SectionNoOutOfRange as exc:
        # Belt-and-braces: FastAPI's Path validation already rejects
        # out-of-range values with 422 before this handler runs. This
        # branch handles the case where the service is called with a
        # value that bypassed Path validation (e.g., programmatic use).
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body is None:
        raise HTTPException(status_code=404, detail="MSDS_SECTION_NOT_FOUND")
    return body
