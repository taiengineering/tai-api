"""Public EXT-165 화학사고 read. 현행 스냅샷만."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from services.ext165_chemical_accident.read import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    MAX_Q_LEN,
    ChemicalAccidentQueryError,
    get_chemical_accident_by_datano,
    list_chemical_accidents,
    sanitize_q,
)

router = APIRouter(prefix="/public/accidents", tags=["Public chemical accidents"])

_override_store = None
_production = None


def configure_chemical_accident_public(store) -> None:
    global _override_store, _production
    _override_store = store
    _production = None


def reset_chemical_accident_public() -> None:
    configure_chemical_accident_public(None)


def _store():
    global _production
    if _override_store is not None:
        return _override_store
    try:
        if _production is None:
            from db.supabase_client import get_supabase
            from services.ext165_chemical_accident.read import SupabaseChemicalAccidentStore
            _production = SupabaseChemicalAccidentStore(get_supabase())
        return _production
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="CHEMICAL_ACCIDENT_UNAVAILABLE") from None


def _http(exc: ChemicalAccidentQueryError) -> HTTPException:
    if exc.code == "NOT_FOUND":
        return HTTPException(status_code=404, detail="NOT_FOUND")
    if exc.code == "DATANO_INVALID":
        return HTTPException(status_code=422, detail="DATANO_INVALID")
    if exc.code in ("Q_INVALID", "Q_TOO_LONG"):
        return HTTPException(status_code=422, detail=exc.code)
    return HTTPException(status_code=503, detail=exc.code)


@router.get("/chemical")
def public_chemical_accident_list(
    q: str | None = Query(None, max_length=MAX_Q_LEN),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    try:
        term = sanitize_q(q)
        return list_chemical_accidents(_store(), q=term, page=page, page_size=page_size)
    except ChemicalAccidentQueryError as exc:
        raise _http(exc) from exc


@router.get("/chemical/{datano}")
def public_chemical_accident_detail(datano: str):
    try:
        return get_chemical_accident_by_datano(_store(), datano)
    except ChemicalAccidentQueryError as exc:
        raise _http(exc) from exc
