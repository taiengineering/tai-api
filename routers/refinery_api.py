"""D-007 + Actor Overlay: Refinery API

중복 제거 + 문장 생성 → StoredDiagnosisResult.
Actor Overlay 연결: draft_id → article_id → semantic_clause_fix → actor_resolution

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


def _build_actor_map_by_article(
    supabase,
    draft_ids: List[str],
) -> Dict[str, dict]:
    """draft_id → article_id → semantic_clause_actor_resolution 경유로 actor 정보 로드.

    반환: {draft_id: {actor_group, actor_code, confidence}}
    """
    if not draft_ids:
        return {}

    try:
        # 1) draft_id → article_id
        draft_res = (
            supabase.table("executable_draft")
            .select("id, article_id")
            .in_("id", draft_ids)
            .execute()
        )
        draft_rows = draft_res.data or []
        # {draft_id: article_id}
        draft_to_article: Dict[str, str] = {
            str(d["id"]): str(d["article_id"])
            for d in draft_rows
            if d.get("article_id")
        }

        article_ids = list(set(draft_to_article.values()))
        if not article_ids:
            return {}

        # 2) article_id → semantic_clause_fix.id (source_article_id 기준)
        clause_res = (
            supabase.table("semantic_clause_fix")
            .select("id, source_article_id")
            .in_("source_article_id", article_ids)
            .execute()
        )
        clause_rows = clause_res.data or []
        # {article_id: clause_id} — 한 article에 clause 여러 개일 수 있으므로 첫 번째 사용
        article_to_clause: Dict[str, str] = {}
        for c in clause_rows:
            aid = str(c.get("source_article_id") or "")
            if aid and aid not in article_to_clause:
                article_to_clause[aid] = str(c["id"])

        clause_ids = list(set(article_to_clause.values()))
        if not clause_ids:
            return {}

        # 3) clause_id → actor_resolution
        actor_res = (
            supabase.table("semantic_clause_actor_resolution")
            .select("clause_id, actor_group, actor_code, confidence")
            .in_("clause_id", clause_ids)
            .execute()
        )
        # {clause_id: actor_info}
        clause_to_actor: Dict[str, dict] = {
            str(row["clause_id"]): {
                "actor_group": row.get("actor_group"),
                "actor_code": row.get("actor_code"),
                "confidence": row.get("confidence"),
            }
            for row in (actor_res.data or [])
        }

        # 4) draft_id → actor_info 조합
        result: Dict[str, dict] = {}
        for draft_id, article_id in draft_to_article.items():
            clause_id = article_to_clause.get(article_id)
            if clause_id and clause_id in clause_to_actor:
                result[draft_id] = clause_to_actor[clause_id]

        return result

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

    # 3) Actor Overlay — draft_id 경유
    draft_ids = [t.full_trace.get("stage_check", {}).get("draft_id") for t in traces]
    draft_ids = [d for d in draft_ids if d]
    actor_map = _build_actor_map_by_article(supabase, draft_ids)

    authority_count = 0
    fragment_count = 0
    business_count = 0
    unmatched_count = 0

    filtered_traces = []
    for t in traces:
        draft_id = t.full_trace.get("stage_check", {}).get("draft_id")
        actor_info = actor_map.get(str(draft_id), {}) if draft_id else {}
        ag = actor_info.get("actor_group", "UNKNOWN")

        if ag == "AUTHORITY":
            authority_count += 1
            if exclude_authority:
                continue
        elif ag == "FRAGMENT":
            fragment_count += 1
        elif ag in ("BUSINESS", "ASSOCIATION"):
            business_count += 1
        else:
            unmatched_count += 1

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
    """K-02~03: facility 기준 Actor 분류 통계."""
    supabase = get_supabase()

    check_results = load_track_a_results(
        supabase,
        facility_id=facility_id,
        status_filter=_DEFAULT_STATUS_FILTER,
    )
    traces = run_reverse_check_batch(check_results)

    draft_ids = [t.full_trace.get("stage_check", {}).get("draft_id") for t in traces]
    draft_ids = [d for d in draft_ids if d]
    actor_map = _build_actor_map_by_article(supabase, draft_ids)

    stats: Dict[str, int] = {
        "total": len(traces),
        "AUTHORITY": 0,
        "BUSINESS": 0,
        "FRAGMENT": 0,
        "ASSOCIATION": 0,
        "UNKNOWN": 0,
    }
    for t in traces:
        draft_id = t.full_trace.get("stage_check", {}).get("draft_id")
        ag = actor_map.get(str(draft_id) if draft_id else "", {}).get("actor_group", "UNKNOWN")
        if ag in stats:
            stats[ag] += 1
        else:
            stats["UNKNOWN"] += 1

    stats["actor_overlay_coverage"] = len(actor_map)
    stats["estimated_clean_after_authority_filter"] = (
        stats["total"] - stats["AUTHORITY"] - stats["FRAGMENT"]
    )
    return stats
