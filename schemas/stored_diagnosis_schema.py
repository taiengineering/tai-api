"""D-007: StoredDiagnosisResult 스키마

정제 결과 최종 객체.
중복 제거 + 문장 생성 후 저장 가능한 형태.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from schemas.reverse_check_schema import ReverseCheckResult


class ObligationItem(BaseModel):
    """의무 1건."""
    obligation_id: str              # applicability_id 재사용
    law_name: Optional[str]
    article_no: Optional[str]
    article_title: Optional[str]
    obligation_text: str            # 생성된 의무 문장
    check_verdict: Optional[str]    # APPLICABLE / POSSIBLE
    applicability_status: Optional[str]
    law_article_url: Optional[str]
    trace: ReverseCheckResult


class StoredDiagnosisResult(BaseModel):
    """정제 완료된 진단 결과."""
    facility_id: str
    obligations: List[ObligationItem]
    total_count: int
    dedup_removed: int              # 중복 제거 건수
    generated_at: datetime
    pipeline_version: str = "WO-D-007-v1"


class RefineryResponse(BaseModel):
    result: StoredDiagnosisResult
    before_dedup: int
    after_dedup: int
