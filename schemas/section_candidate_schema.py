"""D-003: SectionCandidateClause 스키마

Section Sieve 결과 객체.
CandidateClause(KEEP) → 섹터 배정 후 SectionCandidateClause.

원칙:
  SPECIAL_FACILITY 절대 할당 금지 (의도적 휴면)
  보여업 법령 → 모든 섹터 통과 ("universal", "가지고 감" 원칙)
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from schemas.candidate_clause_schema import CandidateClause, SieveResult


class Sector(str, Enum):
    INDUSTRIAL = "INDUSTRIAL"
    BUILDING = "BUILDING"
    CONSTRUCTION = "CONSTRUCTION"
    # SPECIAL_FACILITY: 의도적 휴면 — 절대 할당 금지


class SectionCandidateClause(BaseModel):
    """CandidateClause에 섹터 배정 결과를 붙인 객체."""

    # CandidateClause 핵심 필드 복사
    clause_id: str
    part_id: str
    article_id: str
    law_id: str
    law_name: str
    article_no: str
    article_title: str
    executor_text: str
    clause_text: str
    sector_hint: Optional[str] = None
    sieve_result: SieveResult
    sieve_rule_id: Optional[str] = None
    sieve_class_label: Optional[str] = None

    # 섹터 배정 결과
    assigned_sectors: List[str]  # ["INDUSTRIAL", "BUILDING"] 등
    sector_source: str           # "law_sector_mapping" | "universal"

    @classmethod
    def from_candidate(
        cls,
        c: CandidateClause,
        assigned_sectors: List[str],
        sector_source: str,
    ) -> "SectionCandidateClause":
        return cls(
            clause_id=c.clause_id,
            part_id=c.part_id,
            article_id=c.article_id,
            law_id=c.law_id,
            law_name=c.law_name,
            article_no=c.article_no,
            article_title=c.article_title,
            executor_text=c.executor_text,
            clause_text=c.clause_text,
            sector_hint=c.sector_hint,
            sieve_result=c.sieve_result,
            sieve_rule_id=c.sieve_rule_id,
            sieve_class_label=c.sieve_class_label,
            assigned_sectors=assigned_sectors,
            sector_source=sector_source,
        )


class SectionCandidateListResponse(BaseModel):
    items: list[SectionCandidateClause]
    total: int
    facility_sector: str
    limit: int
    offset: int
