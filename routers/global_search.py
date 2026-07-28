"""통합 교차검색 라우터 (WO-11 GlobalSearch).

Goal: G-ms4je4z3-33eada
- GET /search?q=...&types=company,user&limit=5 — 회사·회원·사업장·결제 교차검색.
- 얇은 위임: services.global_search_svc.
"""
from typing import Optional

from fastapi import APIRouter, Query

from services.global_search_svc import search

router = APIRouter(prefix="/search", tags=["통합검색"])


@router.get("")
def global_search(
    q: str = Query(..., description="검색어(2자 이상)"),
    types: Optional[str] = Query(None, description="콤마구분: company,user,factory,payment"),
    limit: int = Query(default=5, ge=1, le=20),
):
    """통합 교차검색."""
    type_list = [t.strip() for t in types.split(",")] if types else None
    data = search(q, types=type_list, limit_per_type=limit)
    return {"status": "success", "data": data}
