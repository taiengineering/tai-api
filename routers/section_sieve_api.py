"""D-003: Section Sieve API

CandidateClause(KEEP) → 셉터별 분리 → SectionCandidateClause.

원칙:
  SPECIAL_FACILITY 절대 할당 금지
  미매핑 법령 → universal 통과
  sector_source 필드 반드시 기록
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from db.supabase_client import get_supabase
from schemas.section_candidate_schema import SectionCandidateListResponse
from services.common_sieve_service import apply_common_sieve, load_sieve_rules
from services.section_sieve_service import load_sector_mapping, run_section_sieve
from services.semantic_clause_service import get_semantic_clauses

router = APIRouter(prefix="/section-sieve", tags=["D-003 Section Sieve"])

_VALID_SECTORS = {"INDUSTRIAL", "BUILDING", "CONSTRUCTION"}


@router.post("/run", response_model=SectionCandidateListResponse)
def run_section(
    facility_sector: str = Query(..., description="INDUSTRIAL / BUILDING / CONSTRUCTION"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """셉터별 창후보 실행.

    D-003 체크 1: 결과 total > 0.
    D-003 체크 2: SPECIAL_FACILITY 배정 건수 = 0.
    D-003 체크 3: universal 법령 포함 확인.
    """
    if facility_sector not in _VALID_SECTORS:
        raise HTTPException(
            status_code=400,
            detail=f"facility_sector는 {_VALID_SECTORS} 중 하나여야 합니다.",
        )

    supabase = get_supabase()

    # 1) SemanticClause 조회
    clauses = get_semantic_clauses(supabase, limit=limit, offset=offset)

    # 2) Common Sieve 적용 (KEEP 추출)
    sieve_rules = load_sieve_rules(supabase)
    candidates = [apply_common_sieve(c, sieve_rules) for c in clauses]

    # 3) 셉터 시브 적용
    sector_mapping = load_sector_mapping(supabase)
    section_clauses = run_section_sieve(candidates, sector_mapping, facility_sector)

    # SPECIAL_FACILITY 배정 건수 = 0 엄격 제어
    special = [s for s in section_clauses if "SPECIAL_FACILITY" in s.assigned_sectors]
    if special:
        import logging
        logging.getLogger(__name__).error(
            "SPECIAL_FACILITY 배정 발생! 즉시 차단: %d개", len(special)
        )
        section_clauses = [s for s in section_clauses if "SPECIAL_FACILITY" not in s.assigned_sectors]

    return SectionCandidateListResponse(
        items=section_clauses,
        total=len(section_clauses),
        facility_sector=facility_sector,
        limit=limit,
        offset=offset,
    )
