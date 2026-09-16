"""routers.search_dictionary — lexical search dictionary endpoints.

MASTER-WO-TAI-SEARCH-DICT-001. Prefix /search-dict (verified non-colliding with
existing /search, /public/safety-search/kosha, public_knowledge_graph).
Thin router: parse -> service -> {status, data} envelope (repo convention).
Register by appending {"module": "routers.search_dictionary"} to
router_registry/public.py ROUTERS.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from services import search_query_svc, search_dictionary_svc
from services.search_query_svc import SearchDictError

router = APIRouter(prefix="/search-dict", tags=["search-dictionary"])


@router.get("/lookup")
def lookup(
    q: str = Query(..., description="search query"),
    limit: int = Query(10, ge=1, le=100),
    subject_type: str | None = Query(None),
):
    try:
        data = search_query_svc.lookup(q, limit=limit, subject_type=subject_type)
    except SearchDictError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "data": data}


@router.get("/health")
def health():
    try:
        data = search_query_svc.health()
    except SearchDictError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"status": "success", "data": data}


@router.get("/census")
def census():
    try:
        data = search_dictionary_svc.census()
    except SearchDictError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return {"status": "success", "data": data}
