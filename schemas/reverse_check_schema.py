"""D-006: ReverseCheckResult 스키마

'왜 포함됐는가' 역추적 객체.
각 의무 후보의 통과 경로 전체를 한 객체에 담는다.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ReverseCheckResult(BaseModel):
    """의무 후보의 전체 경로 역추적.

    D-006 입력: ObligationCandidate (CheckResult + 추가 맥락)
    D-006 출력: 이 객체
    D-006 역할: 순수 변환 (DB 쓰기 없음, 네트워크 없음)
    """

    # 식별자
    clause_id: str                        # semantic_clause_fix.id
    facility_id: str

    # 법령 원문 연결
    law_name: Optional[str] = None
    article_no: Optional[str] = None
    article_title: Optional[str] = None
    executor_text: Optional[str] = None
    clause_text: Optional[str] = None
    law_article_url: Optional[str] = None  # https://www.law.go.kr/법령/{law_name}/{article_no}

    # 거름망 경로
    sieve_rule_id: Optional[str] = None    # legal_sieve_rule.id (KEEP 근거)
    sieve_class_label: Optional[str] = None  # BUSINESS / AUTHORITY / FRAGMENT / None(PENDING)
    sieve_result: Optional[str] = None     # KEEP / DROP / PENDING

    # 섹터 경로
    assigned_sectors: List[str] = []       # ["INDUSTRIAL", ...]
    sector_source: Optional[str] = None    # "law_sector_mapping" | "clause_hint" | "universal"

    # Check 경로
    check_verdict: Optional[str] = None    # APPLICABLE / POSSIBLE / UNKNOWN
    check_reason: Optional[str] = None
    check_method: Optional[str] = None     # "track_a_facility_applicability"
    applicability_status: Optional[str] = None  # MATCH_CANDIDATE / POSSIBLE_CANDIDATE

    # KSIC 신호
    ksic_boost: bool = False
    ksic_matched_noun: Optional[str] = None
    ksic_code: Optional[str] = None

    # 전체 경로 직렬화
    full_trace: Dict[str, Any] = {}


class ReverseCheckListResponse(BaseModel):
    items: List[ReverseCheckResult]
    total: int
    facility_id: str
