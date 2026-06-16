"""D-002: Common Sieve API

거름 실행 및 결과 조회 엔드포인트.
SemanticClause → CandidateClause (KEEP/DROP/PENDING) 변환.

금지:
  법 해석 기반 DROP 엔드포인트 추가 금지
  admin_executor_llm_fix.py 수정 금지
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from db.supabase_client import get_supabase
from schemas.candidate_clause_schema import (
    CandidateClauseListResponse,
    SieveResult,
    SieveSummary,
)
from services.common_sieve_service import (
    apply_common_sieve,
    run_common_sieve_batch,
    _load_sieve_rules,
)
from services.semantic_clause_service import get_semantic_clauses, count_semantic_clauses

router = APIRouter(prefix="/common-sieve", tags=["D-002 Common Sieve"])


@router.post("/run", response_model=SieveSummary)
def run_sieve(
    limit: int = Query(500, ge=1, le=2000,
                       description="처리할 SemanticClause 수 (개발·검증용)"),
    offset: int = Query(0, ge=0),
    sector_hint: Optional[str] = Query(None),
):
    """SemanticClause 배치에 거름망 적용 후 요약 반환.

    D-002 체크 1: keep/drop/pending 합계 = total 인지 확인.
    """
    supabase = get_supabase()
    clauses = get_semantic_clauses(
        supabase, sector_hint=sector_hint, limit=limit, offset=offset
    )
    _, summary = run_common_sieve_batch(supabase, clauses)
    return summary


@router.get("/candidates", response_model=CandidateClauseListResponse)
def list_candidates(
    sieve_result: Optional[str] = Query(
        None, description="KEEP / DROP / PENDING 필터"
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sector_hint: Optional[str] = Query(None),
):
    """거름 결과 목록 조회.

    D-002 체크 3·4: DROP/KEEP 샘플 글읽기용.
    sieve_result 필터로 KEEP/DROP/PENDING 각각 조회 가능.
    """
    supabase = get_supabase()
    clauses = get_semantic_clauses(
        supabase, sector_hint=sector_hint, limit=limit, offset=offset
    )
    sieve_rules = _load_sieve_rules(supabase)

    all_candidates = [apply_common_sieve(c, sieve_rules) for c in clauses]

    # 필터 적용
    if sieve_result:
        try:
            target = SieveResult(sieve_result)
            all_candidates = [c for c in all_candidates if c.sieve_result == target]
        except ValueError:
            pass  # 잘못된 값이면 전체 반환

    return CandidateClauseListResponse(
        items=all_candidates,
        total=len(all_candidates),
        limit=limit,
        offset=offset,
    )
