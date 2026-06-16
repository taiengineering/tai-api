"""D-006: Reverse Check Engine API

'왜 포함됐는가' 역추적 엔드포인트.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from db.supabase_client import get_supabase
from schemas.reverse_check_schema import ReverseCheckListResponse
from services.check_engine_adapter import load_track_a_results
from services.reverse_check_service import run_reverse_check_batch

router = APIRouter(prefix="/reverse-check", tags=["D-006 Reverse Check"])


@router.post("/trace-track-a", response_model=ReverseCheckListResponse)
def trace_track_a(
    facility_id: str = Query(..., description="factories.id"),
    limit: int = Query(100, ge=1, le=500),
):
    """Track A CheckResult 전체를 역추적.

    D-006 체크 1: ReverseCheckResult 목록 반환
    D-006 체크 2: full_trace.stage_check.verdict 있음
    D-006 체크 3: law_article_url 형식 확인
    D-006 체크 4: check_method = 'track_a_facility_applicability'
    """
    supabase = get_supabase()

    # load_track_a_results는 이미 List[CheckResult] 반환
    check_results = load_track_a_results(supabase, facility_id=facility_id)
    check_results = check_results[:limit]

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

    check_results = load_track_a_results(supabase, facility_id=facility_id)
    target = next((r for r in check_results if r.applicability_id == applicability_id), None)
    if not target:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="해당 applicability_id를 찾을 수 없음")

    trace = run_reverse_check_batch([target])[0]
    return trace
