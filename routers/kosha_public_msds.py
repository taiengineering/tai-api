"""WO-CHEM-07 dormant KOSHA MSDS public router.

Prefix: /public/kosha/msds

Implemented but NOT registered in router_registry (WO §16). The
router delegates every read to services.kosha_msds.read; it does not
open a Supabase table directly, does not join tables, does not
compute hashes, and does not carry any DML path. Activation is a
separate future WO gated on:

  1. CHEM-04 full corpus (329,088 authoritative sections)
  2. Production materialize under a future owner-approved WO
  3. A snapshot with publish_state=PUBLISHED_FULL
  4. Explicit owner-approved activation WO

Until then, this file exists on disk but the app does not import it.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query

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
)

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
    """List or filter-search the current KOSHA MSDS catalog.

    - Zero filters → list_current (deterministic ORDER BY chem_id ASC).
    - Any filter present → search (exact filters AND-ed; name partial).
    """
    store = get_store()
    if _has_any_search_filter(chem_id, cas_no, ke_no, en_no, un_no, name_ko, name_en):
        return search(
            store=store,
            chem_id=chem_id,
            cas_no=cas_no,
            ke_no=ke_no,
            en_no=en_no,
            un_no=un_no,
            name_ko=name_ko,
            name_en=name_en,
            limit=limit,
            offset=offset,
        )
    return list_current(store=store, limit=limit, offset=offset)


@router.get("/{chem_id}")
def get_msds_detail(chem_id: str):
    """Return the current chemical detail including its 16 sections."""
    body = get_by_chem_id(chem_id, store=get_store(), include_sections=True)
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
    out-of-range. If the chemical is not in the current view, 404
    (regardless of whether a section row exists in the underlying
    table). If the chemical is current but the requested section is
    absent, 404.
    """
    try:
        body = get_section(chem_id, section_no, store=get_store())
    except SectionNoOutOfRange as exc:
        # Belt-and-braces: FastAPI's Path validation already rejects
        # out-of-range values with 422 before this handler runs. This
        # branch handles the case where the service is called with a
        # value that bypassed Path validation (e.g., programmatic use).
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if body is None:
        raise HTTPException(status_code=404, detail="MSDS_SECTION_NOT_FOUND")
    return body
