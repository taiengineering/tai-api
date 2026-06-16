"""D-007: Refinery API

중복 제거 + 문장 생성 → StoredDiagnosisResult 반환.

금지:
  emit_stored_diagnosis_result 삭제
  assemble_refinery_result 삭제
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from db.supabase_client import get_supabase
from schemas.stored_diagnosis_schema import RefineryResponse
from services.check_engine_adapter import load_track_a_results
from services.refinery_service import build_stored_diagnosis_result
from services.reverse_check_service import run_reverse_check_batch

router = APIRouter(prefix="/refinery", tags=["D-007 Refinery"])

_DEFAULT_STATUS_FILTER = ["MATCH_CANDIDATE", "POSSIBLE_CANDIDATE"]


@router.post("/run", response_model=RefineryResponse)
def run_refinery(
    facility_id: str = Query(..., description="factories.id"),
    limit: int = Query(500, ge=1, le=2000),
):
    """Track A 결과 → 역추적 → 중복제거 → 의무 문장 생성.

    D-007 체크 1: StoredDiagnosisResult 반환
    D-007 체크 2: obligations[].obligation_text 글읽기
    D-007 체크 3: before_dedup > after_dedup (중복 제거 발생)
    D-007 체크 4: pipeline_version = 'WO-D-007-v1'
    D-007 체크 5: 기존 anonymous-diagnosis 무결성 유지
    """
    supabase = get_supabase()

    # 1) Track A 로드
    check_results = load_track_a_results(
        supabase,
        facility_id=facility_id,
        status_filter=_DEFAULT_STATUS_FILTER,
    )
    check_results = check_results[:limit]

    # 2) 역추적
    traces = run_reverse_check_batch(check_results)

    # 3) 정제
    stored, before_count = build_stored_diagnosis_result(facility_id, traces)

    return RefineryResponse(
        result=stored,
        before_dedup=before_count,
        after_dedup=stored.total_count,
    )
