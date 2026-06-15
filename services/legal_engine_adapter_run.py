"""
legal_engine_adapter_run — 어댑터를 실제로 붙여 돌려보는 경로 (검증용).

설계: taieng/docs/2026-06-14_STAGE_D_DB_FUNCTION_VALUE_SIEVE.md
흐름 (DB+함수 전환):
  factory_id → 사용자입력 표준화 → 어댑터.facility_input_to_base
           → DB 함수 diagnose_clauses_common() (KEEP+보류만 반환, DROP은 DB에서 제외)
              · 의무절 전체에 공용 거름(sieve_executor) 적용 = DB가 한 번에 거름
              · 각 의무에 sieve_class / sieve_decision(KEEP/KEEP_REVIEW) / rule_id
           → 페이지네이션(.range)으로 전체 수신 → 어댑터로 표준계약 변환

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

_PAGE = 1000


def _fetch_sieved_clauses(supabase) -> List[Dict[str, Any]]:
    """DB 함수 diagnose_clauses_common() 호출 — 공용 거름 KEEP+보류.
    PostgREST 1000행 제한 → .range() 페이지네이션으로 전체 수신."""
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        try:
            res = supabase.rpc("diagnose_clauses_common").range(offset, offset + _PAGE - 1).execute()
        except Exception as exc:
            log.warning("diagnose_clauses_common rpc failed: %s", exc)
            break
        chunk = res.data or []
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < _PAGE:
            break
        offset += _PAGE
    return rows


def run_adapter_diagnosis(supabase, body: DiagnoseStep1Body) -> Dict[str, Any]:
    """어댑터 변환 + 공용 거름(DB 함수). KEEP/보류를 표준계약으로."""
    sector_raw = body.sector.strip().upper()
    inp = normalize_consumer_inp(body)
    facility_ctx = _input_to_facility_context(sector_raw, inp)
    facility_base = adapter.facility_input_to_base(sector_raw, facility_ctx)

    rows = _fetch_sieved_clauses(supabase)

    kept: List[Dict[str, Any]] = []      # KEEP (확실한 사업장 적용대상)
    review: List[Dict[str, Any]] = []    # KEEP_REVIEW (보류, 빠짐없이)
    class_counts: Dict[str, int] = {}
    skipped_non_obligation = 0

    for r in rows:
        decision = r.get("sieve_decision")
        cls = r.get("sieve_class") or "AMBIGUOUS"
        class_counts[cls] = class_counts.get(cls, 0) + 1

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
        "sieve": "common (DB function diagnose_clauses_common, paginated)",
        "counts": {
            "clauses_returned": len(rows),       # KEEP+보류 (DROP은 DB에서 제외)
            "skipped_non_obligation": skipped_non_obligation,
            "extracted_keep": len(kept),
            "extracted_review": len(review),
            "extracted_total": len(kept) + len(review),
            "by_class": class_counts,
        },
        "contexts": kept + review,
    }
