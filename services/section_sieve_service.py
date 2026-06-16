"""D-003: Section Sieve 서비스

CandidateClause(KEEP) → law_sector_mapping 대조 → 셉터 배정
→ SectionCandidateClause

원칙:
  law_sector_mapping에 없는 법령 = universal (전 셉터 통과)
  SPECIAL_FACILITY 배정 절대 금지
  sectors 필드 = ARRAY 형식

금지:
  law_sector_mapping 테이블 수정
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

from schemas.candidate_clause_schema import CandidateClause, SieveResult
from schemas.section_candidate_schema import SectionCandidateClause

log = logging.getLogger(__name__)

_ALL_SECTORS = ["INDUSTRIAL", "BUILDING", "CONSTRUCTION"]
_FORBIDDEN_SECTORS = {"SPECIAL_FACILITY"}


def load_sector_mapping(supabase) -> Dict[str, List[str]]:
    """law_sector_mapping 전체 로드.

    Returns:
        {law_id: ["INDUSTRIAL", "BUILDING", ...]} 딕셔너리.
        SPECIAL_FACILITY는 제외하고 필터링.
    """
    mapping: Dict[str, List[str]] = {}
    offset = 0
    page = 1000
    while True:
        res = (
            supabase.table("law_sector_mapping")
            .select("law_id, sectors")
            .range(offset, offset + page - 1)
            .execute()
        )
        batch = res.data or []
        for row in batch:
            law_id = str(row.get("law_id") or "")
            sectors_raw = row.get("sectors") or []
            # SPECIAL_FACILITY 제외, 유효 셉터만
            sectors = [
                s for s in sectors_raw
                if s in set(_ALL_SECTORS)
            ]
            if law_id and sectors:
                mapping[law_id] = sectors
        if len(batch) < page:
            break
        offset += page
    return mapping


def assign_sector(
    clause: CandidateClause,
    sector_mapping: Dict[str, List[str]],
    facility_sector: str,
) -> Optional[SectionCandidateClause]:
    """단일 CandidateClause에 셉터 배정.

    반환값:
      표제 셉터와 assigned_sectors가 교차되면 SectionCandidateClause.
      교차하지 않으면 None (이 셉터와 무관한 법령).
    """
    law_id = clause.law_id

    if law_id in sector_mapping:
        assigned = sector_mapping[law_id]
        sector_source = "law_sector_mapping"
    else:
        # 미매핑 법령 → universal ("\uac00지고 \uac08" 원칙)
        assigned = _ALL_SECTORS[:]
        sector_source = "universal"

    # 입력 셉터와 교차 확인
    if facility_sector not in assigned:
        return None

    return SectionCandidateClause.from_candidate(
        clause,
        assigned_sectors=assigned,
        sector_source=sector_source,
    )


def run_section_sieve(
    candidates: List[CandidateClause],
    sector_mapping: Dict[str, List[str]],
    facility_sector: str,
) -> List[SectionCandidateClause]:
    """CandidateClause(KEEP)만 셉터 시브에 통과시키고 필터.

    - KEEP이 아닌 것(드롱/펀딩)은 셀제
    - KEEP인 것 중 해당 셉터 매칭되는 것만 반환
    """
    result: List[SectionCandidateClause] = []
    for c in candidates:
        if c.sieve_result != SieveResult.KEEP:
            continue
        section_clause = assign_sector(c, sector_mapping, facility_sector)
        if section_clause is not None:
            result.append(section_clause)
    return result
