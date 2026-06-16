"""D-005: KSICSignal 스키마

process_noun_match_stats 활용 → 업종(KSIC) 기반 의무 신호.

주의:
  KSICSignal은 의무 추가용 신호 (제거 근거 사용 금지)
  KSIC 신호 없어도 기존 CheckResult 유지
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class KSICSignal(BaseModel):
    """process_noun_match_stats 기반 업종 신호.

    이 신호는 의무 추가용.
    제거 근거로 사용 금지.
    """

    clause_id: str
    facility_id: str
    ksic_code: Optional[str] = None      # factories.ksic_code
    ksic_name: Optional[str] = None      # factories.ksic_name
    matched_noun: str                    # 매칭된 noun
    obligation_hits: int                 # 해당 noun의 의무 함의 횟수
    distinct_articles: int               # 관련 조문 수
    signal_source: str = "process_noun_match"  # 고정


class KSICSignalListResponse(BaseModel):
    items: List[KSICSignal]
    total: int
    facility_id: str
    clause_ids_checked: int
