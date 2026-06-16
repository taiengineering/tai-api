"""D-006: Reverse Check Engine API

ObligationCandidate → ReverseCheckResult 역추적.

Track A 결과를 기반으로 하며, section_clause는
같은 article_id를 갖는 SemanticClause로 매칭을 시도.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from db.supabase_client import get_supabase
from schemas.check_input_schema import CheckVerdict
from schemas.reverse_check_schema import (
    ObligationCandidate,
    ReverseCheckListResponse,
)
from services.check_engine_adapter import load_track_a_results
from services.common_sieve_service import apply_common_sieve, load_sieve_rules
from services.ksic_signal_service import generate_ksic_signals, load_noun_stats
from services.reverse_check_service import run_reverse_check_batch
from services.section_sieve_service import assign_sector, load_sector_mapping
from services.semantic_clause_service import get_semantic_clauses
from schemas.candidate_clause_schema import SieveResult

router = APIRouter(prefix="/reverse-check", tags=["D-006 Reverse Check"])

_VALID_SECTORS = {"INDUSTRIAL", "BUILDING", "CONSTRUCTION"}


@router.post("/run", response_model=ReverseCheckListResponse)
def run_reverse(
    facility_id: str = Query(...),
    facility_sector: str = Query(..., description="INDUSTRIAL / BUILDING / CONSTRUCTION"),
    limit: int = Query(200, ge=1, le=1000),
):
    """Track A 결과 기반 역추적 실행.

    D-006 체크 1: ReverseCheckResult 목록 반환
    D-006 체크 2: full_trace 필드 아래 track_a 있음
    D-006 체크 3: law_article_url 형식 확인
    """
    if facility_sector not in _VALID_SECTORS:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"facility_sector는 {_VALID_SECTORS} 중 하나")

    supabase = get_supabase()

    # 1) Track A CheckResult 조회
    check_results = load_track_a_results(
        supabase, facility_id,
        status_filter=["MATCH_CANDIDATE", "POSSIBLE_CANDIDATE"]
    )

    # 2) SemanticClause → Section Sieve (article_id 매칭용)
    clauses = get_semantic_clauses(supabase, limit=limit)
    sieve_rules = load_sieve_rules(supabase)
    sector_mapping = load_sector_mapping(supabase)

    # article_id → SectionCandidateClause 매핑
    article_to_section: dict = {}
    for c in clauses:
        candidate = apply_common_sieve(c, sieve_rules)
        if candidate.sieve_result != SieveResult.KEEP:
            continue
        sc = assign_sector(candidate, sector_mapping, facility_sector)
        if sc and sc.article_id:
            article_to_section[sc.article_id] = sc

    # 3) KSIC 신호
    section_list = list(article_to_section.values())
    noun_stats = load_noun_stats(supabase)
    ksic_signals = generate_ksic_signals(supabase, section_list, facility_id, noun_stats)
    clause_to_ksic = {s.clause_id: s for s in ksic_signals}

    # 4) ObligationCandidate 조립
    obligations = []
    for cr in check_results:
        sc = article_to_section.get(cr.article_id or "")
        ks = clause_to_ksic.get(sc.clause_id if sc else "", None)
        obligations.append(ObligationCandidate(
            check_result=cr,
            section_clause=sc,
            ksic_signal=ks,
        ))

    # 5) 역추적
    results = run_reverse_check_batch(obligations)

    return ReverseCheckListResponse(
        items=results,
        total=len(results),
        facility_id=facility_id,
    )
