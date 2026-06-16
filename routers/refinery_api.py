"""D-007 + Actor Overlay: Refinery API

중복 제거 + 문장 생성 → StoredDiagnosisResult.
Actor Overlay 연결: AUTHORITY/FRAGMENT 필터 + 통계 엔드포인트 추가.

기존 함수 삭제 금지:
  emit_stored_diagnosis_result
  assemble_refinery_result
  fetch_compiler_candidates
  evaluate_single_factory
"""
from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, Query

from db.supabase_client import get_supabase
from schemas.stored_diagnosis_schema import StoredDiagnosisResult
from services.check_engine_adapter import load_track_a_results
from services.refinery_service import build_stored_diagnosis_result
from services.reverse_check_service import run_reverse_check_batch

router = APIRouter(prefix="/refinery", tags=["D-007 Refinery"])

_DEFAULT_STATUS_FILTER = ["MATCH_CANDIDATE", "POSSIBLE_CANDIDATE"]


def _load_actor_overlay(supabase, clause_ids: List[str]) -> Dict[str, dict]:
    """semantic_clause_actor_resolution 에서 clause_id 기준으로 actor_group 로드."""
    if not clause_ids:
        return {}
    try:
        res = (
            supabase.table("semantic_clause_actor_resolution")
            .select("clause_id,actor_group,actor_code,confidence")
            .in_("clause_id", clause_ids)
            .execute()
        )
        return {
            row["clause_id"]: {
                "actor_group": row.get("actor_group"),
                "actor_code": row.get("actor_code"),
                "confidence": row.get("confidence"),
            }
            for row in (res.data or [])
        }
    except Exception:
        return {}


@router.post("/run", response_model=StoredDiagnosisResult)
def run_refinery(
    facility_id: str = Query(..., description="factories.id"),
    sector: str = Query(None, description="INDUSTRIAL / BUILDING / CONSTRUCTION (선택)"),
    limit: int = Query(500, ge=1, le=2000),
    exclude_authority: bool = Query(False, description="AUTHORITY actor 제외 여부"),
):
    """Track A → 역추적 → Actor Overlay → 중복 제거 → 문장 생성."""
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

    # 3) Actor Overlay 연결
    clause_ids = [t.clause_id for t in traces if t.clause_id]
    actor_map = _load_actor_overlay(supabase, clause_ids)

    authority_count = 0
    fragment_count = 0
    business_count = 0
    unmatched_count = 0

    filtered_traces = []
    for t in traces:
        actor_info = actor_map.get(t.clause_id, {})
        ag = actor_info.get("actor_group", "UNKNOWN")

        if ag == "AUTHORITY":
            authority_count += 1
            if exclude_authority:
                continue
        elif ag == "FRAGMENT":
            fragment_count += 1
        elif ag in ("BUSINESS",):
            business_count += 1
        else:
            unmatched_count += 1

        # trace에 actor 정보 주입
        if actor_info:
            t.full_trace["actor_overlay"] = actor_info
        filtered_traces.append(t)

    # 4) 정제
    pipeline_stages = {
        "track_a_loaded": len(check_results),
        "after_reverse_check": len(traces),
        "actor_overlay_applied": len(actor_map),
        "actor_authority": authority_count,
        "actor_fragment": fragment_count,
        "actor_business": business_count,
        "actor_unmatched": unmatched_count,
        "after_actor_filter": len(filtered_traces),
    }
    result = build_stored_diagnosis_result(
        traces=filtered_traces,
        facility_id=facility_id,
        sector=sector,
        pipeline_stages=pipeline_stages,
    )
    return result


@router.get("/actor-stats")
def get_actor_stats(
    facility_id: str = Query(..., description="factories.id"),
):
    """K-02~03: facility 기준 Actor 분류 통계.

    AUTHORITY / BUSINESS / FRAGMENT / ASSOCIATION / UNKNOWN 건수를 반환한다.
    """
    supabase = get_supabase()

    check_results = load_track_a_results(
        supabase,
        facility_id=facility_id,
        status_filter=_DEFAULT_STATUS_FILTER,
    )
    traces = run_reverse_check_batch(check_results)
    clause_ids = [t.clause_id for t in traces if t.clause_id]
    actor_map = _load_actor_overlay(supabase, clause_ids)

    stats: Dict[str, int] = {
        "total": len(traces),
        "AUTHORITY": 0,
        "BUSINESS": 0,
        "FRAGMENT": 0,
        "ASSOCIATION": 0,
        "UNKNOWN": 0,
    }
    for t in traces:
        ag = actor_map.get(t.clause_id, {}).get("actor_group", "UNKNOWN")
        if ag in stats:
            stats[ag] += 1
        else:
            stats["UNKNOWN"] += 1

    stats["actor_overlay_coverage"] = len(actor_map)
    stats["estimated_clean_after_authority_filter"] = (
        stats["total"] - stats["AUTHORITY"] - stats["FRAGMENT"]
    )
    return stats
