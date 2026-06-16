"""D-006: ReverseCheckResult 스키마

ObligationCandidate → "왜 포함됐는가" 역추적.
네트워크 호출 없음 — 순수 변환.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from schemas.check_input_schema import CheckResult, CheckVerdict
from schemas.ksic_signal_schema import KSICSignal
from schemas.section_candidate_schema import SectionCandidateClause


class ObligationCandidate(BaseModel):
    """D-004A + D-005의 결합 입력 객체."""

    # Track A CheckResult
    check_result: CheckResult
    # D-003 SectionCandidateClause (섹터 + 거름 trace)
    # clause_id로 매칭 — 없으면 None
    section_clause: Optional[SectionCandidateClause] = None
    # D-005 KSICSignal (없으면 None)
    ksic_signal: Optional[KSICSignal] = None


class ReverseCheckResult(BaseModel):
    """ObligationCandidate의 전체 경로를 역으로 재구성한 객체."""

    clause_id: Optional[str] = None
    facility_id: str

    # 조문 역링크
    law_name: Optional[str] = None
    article_no: Optional[str] = None
    article_title: Optional[str] = None
    law_article_url: Optional[str] = None

    # 거름 trace
    sieve_rule_id: Optional[str] = None
    sieve_class_label: Optional[str] = None
    executor_text: Optional[str] = None

    # 셉터 trace
    sector_assigned: List[str] = []
    sector_source: Optional[str] = None

    # Track A 판정
    check_verdict: CheckVerdict
    check_reason: str
    check_method: str
    applicability_status: Optional[str] = None

    # KSIC 신호
    ksic_boost: bool = False
    ksic_matched_noun: Optional[str] = None

    # 전체 trace JSON
    full_trace: Dict[str, Any] = {}


class ReverseCheckListResponse(BaseModel):
    items: List[ReverseCheckResult]
    total: int
    facility_id: str
