"""D-002: Common Sieve API

거름 실행 및 결과 조회 엔드포인트.
SemanticClause → CandidateClause (KEEP/DROP/PENDING) 변환.

금지:
  법 해석 기반 DROP 엔드포인트 추가 금지
  admin_executor_llm_fix.py 수정 금지
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Query

from db.supabase_client import get_supabase
from schemas.candidate_clause_schema import (
    CandidateClause,
    CandidateClauseListResponse,
    SieveResult,
    SieveSummary,
)
from services.common_sieve_service import (
    apply_common_sieve,
    load_sieve_rules,
    run_common_sieve_batch,
)
from services.semantic_clause_service import get_semantic_clauses

router = APIRouter(prefix="/common-sieve", tags=["D-002 Common Sieve"])

_SCAN_MULTIPLIER = 12  # KEEP 비율 ~9.6% → 결과 limit의 12배 스캔
_MAX_SCAN = 5000       # 무한루프 방지


@router.post("/run", response_model=SieveSummary)
def run_sieve(
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    sector_hint: Optional[str] = Query(None),
):
    """SemanticClause 배치에 거름망 적용 후 요약 반환."""
    supabase = get_supabase()
    clauses = get_semantic_clauses(
        supabase, sector_hint=sector_hint, limit=limit, offset=offset
    )
    _, summary = run_common_sieve_batch(supabase, clauses)
    return summary


@router.get("/candidates", response_model=CandidateClauseListResponse)
def list_candidates(
    sieve_result: Optional[str] = Query(None, description="KEEP / DROP / PENDING"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sector_hint: Optional[str] = Query(None),
):
    """거름 결과 목록 조회.

    sieve_result 필터가 있으면 충분한 결과가 모일 때까지 배치 스캔.
    """
    supabase = get_supabase()
    sieve_rules = load_sieve_rules(supabase)

    target_filter: Optional[SieveResult] = None
    if sieve_result:
        try:
            target_filter = SieveResult(sieve_result)
        except ValueError:
            pass

    if target_filter is None:
        clauses = get_semantic_clauses(
            supabase, sector_hint=sector_hint, limit=limit, offset=offset
        )
        items = [apply_common_sieve(c, sieve_rules) for c in clauses]
        return CandidateClauseListResponse(
            items=items, total=len(items), limit=limit, offset=offset
        )

    # 필터 있음 — 결과 limit개가 모일 때까지 배치 스캔
    collected: List[CandidateClause] = []
    scan_offset = offset
    scan_batch = max(limit * _SCAN_MULTIPLIER, 500)

    while len(collected) < limit and scan_offset < _MAX_SCAN:
        clauses = get_semantic_clauses(
            supabase,
            sector_hint=sector_hint,
            limit=scan_batch,
            offset=scan_offset,
        )
        if not clauses:
            break
        for c in clauses:
            candidate = apply_common_sieve(c, sieve_rules)
            if candidate.sieve_result == target_filter:
                collected.append(candidate)
                if len(collected) >= limit:
                    break
        scan_offset += len(clauses)

    return CandidateClauseListResponse(
        items=collected[:limit],
        total=len(collected),
        limit=limit,
        offset=offset,
    )
