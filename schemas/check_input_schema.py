"""D-004A: CheckResult 스키마

Track A (facility_applicability 테이블) 결과를
표준 CheckResult로 래핑하는 트랭.

금지:
  evaluate_single_factory 수정
  evaluate_draft_for_facility 수정
  SemanticClause → facility_applicability_eval 연결 시도
  (binding_field 없어서 평가 대상 0건 — 가짜 연결)
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel


class CheckVerdict(str, Enum):
    APPLICABLE = "APPLICABLE"         # 해당됨 (MATCH_CANDIDATE)
    POSSIBLE = "POSSIBLE"             # 잠정 해당 (POSSIBLE_CANDIDATE)
    NOT_APPLICABLE = "NOT_APPLICABLE" # 해당 안 됨
    UNKNOWN = "UNKNOWN"               # 판단 불가


class CheckResult(BaseModel):
    """Track A facility_applicability row를 래핑한 관찰용 객체.

    D-004A의 입력: facility_applicability rows (읽기만)
    D-004A의 출력: 이 객체
    D-004A의 금지:
      evaluate_single_factory 수정
      evaluate_draft_for_facility 수정
      SemanticClause → facility_applicability_eval 연결 시도
    """

    # facility_applicability 연결 필드
    applicability_id: str         # facility_applicability.id
    facility_id: str              # facility_applicability.factory_id
    draft_id: str                 # facility_applicability.draft_id
    applicability_status: str     # MATCH_CANDIDATE / POSSIBLE_CANDIDATE
    match_details: Optional[Dict[str, Any]] = None  # jsonb 그대로

    # 조문 연결 필드 (executable_draft → law_article → law_master)
    article_id: Optional[str] = None
    article_no: Optional[str] = None
    article_title: Optional[str] = None
    law_name: Optional[str] = None

    # 표준 판정
    verdict: CheckVerdict
    reason: str                   # 판정 근거 (역추적 필수)
    check_method: str = "track_a_facility_applicability"  # 고정


class CheckResultListResponse(BaseModel):
    items: list[CheckResult]
    total: int
    facility_id: str
