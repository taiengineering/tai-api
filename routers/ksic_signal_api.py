"""D-005: KSIC Signal Engine API

process_noun_match_stats 활용 → 업종 기반 의무 신호 생성.

주의:
  KSICSignal은 의무 추가용 신호 (제거 근거 가능 금지)
  KSIC 신호 없어도 기존 CheckResult 유지
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from db.supabase_client import get_supabase
from schemas.ksic_signal_schema import KSICSignalListResponse
from services.common_sieve_service import apply_common_sieve, load_sieve_rules
from services.ksic_signal_service import generate_ksic_signals, load_noun_stats
from services.section_sieve_service import assign_sector, load_sector_mapping
from services.semantic_clause_service import get_semantic_clauses

router = APIRouter(prefix="/ksic-signal", tags=["D-005 KSIC Signal"])

_VALID_SECTORS = {"INDUSTRIAL", "BUILDING", "CONSTRUCTION"}


@router.post("/run", response_model=KSICSignalListResponse)
def run_ksic_signal(
    facility_id: str = Query(..., description="factories.id"),
    facility_sector: str = Query(..., description="INDUSTRIAL / BUILDING / CONSTRUCTION"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """clause_text 기반 KSIC 신호 생성.

    D-005 체크 1: KSICSignal 목록 반환
    D-005 체크 2: 의무 건수가 이전 단계보다 줄지 않음 확인
    D-005 체크 3: signal_source 필드 기록됨
    """
    if facility_sector not in _VALID_SECTORS:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"facility_sector는 {_VALID_SECTORS} 중 하나")

    supabase = get_supabase()

    # 1) SemanticClause → Common Sieve → Section Sieve
    clauses = get_semantic_clauses(supabase, limit=limit, offset=offset)
    sieve_rules = load_sieve_rules(supabase)
    sector_mapping = load_sector_mapping(supabase)

    candidates = [apply_common_sieve(c, sieve_rules) for c in clauses]
    from schemas.candidate_clause_schema import SieveResult
    section_clauses = []
    for c in candidates:
        if c.sieve_result != SieveResult.KEEP:
            continue
        sc = assign_sector(c, sector_mapping, facility_sector)
        if sc:
            section_clauses.append(sc)

    # 2) KSIC 신호 생성
    noun_stats = load_noun_stats(supabase)
    signals = generate_ksic_signals(supabase, section_clauses, facility_id, noun_stats)

    return KSICSignalListResponse(
        items=signals,
        total=len(signals),
        facility_id=facility_id,
        clause_ids_checked=len(section_clauses),
    )
