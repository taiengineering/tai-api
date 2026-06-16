"""D-007: StoredDiagnosisResult 스키마

중복 제거 + 문장 생성 후 최종 산출물.
DB 저장 없음 — 메모리 객체 반환.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from schemas.reverse_check_schema import ReverseCheckResult


class ObligationItem(BaseModel):
    """정제된 의무 항목 1개."""
    obligation_id: str              # applicability_id (Track A 식별자)
    law_name: Optional[str] = None
    article_no: Optional[str] = None
    article_title: Optional[str] = None
    obligation_text: str            # 생성된 의무 문장
    check_verdict: Optional[str] = None   # APPLICABLE / POSSIBLE / UNKNOWN
    check_method: str = "track_a_facility_applicability"
    law_article_url: Optional[str] = None
    trace: Optional[ReverseCheckResult] = None


class StoredDiagnosisResult(BaseModel):
    """D-007 파이프라인 최종 산출물."""
    facility_id: str
    sector: Optional[str] = None
    obligations: List[ObligationItem]
    total_count: int
    before_dedup: int               # 중복 제거 전 건수
    after_dedup: int                # 중복 제거 후 건수 (= total_count)
    generated_at: str
    pipeline_version: str = "WO-D-007-v1"
    pipeline_stages: Dict[str, Any] = {}  # 각 단계 건수 요약
