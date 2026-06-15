"""
legal_engine_adapter_run — 어댑터를 실제로 붙여 돌려보는 경로 (검증용).

설계: taieng/docs/2026-06-14_STAGE_D_DB_FUNCTION_VALUE_SIEVE.md
흐름 (DB+함수 전환):
  factory_id → 사용자입력 표준화 → 어댑터.facility_input_to_base
           → DB 함수 diagnose_clauses_common() 한 번 호출
              · 의무절 전체에 공용 거름(sieve_executor) 적용 = DB가 한 번에 거름
              · 각 의무에 sieve_class / sieve_decision(KEEP/DROP/KEEP_REVIEW) / rule_id
           → DROP 제외, KEEP+KEEP_REVIEW를 어댑터로 표준계약 변환

거름은 DB 함수가 정본(legal_sieve_rule 값 단위 + 함수). Python은 결과만 받아 변환.
공용 거름만 적용(대표 순서: 공용 먼저 → 섹터 나중). 섹터 거름은 다음 단계.
영역: 어댑터 변환 + 거름망 호출. 분해기·판정로직(GPT)·엔진코어·체크엔진코어 무수정.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from services.legal_context import _input_to_facility_context
from services.anonymous_factory_service import normalize_consumer_inp
from schemas.legal_engine import DiagnoseStep1Body
from services import legal_engine_adapter as adapter

log = logging.getLogger(__name__)


def _fetch_sieved_clauses(supabase) -> List[Dict[str, Any]]:
    """DB 함수 diagnose_clauses_common() 호출 — 공용 거름까지 적용된 의무절."""
    try:
        res = supabase.rpc("diagnose_clauses_common").execute()
        return res.data or []
    except Exception as exc:
        log.warning("diagnose_clauses_common rpc failed: %s", exc)
        return []


def run_adapter_diagnosis(supabase, body: DiagnoseStep1Body) -> Dict[str, Any]:
    """어댑터 변환 + 공용 거름(DB 함수). KEEP/보류를 표준계약으로. DROP은 제외."""
    sector_raw = body.sector.strip().upper()
    inp = normalize_consumer_inp(body)
    facility_ctx = _input_to_facility_context(sector_raw, inp)
    facility_base = adapter.facility_input_to_base(sector_raw, facility_ctx)

    rows = _fetch_sieved_clauses(supabase)

    kept: List[Dict[str, Any]] = []      # KEEP (확실한 사업장 적용대상)
    review: List[Dict[str, Any]] = []    # KEEP_REVIEW (보류, 빠짐없이)
    class_counts: Dict[str, int] = {}
    dropped = 0
    skipped_non_obligation = 0

    for r in rows:
        decision = r.get("sieve_decision")
        cls = r.get("sieve_class") or "AMBIGUOUS"
        class_counts[cls] = class_counts.get(cls, 0) + 1

        if decision == "DROP":
            dropped += 1
            continue

        # 어댑터가 읽는 형태로 매핑(기존 clause_to_context 호환 키)
        clause = {
            "id": r.get("clause_id"),
            "source_article_id": r.get("article_id"),
            "source_part_id": None,
            "source_text": r.get("action_text"),
            "executor_text": r.get("executor_text"),
            "action_text": r.get("action_text"),
            "condition_text": r.get("condition_text"),
            "cycle_text": r.get("cycle_text"),
            "content_type": r.get("content_type"),
            "sector": r.get("clause_sector"),
        }
        ctx = adapter.clause_to_context(clause, facility_ctx)
        if ctx is None:
            skipped_non_obligation += 1
            continue
        ctx["applicability"] = {
            "class": cls,
            "decision": decision,
            "rule_id": r.get("sieve_rule_id"),
        }
        if decision == "KEEP_REVIEW":
            review.append(ctx)
        else:
            kept.append(ctx)

    return {
        "adapter": adapter.adapter_definition(),
        "facility_base": facility_base,
        "sector": sector_raw,
        "sieve": "common (DB function diagnose_clauses_common)",
        "counts": {
            "clauses_total": len(rows),
            "skipped_non_obligation": skipped_non_obligation,
            "dropped_common": dropped,
            "extracted_keep": len(kept),
            "extracted_review": len(review),
            "extracted_total": len(kept) + len(review),
            "by_class": class_counts,
        },
        "contexts": kept + review,
    }
