"""
legal_engine_adapter_run — 어댑터를 실제로 붙여 돌려보는 경로 (검증용).

설계: taieng/docs/2026-06-14_STAGE_D_LEGAL_ENGINE_ADAPTER_DESIGN.md (섹션 0: RASE 추출)
흐름:
  factory_id → 사용자입력 표준화(_input_to_facility_context, 기존 재사용)
           → 어댑터.facility_input_to_base (사업장 = 평가 주체측)
           → sector 해당 article의 의미절 적재(semantic_clause_fix, 보정 executor)
           → 어댑터.clause_to_context (의무 1건 → 표준 계약 1건)
           → policyProvider.classify_applicability (RASE 적용대상 판정)
              · BUSINESS  → 추출(KEEP)
              · AMBIGUOUS → 보류로 추출(KEEP_REVIEW, "빠짐없이")
              · AUTHORITY/FRAGMENT → 제외(DROP, 명백히 사업장 대상 아님)
           → 추출된 표준 계약 목록 반환

RASE 추출: 거름망(빼기)이 아니라 적용대상 일치하면 담음. 명백 불일치만 버리고 애매는 남김.
영역: 어댑터 변환 + 적용대상 판정만. 분해기·판정로직(GPT)·엔진코어·체크엔진코어 무수정.
의미절 읽기만. 규모 수치(≥,≤) 2차 거름은 아직(적용대상 1차만).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from services.legal_context import _input_to_facility_context
from services.anonymous_factory_service import normalize_consumer_inp, _mapping_sector_key
from services.legal_rules import normalize_sector_db
from schemas.legal_engine import DiagnoseStep1Body
from services import legal_engine_adapter as adapter
from services import legal_engine_policy as policy

log = logging.getLogger(__name__)

_PAGE = 1000
_CHUNK = 200


def _load_sector_allowed_article_ids(supabase, sector_value: str) -> Optional[Set[str]]:
    """sector → 허용 article_id 집합 (기존 표준 law_article→law_master←law_sector_mapping 재사용).
    미매핑은 가지고 감. 매핑 없거나 실패 시 None(전체 폴백)."""
    key = _mapping_sector_key(sector_value)
    if not key:
        return None
    article_law: Dict[str, str] = {}
    law_ids: Set[str] = set()
    offset = 0
    while True:
        try:
            res = supabase.table("law_article").select("id, law_id").range(offset, offset + _PAGE - 1).execute()
        except Exception as exc:
            log.warning("adapter sector-filter law_article failed: %s", exc)
            return None
        chunk = res.data or []
        if not chunk:
            break
        for row in chunk:
            aid = str(row.get("id") or "")
            lid = str(row.get("law_id") or "")
            if aid and lid:
                article_law[aid] = lid
                law_ids.add(lid)
        if len(chunk) < _PAGE:
            break
        offset += _PAGE
    if not article_law:
        return None
    law_sectors: Dict[str, List[str]] = {}
    lid_list = list(law_ids)
    for i in range(0, len(lid_list), _CHUNK):
        chunk = lid_list[i:i + _CHUNK]
        try:
            res = supabase.table("law_sector_mapping").select("law_id, sectors").in_("law_id", chunk).execute()
        except Exception as exc:
            log.warning("adapter sector-filter mapping failed: %s", exc)
            return None
        for row in res.data or []:
            lid = str(row.get("law_id") or "")
            secs = row.get("sectors") or []
            if lid:
                law_sectors[lid] = [str(s).strip().upper() for s in secs if s]
    if not law_sectors:
        return None
    allowed: Set[str] = set()
    for aid, lid in article_law.items():
        secs = law_sectors.get(lid)
        if secs is None or key in secs:
            allowed.add(aid)
    return allowed


def _load_obligation_clauses(supabase, allowed_article_ids: Optional[Set[str]]) -> List[Dict[str, Any]]:
    """semantic_clause_fix(보정 executor)에서 OBLIGATION/PROHIBITION 의무절 적재."""
    clauses: List[Dict[str, Any]] = []
    offset = 0
    while True:
        try:
            res = (
                supabase.table("semantic_clause_fix")
                .select("id, source_article_id, source_part_id, source_text, executor_text, "
                        "action_text, condition_text, cycle_text, content_type, sector")
                .in_("content_type", ["OBLIGATION", "PROHIBITION"])
                .range(offset, offset + _PAGE - 1)
                .execute()
            )
        except Exception as exc:
            log.warning("adapter clause fetch failed: %s", exc)
            break
        chunk = res.data or []
        if not chunk:
            break
        for row in chunk:
            aid = str(row.get("source_article_id") or "")
            if allowed_article_ids is not None and aid and aid not in allowed_article_ids:
                continue
            clauses.append(row)
        if len(chunk) < _PAGE:
            break
        offset += _PAGE
    return clauses


def run_adapter_diagnosis(supabase, body: DiagnoseStep1Body) -> Dict[str, Any]:
    """어댑터 변환 + RASE 적용대상 추출. (1차: 적용대상 거름까지. 규모 수치는 2차 별도.)"""
    sector_raw = body.sector.strip().upper()
    inp = normalize_consumer_inp(body)
    facility_ctx = _input_to_facility_context(sector_raw, inp)
    sector_db = normalize_sector_db(sector_raw)

    # 사용자 입력 → 사업장 base (어댑터)
    facility_base = adapter.facility_input_to_base(sector_raw, facility_ctx)

    # sector 해당 의무절 적재 → 어댑터로 표준 계약 변환 → 적용대상 판정
    allowed = _load_sector_allowed_article_ids(supabase, sector_db)
    clauses = _load_obligation_clauses(supabase, allowed)

    kept: List[Dict[str, Any]] = []           # BUSINESS (확실한 적용대상)
    review: List[Dict[str, Any]] = []         # AMBIGUOUS (보류, 빠짐없이)
    class_counts: Dict[str, int] = {
        policy.APPLY_BUSINESS: 0, policy.APPLY_AUTHORITY: 0,
        policy.APPLY_FRAGMENT: 0, policy.APPLY_AMBIGUOUS: 0,
    }
    skipped_non_obligation = 0
    dropped = 0

    for c in clauses:
        ctx = adapter.clause_to_context(c, facility_ctx)
        if ctx is None:
            skipped_non_obligation += 1
            continue
        executor = (c.get("executor_text") or "").strip()
        cls, decision = policy.classify_applicability(executor)
        class_counts[cls] = class_counts.get(cls, 0) + 1
        # 표준 계약에 적용대상 판정 부착(추적용)
        ctx["applicability"] = {"class": cls, "decision": decision}
        if decision == policy.DECISION_DROP:
            dropped += 1
            continue
        if decision == policy.DECISION_KEEP_REVIEW:
            review.append(ctx)
        else:
            kept.append(ctx)

    return {
        "adapter": adapter.adapter_definition(),
        "facility_base": facility_base,
        "sector": sector_raw,
        "counts": {
            "clauses_loaded": len(clauses),
            "skipped_non_obligation": skipped_non_obligation,
            "dropped_not_business": dropped,        # 명백히 사업장 대상 아님(행정청·조각)
            "extracted_business": len(kept),        # 확실한 적용대상
            "extracted_review": len(review),        # 보류(빠짐없이)
            "extracted_total": len(kept) + len(review),
            "by_class": class_counts,
            "sector_filtered": allowed is not None,
            "allowed_articles": len(allowed) if allowed else None,
        },
        # 추출 결과: 확실분 먼저, 보류분 뒤
        "contexts": kept + review,
    }
