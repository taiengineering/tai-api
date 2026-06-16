"""D-007: Refinery API

중복 제거 + 문장 생성 → StoredDiagnosisResult.

기존 함수 삭제 금지:
  emit_stored_diagnosis_result
  assemble_refinery_result
  fetch_compiler_candidates
  evaluate_single_factory
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from db.supabase_client import get_supabase
from schemas.stored_diagnosis_schema import StoredDiagnosisResult
from services.check_engine_adapter import load_track_a_results
from services.refinery_service import build_stored_diagnosis_result
from services.reverse_check_service import run_reverse_check_batch

router = APIRouter(prefix="/refinery", tags=["D-007 Refinery"])

_DEFAULT_STATUS_FILTER = ["MATCH_CANDIDATE", "POSSIBLE_CANDIDATE"]


@router.post("/run", response_model=StoredDiagnosisResult)
def run_refinery(
    facility_id: str = Query(..., description="factories.id"),
    sector: str = Query(None, description="INDUSTRIAL / BUILDING / CONSTRUCTION (선택)"),
    limit: int = Query(500, ge=1, le=2000),
):
    """Track A → 역추적 → 중복 제거 → 문장 생성 → StoredDiagnosisResult.

    D-007 체크 1: obligations 목록 반환
    D-007 체크 2: obligations[].trace.full_trace 포함
    D-007 체크 3: before_dedup vs after_dedup 건수 로그
    D-007 체크 4: pipeline_version = 'WO-D-007-v1'
    D-007 체크 5: 기존 anonymous-diagnosis 결과 동일 (무결성)
    """
    supabase = get_supabase()

    # 1) Track A CheckResult 로드
    check_results = load_track_a_results(
        supabase,
        facility_id=facility_id,
        status_filter=_DEFAULT_STATUS_FILTER,
    )
    check_results = check_results[:limit]

    # 2) 역추적
    traces = run_reverse_check_batch(check_results)

    # 3) 정제 (중복 제거 + 문장 생성)
    pipeline_stages = {
        "track_a_loaded": len(check_results),
        "after_reverse_check": len(traces),
    }
    result = build_stored_diagnosis_result(
        traces=traces,
        facility_id=facility_id,
        sector=sector,
        pipeline_stages=pipeline_stages,
    )

    return result
