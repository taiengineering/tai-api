"""Public WAVE 2 Smart Search provider.

GET /public/safety-search/kosha?q=&page=&page_size=
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from services.kosha_smart_search import (
    MAX_PAGE_SIZE,
    SmartSearchQueryError,
    search_kosha_public,
)

router = APIRouter(prefix="/public/safety-search", tags=["Public safety search"])


@router.get("/kosha")
async def public_kosha_smart_search(
    q: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=MAX_PAGE_SIZE),
):
    try:
        return await search_kosha_public(q=q, page=page, page_size=page_size)
    except SmartSearchQueryError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
