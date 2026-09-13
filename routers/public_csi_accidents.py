"""Public CSI accident read. READY current only. HOLD = 404."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from services.csi_accidents.public import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PublicCsiQueryError,
    get_public_accident,
    list_public_accidents,
)

router = APIRouter(prefix="/public/accidents", tags=["Public CSI accidents"])

_override_store = None
_production = None


def configure_csi_public(store) -> None:
    global _override_store, _production
    _override_store = store
    _production = None


def reset_csi_public() -> None:
    configure_csi_public(None)


def _store():
    global _production
    if _override_store is not None:
        return _override_store
    try:
        if _production is None:
            from db.supabase_client import get_supabase
            from services.csi_accidents.public import SupabaseCsiPublicStore

            _production = SupabaseCsiPublicStore(get_supabase())
        return _production
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="CSI_PUBLIC_UNAVAILABLE") from None


def _http(exc: PublicCsiQueryError) -> HTTPException:
    if exc.code == "NOT_FOUND":
        return HTTPException(status_code=404, detail="NOT_FOUND")
    if exc.code == "UUID_INVALID":
        return HTTPException(status_code=404, detail="NOT_FOUND")
    return HTTPException(status_code=422, detail=exc.code)


@router.get("/csi")
def public_csi_list(
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
):
    try:
        return list_public_accidents(_store(), q=q, page=page, page_size=page_size)
    except PublicCsiQueryError as exc:
        raise _http(exc) from exc


@router.get("/csi/{case_uuid}")
def public_csi_detail(case_uuid: str):
    try:
        return get_public_accident(_store(), case_uuid)
    except PublicCsiQueryError as exc:
        raise _http(exc) from exc
