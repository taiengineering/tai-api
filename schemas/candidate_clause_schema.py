"""D-002: CandidateClause 스키마

Common Sieve 결과 객체.
SieveResult.PENDING = 미매칭 보류 (소멸 금지).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel

from schemas.semantic_clause_schema import SemanticClause


class SieveResult(str, Enum):
    KEEP = "KEEP"       # BUSINESS — 다음 단계로
    DROP = "DROP"       # AUTHORITY/FRAGMENT/DELEGATED_ORG 등 — 제거
    PENDING = "PENDING" # 미매칭 — 보류 (소멸 금지)


class CandidateClause(BaseModel):
    """SemanticClause에 거름 결과를 붙인 객체."""

    # SemanticClause 핵심 필드 (중복 보존)
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

    # 거름 결과
    sieve_result: SieveResult
    sieve_rule_id: Optional[str] = None    # 매칭된 legal_sieve_rule.id (역추적)
    sieve_class_label: Optional[str] = None  # BUSINESS/AUTHORITY/FRAGMENT 등

    @classmethod
    def from_semantic(cls, sc: SemanticClause, result: SieveResult,
                      rule_id: Optional[str] = None,
                      class_label: Optional[str] = None) -> "CandidateClause":
        return cls(
            clause_id=sc.clause_id,
            part_id=sc.part_id,
            article_id=sc.article_id,
            law_id=sc.law_id,
            law_name=sc.law_name,
            article_no=sc.article_no,
            article_title=sc.article_title,
            executor_text=sc.executor_text,
            clause_text=sc.clause_text,
            sector_hint=sc.sector_hint,
            sieve_result=result,
            sieve_rule_id=rule_id,
            sieve_class_label=class_label,
        )


class SieveSummary(BaseModel):
    """배치 거름 결과 요약."""
    total: int
    keep: int
    drop: int
    pending: int


class CandidateClauseListResponse(BaseModel):
    items: list[CandidateClause]
    total: int
    limit: int
    offset: int
