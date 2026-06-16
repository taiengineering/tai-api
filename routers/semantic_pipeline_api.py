"""D-001: SemanticClause Pipeline API

검증용 엔드포인트. 새 진단엔진이 아님 — 관찰 파이프라인 단계 1.

금지:
  - anonymous_diagnosis.py 수정 금지
  - semantic_clause_fix 테이블 수정 금지
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from db.supabase_client import get_supabase
from schemas.semantic_clause_schema import (
    SemanticClauseCountResponse,
    SemanticClauseListResponse,
)
from services.semantic_clause_service import (
    count_semantic_clauses,
    get_semantic_clause_by_id,
    get_semantic_clauses,
)

router = APIRouter(prefix="/semantic-pipeline", tags=["D-001 SemanticClause"])


@router.get("/clauses", response_model=SemanticClauseListResponse)
def list_semantic_clauses(
    law_id: Optional[str] = Query(None, description="law_master.id 필터"),
    sector_hint: Optional[str] = Query(None, description="INDUSTRIAL/BUILDING/CONSTRUCTION"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """SemanticClause 목록 조회.

    D-001 체크 1: 응답에 items와 total이 있는지 확인.
    """
    supabase = get_supabase()
    items = get_semantic_clauses(
        supabase,
        law_id=law_id,
        sector_hint=sector_hint,
        limit=limit,
        offset=offset,
    )
    total = count_semantic_clauses(supabase, law_id=law_id)
    return SemanticClauseListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/clauses/count", response_model=SemanticClauseCountResponse)
def count_clauses(
    law_id: Optional[str] = Query(None),
):
    """SemanticClause 총 건수.

    D-001 체크 2: total이 53,053 ±100 범위인지 확인.
    """
    supabase = get_supabase()
    total = count_semantic_clauses(supabase, law_id=law_id)
    return SemanticClauseCountResponse(total=total)


@router.get("/clauses/{clause_id}")
def get_clause(
    clause_id: str,
):
    """clause_id로 단건 조회. 역추적용."""
    supabase = get_supabase()
    clause = get_semantic_clause_by_id(supabase, clause_id)
    if not clause:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="clause not found")
    return {"status": "success", "data": clause.model_dump()}
