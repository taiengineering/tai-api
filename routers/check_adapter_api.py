"""D-004A: Track A Check Adapter API

facility_applicability 결과를 CheckResult로 변환해 관찰.

금지:
  evaluate_single_factory 수정
  evaluate_draft_for_facility 수정
  SemanticClause → facility_applicability_eval 연결 시도
  facility_applicability 테이블 수정
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from db.supabase_client import get_supabase
from schemas.check_input_schema import CheckResultListResponse
from services.check_engine_adapter import load_track_a_results

router = APIRouter(prefix="/check-adapter", tags=["D-004A Track A Check Adapter"])


@router.post("/run-track-a", response_model=CheckResultListResponse)
def run_track_a(
    facility_id: str = Query(..., description="factories.id (UUID)"),
    status: Optional[str] = Query(
        None,
        description="MATCH_CANDIDATE / POSSIBLE_CANDIDATE / 전체"
    ),
):
    """Track A 결과 조회 및 CheckResult 변환.

    D-004A 체크 1: CheckResult 목록 반환
    D-004A 체크 2: draft_id / applicability_status / check_method 필드 확인
    D-004A 체크 3: reason 필드 글읽기
    """
    supabase = get_supabase()

    status_filter = None
    if status:
        valid = {"MATCH_CANDIDATE", "POSSIBLE_CANDIDATE"}
        if status not in valid:
            raise HTTPException(
                status_code=400,
                detail=f"status는 {valid} 중 하나여야 합니다."
            )
        status_filter = [status]
    else:
        status_filter = ["MATCH_CANDIDATE", "POSSIBLE_CANDIDATE"]

    results = load_track_a_results(supabase, facility_id, status_filter)

    return CheckResultListResponse(
        items=results,
        total=len(results),
        facility_id=facility_id,
    )
