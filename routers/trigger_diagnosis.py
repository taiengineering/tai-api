"""Trigger Diagnosis API (TASK-006).

입력 → Trigger Generator → Obligation Generator → Applicability Adapter
→ 6W → 최종 의무 출력.

수정 금지:
  evaluate_draft_for_facility, applicability_api.evaluate, extract_six_w
→ 모두 재사용만.

ISSUE-005: router_registry/diagnosis.py 등록 필요.
  이 라우터는 돈당 위에 등록되어야 main.py에서 인식.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from db.supabase_client import get_supabase
from services.trigger_generator import generate_trigger_codes
from services.trigger_obligation_generator import generate_obligation_candidates
from services.trigger_applicability_adapter import evaluate_candidates_batch
from services.trigger_six_w_service import extract_six_w_for_candidate

router = APIRouter(
    prefix="/trigger-diagnosis",
    tags=["Trigger Diagnosis"],
)


def _build_output_obligation(
    candidate: Dict[str, Any],
    eval_result: Dict[str, Any],
    six_w: Dict[str, Any],
) -> Dict[str, Any]:
    """TASK-006: 최종 의무 출력 구조."""
    return {
        "obligation": (candidate.get("action_text") or "")[:120],
        "law_basis": "",  # ISSUE-006: semantic_clause에 law_name 없음 → JOIN 필요
        "trigger_codes": candidate.get("trigger_code") or "",
        "status": eval_result.get("applicability_status") or "UNKNOWN",
        "confidence": eval_result.get("confidence") or "MEDIUM",
        "six_w": six_w,
        "source_article_id": candidate.get("source_article_id") or "",
    }


@router.post("/{factory_id}/evaluate")
def evaluate_factory(
    factory_id: str,
    include_possible: bool = False,
) -> Dict[str, Any]:
    """TASK-006: End-to-End Trigger 기반 의무도출 실행.

    Args:
      factory_id: 대상 사업장 ID
      include_possible: True면 POSSIBLE_CANDIDATE도 포함

    Returns:
      {
        factory_id, trigger_codes, trigger_count,
        candidate_count, matched_count,
        obligations: [{obligation, law_basis, trigger_codes,
                       status, confidence, six_w, source_article_id}]
      }
    """
    supabase = get_supabase()

    # Step 1: Trigger Code Set 생성
    try:
        trigger_codes = generate_trigger_codes(factory_id, supabase)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # factory row 조회 (어댑터 평가용)
    fac_res = (
        supabase.table("factories")
        .select("*")
        .eq("id", factory_id)
        .limit(1)
        .execute()
    )
    factory_row = (fac_res.data or [{}])[0]

    # Step 2: semantic_clause 의무후보 생성
    candidates = generate_obligation_candidates(trigger_codes, supabase)

    # Step 3: Applicability 평가 (TASK-003+004)
    eval_results = evaluate_candidates_batch(candidates, factory_row, trigger_codes)

    # MATCH_CANDIDATE + 선택적 POSSIBLE_CANDIDATE 필터
    allowed = {"MATCH_CANDIDATE"}
    if include_possible:
        allowed.add("POSSIBLE_CANDIDATE")

    matched_pairs = [
        (candidates[i], eval_results[i])
        for i in range(len(eval_results))
        if eval_results[i].get("applicability_status") in allowed
    ]

    # Step 4: 6W 보강 (TASK-005)
    obligations: List[Dict[str, Any]] = []
    for cand, ev in matched_pairs:
        # candidate에 action_text/condition_text/trigger_code 합제
        enriched = {**cand, "trigger_code": ev.get("trigger_code") or cand.get("trigger_code") or ""}
        six_w = extract_six_w_for_candidate(enriched, supabase=supabase)
        obligations.append(_build_output_obligation(cand, ev, six_w))

    return {
        "factory_id": factory_id,
        "trigger_codes": trigger_codes,
        "trigger_count": len(trigger_codes),
        "candidate_count": len(candidates),
        "matched_count": len(obligations),
        "obligations": obligations,
        "status": "ok",
    }
