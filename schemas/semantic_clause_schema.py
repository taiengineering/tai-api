"""D-001: SemanticClause 스키마

semantic_clause_fix + law_article_part + law_article + law_master JOIN 결과의
표준 Pydantic 객체. 다운스트림 단계(D-002~)의 기반 단위.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SemanticClause(BaseModel):
    """semantic_clause_fix 기반 의미절 객체.

    executor_text: 법령에서 추출된 주체 텍스트 (수범자).
      이 필드가 D-002 Common Sieve 의 거름 대상.
    clause_text: 해당 조문 part 원문.
    sector_hint: 법령 수집 시 표시된 섹터 힌트 (None = 미지정).
    """

    clause_id: str          # semantic_clause_fix.id
    part_id: str            # law_article_part.id
    article_id: str         # law_article.id
    law_id: str             # law_master.id
    law_name: str
    article_no: str
    article_title: str
    executor_text: str      # D-002 거름 대상 필드
    clause_text: str        # 조문 part 원문
    sector_hint: Optional[str] = None  # INDUSTRIAL/BUILDING/CONSTRUCTION/None
    created_at: Optional[datetime] = None


class SemanticClauseListResponse(BaseModel):
    """SemanticClause 목록 응답."""

    items: list[SemanticClause]
    total: int
    limit: int
    offset: int


class SemanticClauseCountResponse(BaseModel):
    """SemanticClause 건수 응답."""

    total: int
