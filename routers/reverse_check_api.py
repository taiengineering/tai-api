"""D-006: Reverse Check Engine API

'왜 포함됐는가' 역추적 엔드포인트.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Query

from db.supabase_client import get_supabase
from schemas.check_input_schema import CheckResult
from schemas.reverse_check_schema import ReverseCheckListResponse, ReverseCheckResult
from services.check_engine_adapter import load_track_a_results, map_applicability_to_check_result
from services.reverse_check_service import run_reverse_check_batch

router = APIRouter(prefix="/reverse-check", tags=["D-006 Reverse Check"])


@router.post("/trace-track-a", response_model=ReverseCheckListResponse)
def trace_track_a(
    facility_id: str = Query(..., description="factories.id"),
    limit: int = Query(100, ge=1, le=500),
):
    """Track A CheckResult 전체를 역추적.

    D-006 체크 1: ReverseCheckResult 목록 반환
    D-006 체크 2: full_trace에 stage_check.verdict 있음
    D-006 체크 3: law_article_url 형식 확인
    D-006 체크 4: check_method = 'track_a_facility_applicability'
    """
    supabase = get_supabase()

    # 1) Track A 결과 로드
    rows = load_track_a_results(supabase, facility_id=facility_id, limit=limit)

    # 2) CheckResult로 변환
    check_results: List[CheckResult] = [
        map_applicability_to_check_result(row) for row in rows
    ]

    # 3) 역추적
    traces = run_reverse_check_batch(check_results)

    return ReverseCheckListResponse(
        items=traces,
        total=len(traces),
        facility_id=facility_id,
    )


@router.post("/trace-single")
def trace_single(
    facility_id: str = Query(..., description="factories.id"),
    applicability_id: str = Query(..., description="facility_applicability.id"),
):
    """단일 applicability_id 역추적."""
    supabase = get_supabase()

    rows = load_track_a_results(supabase, facility_id=facility_id, limit=500)
    target = next((r for r in rows if r.get("id") == applicability_id), None)
    if not target:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="해당 applicability_id를 찾을 수 없음")

    check_result = map_applicability_to_check_result(target)
    trace = run_reverse_check_batch([check_result])[0]
    return trace
